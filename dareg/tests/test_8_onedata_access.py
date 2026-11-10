from contextlib import nullcontext
import logging
from unittest.mock import patch, MagicMock

import requests
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from knox.models import AuthToken
from rest_framework import status
from rest_framework.test import APITestCase

from api.models import Facility, Project, Dataset, PermsGroup, OnedataSyncState
from api.permissions import update_perms
from onedata_api import sync
from onedata_api.acl import build_dataset_acl, apply_dataset_acl, MASK_FULL, MASK_READ, FLAG_GROUP
from onedata_api.onezone import OnedataError, onedata_gui_url

SERVICE_USER = "svc-user"
# tests must not depend on the ONEDATA_* values of the environment they run in
ONEDATA_SETTINGS = dict(
    ONEDATA_SYNC_ENABLED=False,
    ONEDATA_ONEZONE_GUI_URL="https://onedata.e-infra.cz/ozw/onezone/i",
    ONEDATA_SERVICE_TOKEN="svc-token",
    ONEDATA_SERVICE_USER_ID=SERVICE_USER,
    ONEDATA_ROOT_GROUP_ID="root",
    ONEDATA_ADMINS_GROUP_ID="admins",
    ONEDATA_FULL_PASS_EVERY_N=10,
    ONEDATA_MEMBERSHIP_MODE="invite",
    ONEDATA_ORPHAN_CLEANUP="report",
)


class FakeOnezone:
    """In-memory Onezone used instead of OnezoneClient."""

    def __init__(self):
        self.groups = {}
        self.members = {}
        self.children = set()
        self.spaces = set()
        self.fail_names = set()
        self.forbidden_deletes = set()
        self.deleted = []

    def create_group(self, name):
        if name in self.fail_names:
            raise OnedataError(500, "internalServerError", "boom")
        group_id = f"g{len(self.groups) + 1}"
        self.groups[group_id] = name
        self.members[group_id] = {SERVICE_USER}
        return group_id

    def get_group(self, group_id):
        if group_id not in self.groups:
            raise OnedataError(404, "notFound", "not found")
        return {"groupId": group_id}

    def add_child_group(self, parent_id, child_id):
        self.children.add((parent_id, child_id))

    def list_child_groups(self, group_id):
        return {child for parent, child in self.children if parent == group_id}

    def remove_child_group(self, parent_id, child_id):
        self.children.discard((parent_id, child_id))

    def delete_group(self, group_id):
        if group_id in self.forbidden_deletes:
            raise OnedataError(403, "forbidden", "forbidden")
        self.deleted.append(group_id)
        self.groups.pop(group_id, None)
        self.children = {(p, c) for p, c in self.children if group_id not in (p, c)}

    def list_group_users(self, group_id):
        return set(self.members[group_id])

    def add_user_to_group(self, group_id, user_id):
        self.members[group_id].add(user_id)

    def remove_user_from_group(self, group_id, user_id):
        self.members[group_id].discard(user_id)

    def add_group_to_space(self, space_id, group_id, privileges):
        self.spaces.add((space_id, group_id))

    def whoami(self, token):
        return "facility-user"


def link_user(user, onedata_user_id):
    user.userprofile.onedata_user_id = onedata_user_id
    user.userprofile.save()


@override_settings(**ONEDATA_SETTINGS)
class OnedataSyncTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="owner", password="x")
        link_user(self.user, "owner-od")
        self.facility = Facility.objects.create(name="Fac", abbreviation="FAC", onedata_token="fac-token",
                                                onedata_provider_url="https://provider/api/v3/oneprovider", created_by=self.user)
        self.project = Project.objects.create(name="Proj", facility=self.facility, description="d",
                                              onedata_space_id="space1", created_by=self.user)
        self.dataset = Dataset.objects.create(name="Data", project=self.project, description="d",
                                              onedata_file_id="0000000000527692" + b"guid#x#space1".hex(), created_by=self.user)
        self.fake = FakeOnezone()
        sync._pass_count = 1  # normal (not full) pass

        for target, value in (
            ("onedata_api.sync.OnezoneClient", MagicMock(return_value=self.fake)),
            ("onedata_api.sync._advisory_lock", lambda: nullcontext(True)),
        ):
            patcher = patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch("onedata_api.acl.put_acl")
        self.put_acl = patcher.start()
        self.addCleanup(patcher.stop)

    def test_creates_groups_and_writes_acl(self):
        sync.sync_onedata()

        for obj in (self.facility, self.project, self.dataset):
            obj.refresh_from_db()
            self.assertEqual(obj.onedata_sync_status, OnedataSyncState.OK, obj.onedata_sync_error)
            self.assertTrue(obj.onedata_group_id)
        self.assertEqual(self.facility.onedata_user_id, "facility-user")
        self.assertIn(("root", self.facility.onedata_group_id), self.fake.children)
        self.assertIn((self.project.onedata_group_id, self.dataset.onedata_group_id), self.fake.children)
        self.assertIn(("space1", self.project.onedata_group_id), self.fake.spaces)
        self.assertIn(("space1", self.facility.onedata_staff_group_id), self.fake.spaces)
        self.assertIn(("space1", "admins"), self.fake.spaces)

        self.put_acl.assert_called_once()
        acl = self.put_acl.call_args.args[3]
        group_ids = {ace["identifier"].split("#")[1] for ace in acl if ace["aceflags"] == FLAG_GROUP}
        self.assertEqual(group_ids, {"admins", self.facility.onedata_staff_group_id,
                                     self.project.onedata_managers_group_id, self.dataset.onedata_group_id})

    def test_acl_put_skipped_when_unchanged_except_full_pass(self):
        sync.sync_onedata()
        Dataset.objects.update(onedata_sync_status=OnedataSyncState.PENDING)
        sync.sync_onedata()
        self.assertEqual(self.put_acl.call_count, 1)

        sync._pass_count = 0
        sync.sync_onedata()
        self.assertEqual(self.put_acl.call_count, 2)

    def test_adopts_manually_entered_group_id(self):
        self.fake.groups["manual"] = "existing"
        self.fake.members["manual"] = {SERVICE_USER}
        Facility.objects.filter(id=self.facility.id).update(onedata_group_id="manual")

        sync.sync_onedata()

        self.facility.refresh_from_db()
        self.assertEqual(self.facility.onedata_group_id, "manual")
        self.assertNotIn("fac-FAC", self.fake.groups.values())

    def test_inaccessible_group_id_is_reported_not_recreated(self):
        Facility.objects.filter(id=self.facility.id).update(onedata_group_id="deleted")

        sync.sync_onedata()

        self.facility.refresh_from_db()
        self.assertEqual(self.facility.onedata_sync_status, OnedataSyncState.ERROR)
        self.assertIn("Clear the field in Django admin", self.facility.onedata_sync_error)
        self.assertEqual(self.facility.onedata_group_id, "deleted")
        self.assertNotIn("fac-FAC", self.fake.groups.values())

    def test_invite_mode_only_removes_members(self):
        sync.sync_onedata()
        self.dataset.refresh_from_db()
        group_id = self.dataset.onedata_group_id
        self.fake.members[group_id] |= {"stranger"}
        Dataset.objects.update(onedata_sync_status=OnedataSyncState.PENDING)

        sync.sync_onedata()

        # owner is not added (invite mode), stranger removed, service account kept
        self.assertEqual(self.fake.members[group_id], {SERVICE_USER})

    @override_settings(ONEDATA_MEMBERSHIP_MODE="direct")
    def test_direct_mode_adds_members(self):
        sync.sync_onedata()
        self.dataset.refresh_from_db()
        self.assertEqual(self.fake.members[self.dataset.onedata_group_id], {SERVICE_USER, "owner-od"})

    def test_error_on_one_facility_does_not_stop_others(self):
        Facility.objects.create(name="Fac2", abbreviation="BAD", created_by=self.user)
        self.fake.fail_names.add("fac-BAD")

        sync.sync_onedata()

        bad = Facility.objects.get(abbreviation="BAD")
        self.assertEqual(bad.onedata_sync_status, OnedataSyncState.ERROR)
        self.assertIn("boom", bad.onedata_sync_error)
        self.facility.refresh_from_db()
        self.assertEqual(self.facility.onedata_sync_status, OnedataSyncState.OK)

    @override_settings(ONEDATA_SERVICE_USER_ID="")
    def test_not_configured_makes_no_calls(self):
        sync.sync_onedata()
        self.assertEqual(self.fake.groups, {})
        self.put_acl.assert_not_called()

    def test_update_perms_and_doi_mark_pending(self):
        sync.sync_onedata()
        self.dataset.refresh_from_db()
        self.assertEqual(self.dataset.onedata_sync_status, OnedataSyncState.OK)

        self.dataset.doi = "10.1234/abc"
        self.dataset.save()
        self.dataset.refresh_from_db()
        self.assertEqual(self.dataset.onedata_sync_status, OnedataSyncState.PENDING)

        Dataset.objects.update(onedata_sync_status=OnedataSyncState.OK)
        update_perms(self.dataset.id, MagicMock(data={"shares": [{"id": self.user.id, "perms": "viewer"}]}))
        self.dataset.refresh_from_db()
        self.assertEqual(self.dataset.onedata_sync_status, OnedataSyncState.PENDING)


@override_settings(**ONEDATA_SETTINGS)
class OnedataOrphanCleanupTests(TestCase):
    """Cleanup of child groups that no database row references."""

    def setUp(self):
        OnedataSyncTests.setUp(self)
        sync.sync_onedata()
        for obj in (self.facility, self.project, self.dataset):
            obj.refresh_from_db()
        self.prj_id = self.project.onedata_group_id

    def _add_child(self, parent_id, child_id):
        self.fake.groups[child_id] = child_id
        self.fake.children.add((parent_id, child_id))

    def _pass(self):
        Project.objects.update(onedata_sync_status=OnedataSyncState.PENDING)
        sync.sync_onedata()
        self.project.refresh_from_db()

    @override_settings(ONEDATA_ORPHAN_CLEANUP="delete")
    def test_delete_unused_child(self):
        self._add_child(self.prj_id, "old-ds")
        self._pass()
        self.assertEqual(self.fake.deleted, ["old-ds"])
        self.assertEqual(self.fake.list_child_groups(self.prj_id),
                         {self.project.onedata_managers_group_id, self.dataset.onedata_group_id})
        self.assertEqual(self.project.onedata_sync_status, OnedataSyncState.OK)

    @override_settings(ONEDATA_ORPHAN_CLEANUP="delete")
    def test_forbidden_delete_detaches(self):
        self._add_child(self.prj_id, "old-ds")
        self.fake.forbidden_deletes.add("old-ds")
        self._pass()
        self.assertNotIn("old-ds", self.fake.list_child_groups(self.prj_id))
        self.assertIn("old-ds", self.fake.groups)
        self.assertEqual(self.project.onedata_sync_status, OnedataSyncState.OK)

    @override_settings(ONEDATA_ORPHAN_CLEANUP="report")
    def test_report_mode_only_logs(self):
        self._add_child(self.prj_id, "old-ds")
        with patch.object(self.fake, "remove_child_group") as mock_remove, \
                self.assertLogs("onedata_api.sync", "WARNING") as logs:
            self._pass()
        mock_remove.assert_not_called()
        self.assertEqual(self.fake.deleted, [])
        self.assertIn((self.prj_id, "old-ds"), self.fake.children)
        self.assertIn("Onedata cleanup (report): unused group old-ds", "\n".join(logs.output))
        self.assertEqual(self.project.onedata_sync_status, OnedataSyncState.OK)

    @override_settings(ONEDATA_ORPHAN_CLEANUP="off")
    def test_off_mode_does_not_list_children(self):
        with patch.object(self.fake, "list_child_groups") as mock_list:
            self._pass()
        mock_list.assert_not_called()

    @override_settings(ONEDATA_ORPHAN_CLEANUP="delete")
    def test_child_referenced_by_other_object_is_kept(self):
        self._add_child(self.prj_id, "other-ds")
        other = Project.objects.create(name="Other", facility=self.facility, description="d", created_by=self.user)
        Dataset.objects.create(name="Other", project=other, description="d", onedata_group_id="other-ds", created_by=self.user)
        self._pass()
        self.assertNotIn("other-ds", self.fake.deleted)
        self.assertIn((self.prj_id, "other-ds"), self.fake.children)

    @override_settings(ONEDATA_ORPHAN_CLEANUP="delete")
    def test_root_and_admins_groups_are_kept(self):
        self._add_child(self.prj_id, "root")
        self._add_child(self.prj_id, "admins")
        self._pass()
        self.assertEqual(self.fake.deleted, [])
        self.assertTrue({(self.prj_id, "root"), (self.prj_id, "admins")} <= self.fake.children)

    @override_settings(ONEDATA_ORPHAN_CLEANUP="delete")
    def test_removal_limit_per_pass(self):
        for i in range(25):
            self._add_child(self.prj_id, f"old-{i}")
        self._pass()
        self.assertEqual(len(self.fake.deleted), sync.MAX_ORPHAN_REMOVALS_PER_PASS)
        self.assertEqual(self.project.onedata_sync_status, OnedataSyncState.PENDING)

        sync.sync_onedata()
        self.project.refresh_from_db()
        self.assertEqual(len(self.fake.deleted), 25)
        self.assertEqual(self.project.onedata_sync_status, OnedataSyncState.OK)

    @override_settings(ONEDATA_ORPHAN_CLEANUP="delete")
    def test_children_removed_before_parent(self):
        self._add_child(self.facility.onedata_group_id, "old-prj")
        self._add_child("old-prj", "old-mgr")
        Facility.objects.update(onedata_sync_status=OnedataSyncState.PENDING)
        sync.sync_onedata()
        self.assertEqual(self.fake.deleted, ["old-mgr", "old-prj"])

    def test_delete_marks_parent_pending(self):
        self.dataset.delete()
        self.project.refresh_from_db()
        self.assertEqual(self.project.onedata_sync_status, OnedataSyncState.PENDING)

        self.project.delete()
        self.facility.refresh_from_db()
        self.assertEqual(self.facility.onedata_sync_status, OnedataSyncState.PENDING)

    @override_settings(ONEDATA_ORPHAN_CLEANUP="delete")
    def test_list_children_error_marks_parent_error(self):
        with patch.object(self.fake, "list_child_groups", side_effect=OnedataError(500, "internalServerError", "boom")):
            Facility.objects.update(onedata_sync_status=OnedataSyncState.PENDING)
            Dataset.objects.update(onedata_sync_status=OnedataSyncState.PENDING)
            self._pass()
        self.facility.refresh_from_db()
        for obj in (self.facility, self.project):
            self.assertEqual(obj.onedata_sync_status, OnedataSyncState.ERROR)
            self.assertIn("boom", obj.onedata_sync_error)
        self.dataset.refresh_from_db()
        self.assertEqual(self.dataset.onedata_sync_status, OnedataSyncState.OK)


@override_settings(**ONEDATA_SETTINGS)
class DatasetAclTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(username="owner", password="x")
        facility = Facility.objects.create(name="Fac", abbreviation="FAC", onedata_user_id="facility-user",
                                           onedata_staff_group_id="staff", created_by=user)
        project = Project.objects.create(name="Proj", facility=facility, description="d", onedata_space_id="space1",
                                         onedata_managers_group_id="mgr", created_by=user)
        self.dataset = Dataset.objects.create(name="Data", project=project, description="d", onedata_group_id="ds",
                                              onedata_file_id="file1", created_by=user)

    def test_build_dataset_acl(self):
        acl = build_dataset_acl(self.dataset)
        by_id = {ace["identifier"].split("#")[-1]: ace for ace in acl}

        self.assertEqual(by_id[SERVICE_USER]["acemask"], MASK_FULL)
        self.assertEqual(by_id["facility-user"]["acemask"], MASK_FULL)
        for group_id in ("admins", "staff", "mgr", "ds"):
            self.assertEqual(by_id[group_id]["acemask"], MASK_READ)
            self.assertEqual(by_id[group_id]["aceflags"], FLAG_GROUP)
        identifiers = [ace["identifier"] for ace in acl]
        for forbidden in ("ANONYMOUS@", "EVERYONE@", "OWNER@", "OWNING GROUP@"):
            self.assertNotIn(forbidden, identifiers)

    def test_anonymous_only_with_doi(self):
        self.dataset.doi = "10.1234/abc"
        anonymous = [ace for ace in build_dataset_acl(self.dataset) if ace["identifier"] == "ANONYMOUS@"]
        self.assertEqual(len(anonymous), 1)
        self.assertEqual(anonymous[0]["acemask"], MASK_READ)

    def test_same_service_and_facility_user_listed_once(self):
        self.dataset.project.facility.onedata_user_id = SERVICE_USER
        acl = build_dataset_acl(self.dataset)
        self.assertEqual(sum(1 for ace in acl if ace["acemask"] == MASK_FULL), 1)

    @patch("onedata_api.acl.put_acl")
    def test_apply_dataset_acl_stores_hash(self, mock_put):
        apply_dataset_acl(self.dataset)
        apply_dataset_acl(self.dataset)
        mock_put.assert_called_once()
        self.dataset.refresh_from_db()
        self.assertTrue(self.dataset.onedata_acl_hash)

    @patch("onedata_api.onezone.get_provider_id", return_value="prov1")
    def test_onedata_gui_url(self, _):
        guid = "guid#f195e72ee28ed364b5071fa24e2c37f2ch3d87#407a0d5100d1066a3a813b1ea1bae540ch9a2a"
        self.dataset.onedata_file_id = "0000000000527692" + guid.encode().hex()
        self.dataset.project.facility.onedata_provider_url = "https://provider/api/v3/oneprovider"

        url = onedata_gui_url(self.dataset)

        self.assertEqual(url, "https://onedata.e-infra.cz/ozw/onezone/i#/onedata/spaces/space1/data?options="
                              "oneproviderId.prov1..dir.Z3VpZCNmMTk1ZTcyZWUyOGVkMzY0YjUwNzFmYTI0ZTJjMzdmMmNoM2Q4NyM0MDdhMGQ1MTAwZDEwNjZhM2E4MTNiMWVhMWJhZTU0MGNoOWEyYQ")
        self.dataset.onedata_file_id = None
        self.assertIsNone(onedata_gui_url(self.dataset))


class MockedFolder:
    file_id = "folder-id"


class MockedShare:
    share_id = "share-id"


@override_settings(**ONEDATA_SETTINGS)
@patch("api.views.views.establish_dataset", return_value=("od-dataset", None))
@patch("api.views.views.create_public_share", return_value=(MockedShare(), None))
@patch("api.views.views.create_new_dataset", return_value=(MockedFolder(), None))
class DatasetCreateAclTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="owner", password="x")
        self.client.force_authenticate(user=self.user)
        facility = Facility.objects.create(name="Fac", abbreviation="FAC", created_by=self.user)
        self.project = Project.objects.create(name="Proj", facility=facility, description="d", created_by=self.user)

    def _create(self):
        return self.client.post("/api/v1/datasets/", {"name": "New", "description": "d", "project": str(self.project.id)}, format="json")

    @patch("api.views.views.apply_dataset_acl")
    def test_flag_off_does_not_touch_onedata_acl(self, mock_apply, *_):
        response = self._create()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        mock_apply.assert_not_called()

    @override_settings(ONEDATA_SYNC_ENABLED=True)
    @patch("api.views.views.apply_dataset_acl", side_effect=OnedataError(400, "eacces", "denied"))
    def test_acl_failure_does_not_break_create(self, mock_apply, *_):
        response = self._create()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        mock_apply.assert_called_once()
        dataset = Dataset.objects.get(id=response.data["id"])
        self.assertEqual(dataset.onedata_sync_status, OnedataSyncState.ERROR)
        self.assertEqual(dataset.onedata_file_id, "folder-id")


# INVITE-MODE (disabled, replaced by auto-link)
# @override_settings(**ONEDATA_SETTINGS)
# class OnedataLinkTests(APITestCase):
#     def setUp(self):
#         self.user = User.objects.create_user(username="user", password="x")
#         self.client.force_authenticate(user=self.user)
#         self.url = "/api/v1/profile/onedata-link/"
#
#     @patch("api.views.views.join_user_groups")
#     @patch("api.views.views.OnezoneClient")
#     def test_link_stores_user_id_only(self, mock_client, mock_join):
#         mock_client.return_value.whoami.return_value = "od-user"
#
#         response = self.client.post(self.url, {"token": "secret-token"}, format="json")
#
#         self.assertEqual(response.status_code, status.HTTP_200_OK)
#         self.assertEqual(response.data["onedata_user_id"], "od-user")
#         self.user.userprofile.refresh_from_db()
#         self.assertEqual(self.user.userprofile.onedata_user_id, "od-user")
#         self.assertNotIn("secret-token", str(response.data))
#         mock_join.assert_not_called()  # sync flag is off
#
#     @patch("api.views.views.OnezoneClient")
#     def test_invalid_token(self, mock_client):
#         mock_client.return_value.whoami.side_effect = OnedataError(401, "tokenInvalid", "invalid")
#         response = self.client.post(self.url, {"token": "bad"}, format="json")
#         self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
#
#     def test_profile_onedata_user_id_is_read_only(self):
#         self.client.patch("/api/v1/profile/", {"onedata_user_id": "spoofed"}, format="json")
#         self.user.userprofile.refresh_from_db()
#         self.assertEqual(self.user.userprofile.onedata_user_id, "")


# INVITE-MODE (disabled, replaced by auto-link)
# @override_settings(**ONEDATA_SETTINGS)
# class JoinUserGroupsTests(TestCase):
#     def test_joins_groups_of_user_perms(self):
#         user = User.objects.create_user(username="owner", password="x")
#         facility = Facility.objects.create(name="Fac", abbreviation="FAC", onedata_staff_group_id="staff", created_by=user)
#         Project.objects.create(name="Proj", facility=facility, description="d", onedata_managers_group_id="mgr", created_by=user)
#         viewer =User.objects.create_user(username="viewer", password="x")
#         PermsGroup.objects.get(name=f"{facility.id}_viewer").user_set.add(viewer)
#
#         with patch("onedata_api.sync.OnezoneClient") as mock_client:
#             client = mock_client.return_value
#             client.create_group_invite_token.return_value = "invite"
#             joined, failed = sync.join_user_groups(viewer, "user-token")
#
#         self.assertEqual(joined, ["staff"])
#         self.assertEqual(failed, [])
#         client.join_group.assert_called_once_with("user-token", "invite")


BEARER = "test-bearer-token"
NOT_ACCEPTED = "Onedata did not accept your e-infra login. If you have never used Onedata, log in once at https://onedata.e-infra.cz and then retry."


class LogCapture(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


UNAVAILABLE = "Onedata is not available, please try again later."
ONEZONE_TOKEN = f"einfracz:{BEARER}"


def fail_for(invite_token, error):
    """join_group side effect that fails only for one invite token."""

    def join_group(user_token, invite):
        if invite == invite_token:
            raise error
    return join_group


@override_settings(**ONEDATA_SETTINGS)
class JoinUserGroupsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="user", password="x")
        facility = Facility.objects.create(name="Fac", abbreviation="FAC", onedata_staff_group_id="staff", created_by=self.user)
        project = Project.objects.create(name="Proj", facility=facility, description="d", onedata_managers_group_id="mgr", created_by=self.user)
        Project.objects.create(name="Empty", facility=facility, description="d", created_by=self.user)
        Dataset.objects.create(name="Data", project=project, description="d", onedata_group_id="mgr", created_by=self.user)
        patcher = patch("onedata_api.sync.OnezoneClient")
        self.onezone = patcher.start().return_value
        self.addCleanup(patcher.stop)
        self.onezone.create_group_invite_token.side_effect = lambda group_id: f"invite-{group_id}"
        self.onezone.list_user_groups.return_value = {"staff"}

    def test_expected_groups_deduplicated_without_empty(self):
        self.assertEqual(sync.expected_user_group_ids(self.user), ["staff", "mgr"])

    def test_skips_groups_user_is_in(self):
        joined, failed = sync.join_user_groups(self.user, "user-token")
        self.assertEqual((joined, failed), (["mgr"], []))
        self.onezone.list_user_groups.assert_called_once_with("user-token")
        self.onezone.join_group.assert_called_once_with("user-token", "invite-mgr")

    def test_force_joins_all(self):
        joined, failed = sync.join_user_groups(self.user, "user-token", force=True)
        self.assertEqual((joined, failed), (["staff", "mgr"], []))
        self.onezone.list_user_groups.assert_not_called()

    def test_failure_does_not_stop_others(self):
        error = OnedataError(403, "forbidden", "denied")
        self.onezone.join_group.side_effect = fail_for("invite-staff", error)
        joined, failed = sync.join_user_groups(self.user, "user-token", force=True)
        self.assertEqual(joined, ["mgr"])
        self.assertEqual(failed, [{"group_id": "staff", "error": str(error)}])


@override_settings(**ONEDATA_SETTINGS, ONEDATA_AUTO_LINK_ENABLED=True, ONEDATA_IDP_TOKEN_PREFIX="einfracz:")
class OnedataAutoLinkTests(APITestCase):
    url = "/api/v1/profile/onedata-sync/"

    def setUp(self):
        self.user = User.objects.create_user(username="user", password="x")
        oidc = patch("mozilla_django_oidc.contrib.drf.OIDCAuthentication.authenticate", return_value=(self.user, BEARER))
        self.oidc_authenticate = oidc.start()
        self.addCleanup(oidc.stop)

        # one fake Onezone for the view (whoami) and join_user_groups
        self.onezone = MagicMock()
        self.onezone.whoami.return_value = "od-user"
        self.onezone.list_user_groups.return_value = {"staff"}
        self.onezone.create_group_invite_token.side_effect = lambda group_id: f"invite-{group_id}"
        mocks = {}
        for target, kwargs in (
            ("api.views.views.OnezoneClient", {"return_value": self.onezone}),
            ("onedata_api.sync.OnezoneClient", {"return_value": self.onezone}),
            ("api.views.views.mark_pending", {"wraps": sync.mark_pending}),
            ("api.views.views.schedule_sync", {}),
        ):
            patcher = patch(target, **kwargs)
            mocks[target] = patcher.start()
            self.addCleanup(patcher.stop)
        self.mark_pending = mocks["api.views.views.mark_pending"]
        self.schedule_sync = mocks["api.views.views.schedule_sync"]

        # every log record is checked for the bearer token
        self.logs = LogCapture()
        root = logging.getLogger()
        self.addCleanup(root.setLevel, root.level)
        self.addCleanup(root.removeHandler, self.logs)
        root.addHandler(self.logs)
        root.setLevel(logging.DEBUG)

    def _post(self, auth=f"Bearer {BEARER}", data=None):
        response = self.client.post(self.url, data or {}, format="json", HTTP_AUTHORIZATION=auth)
        self.assertNotIn(BEARER, response.content.decode())
        self.assertFalse([m for m in self.logs.messages if BEARER in m])
        return response

    def _profile(self):
        self.user.userprofile.refresh_from_db()
        return self.user.userprofile

    def _create_objects(self):
        facility = Facility.objects.create(name="Fac", abbreviation="FAC", onedata_staff_group_id="staff", created_by=self.user)
        Project.objects.create(name="Proj", facility=facility, description="d", onedata_managers_group_id="mgr", created_by=self.user)

    def _user_object_ids(self):
        return list(PermsGroup.objects.filter(user=self.user).values_list("object_id", flat=True))

    @override_settings(ONEDATA_SYNC_ENABLED=True)
    def test_normal_poll(self):
        link_user(self.user, "od-user")
        self._create_objects()

        response = self._post()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["joined_groups"], ["mgr"])
        self.assertEqual(response.data["skipped"], False)
        self.onezone.whoami.assert_called_once_with(ONEZONE_TOKEN)
        self.onezone.list_user_groups.assert_called_once_with(ONEZONE_TOKEN)
        self.onezone.create_group_invite_token.assert_called_once_with("mgr")
        self.onezone.join_group.assert_called_once_with(ONEZONE_TOKEN, "invite-mgr")
        self.mark_pending.assert_not_called()
        self.schedule_sync.assert_not_called()
        profile = self._profile()
        self.assertIsNotNone(profile.onedata_last_sync_at)
        self.assertEqual(profile.onedata_last_sync_error, "")
        self.assertIsNotNone(response.data["onedata_last_sync_at"])

    @override_settings(ONEDATA_IDP_TOKEN_PREFIX="x:")
    def test_custom_prefix(self):
        self.assertEqual(self._post().status_code, status.HTTP_200_OK)
        self.onezone.whoami.assert_called_once_with(f"x:{BEARER}")

    def test_id_change(self):
        link_user(self.user, "old-id")
        self._create_objects()
        self.onezone.whoami.return_value = "new-id"

        response = self._post()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["onedata_user_id"], "new-id")
        self.assertEqual(self._profile().onedata_user_id, "new-id")
        self.assertIn(f"Onedata user id changed for user {self.user.id}: old-id -> new-id", self.logs.messages)
        object_ids = self._user_object_ids()
        self.assertTrue(object_ids)
        self.mark_pending.assert_called_once_with(object_ids)
        self.schedule_sync.assert_called_once_with(object_ids)

    @override_settings(ONEDATA_SYNC_ENABLED=True)
    def test_force(self):
        link_user(self.user, "od-user")
        self._create_objects()

        response = self._post(data={"force": True})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["joined_groups"], ["staff", "mgr"])
        self.onezone.list_user_groups.assert_not_called()
        self.mark_pending.assert_called_once_with(self._user_object_ids())
        self.schedule_sync.assert_called_once_with(self._user_object_ids())

    def test_lock_busy(self):
        with patch("api.views.views.user_sync_lock", return_value=nullcontext(False)):
            response = self._post()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["skipped"], True)
        self.assertEqual(self.onezone.method_calls, [])
        profile = self._profile()
        self.assertIsNone(profile.onedata_last_sync_at)
        self.assertEqual(profile.onedata_user_id, "")

    def test_onezone_rejects_token(self):
        link_user(self.user, "stored")
        self.onezone.whoami.side_effect = OnedataError(401, "badToken", "invalid")

        response = self._post()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], NOT_ACCEPTED)
        self.assertEqual(response.data["onedata_user_id"], "stored")
        profile = self._profile()
        self.assertEqual(profile.onedata_user_id, "stored")
        self.assertEqual(profile.onedata_last_sync_error, NOT_ACCEPTED)
        self.assertIsNotNone(profile.onedata_last_sync_at)

    def test_onezone_unavailable(self):
        link_user(self.user, "stored")
        for error in (OnedataError(503, "unavailable", "down"), requests.ConnectionError("down")):
            with self.subTest(error=error):
                self.onezone.whoami.side_effect = error
                response = self._post()
                self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
                self.assertEqual(response.data["error"], UNAVAILABLE)
                profile = self._profile()
                self.assertEqual(profile.onedata_last_sync_error, UNAVAILABLE)
                self.assertEqual(profile.onedata_user_id, "stored")

    @override_settings(ONEDATA_SYNC_ENABLED=True)
    def test_partial_group_failure(self):
        self._create_objects()
        self.onezone.list_user_groups.return_value = set()
        error = OnedataError(403, "forbidden", "denied")
        self.onezone.join_group.side_effect = fail_for("invite-mgr", error)

        response = self._post()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["joined_groups"], ["staff"])
        self.assertEqual(response.data["failed_groups"], [{"group_id": "mgr", "error": str(error)}])
        self.assertEqual(response.data["onedata_last_sync_error"], "1 Onedata group(s) could not be joined.")
        self.assertEqual(self._profile().onedata_last_sync_error, "1 Onedata group(s) could not be joined.")

    @override_settings(ONEDATA_SYNC_ENABLED=True)
    def test_list_user_groups_failure_joins_all(self):
        self._create_objects()
        self.onezone.list_user_groups.side_effect = OnedataError(500, "internalServerError", "boom")

        response = self._post()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["joined_groups"], ["staff", "mgr"])

    @override_settings(ONEDATA_AUTO_LINK_ENABLED=False)
    def test_disabled(self):
        link_user(self.user, "stored")

        response = self._post()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["enabled"], False)
        self.assertEqual(response.data["onedata_user_id"], "stored")
        self.assertEqual(self.onezone.method_calls, [])
        self.assertIsNone(self._profile().onedata_last_sync_at)
        profile = self.client.get("/api/v1/profile/", HTTP_AUTHORIZATION=f"Bearer {BEARER}").data["results"][0]
        self.assertEqual(profile["onedata_auto_link_enabled"], False)

    def test_not_oidc(self):
        self.oidc_authenticate.return_value = None  # like the real one for a non-Bearer header
        _, knox_token = AuthToken.objects.create(self.user)
        for name, auth in (("knox", f"Token {knox_token}"), ("session", "")):
            with self.subTest(name):
                if name == "session":
                    self.client.force_login(self.user)
                response = self._post(auth=auth)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertEqual(response.data["error"], "Onedata auto-link requires an e-infra login.")
                self.assertEqual(self.onezone.method_calls, [])
                self.assertIsNone(self._profile().onedata_last_sync_at)

    @patch("api.views.views.join_user_groups")
    def test_membership_mode(self, mock_join):
        for overrides in ({"ONEDATA_SYNC_ENABLED": True, "ONEDATA_MEMBERSHIP_MODE": "direct"}, {"ONEDATA_SYNC_ENABLED": False}):
            with override_settings(**overrides):
                self.assertEqual(self._post().status_code, status.HTTP_200_OK)
        mock_join.assert_not_called()

    @override_settings(ONEDATA_SYNC_ENABLED=True)
    def test_exception_text_never_leaks_token(self):
        self._create_objects()
        self.onezone.join_group.side_effect = requests.exceptions.InvalidHeader(f"Invalid header value {BEARER}")

        response = self._post()  # checks the response and the logs for the bearer

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual({f["error"] for f in response.data["failed_groups"]}, {"InvalidHeader"})

    def test_profile_onedata_fields_are_read_only(self):
        response = self.client.patch(f"/api/v1/profile/{self.user.userprofile.id}/", {
            "onedata_user_id": "spoofed",
            "onedata_last_sync_at": "2020-01-01T00:00:00Z",
            "onedata_last_sync_error": "spoofed",
            "onedata_auto_link_enabled": False,
        }, format="json", HTTP_AUTHORIZATION=f"Bearer {BEARER}")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["onedata_auto_link_enabled"], True)
        profile = self._profile()
        self.assertEqual((profile.onedata_user_id, profile.onedata_last_sync_at, profile.onedata_last_sync_error), ("", None, ""))


@override_settings(**ONEDATA_SETTINGS)
class TargetedSyncTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="owner", password="x")
        self.client.force_authenticate(user=self.user)
        self.facility = Facility.objects.create(name="Fac", abbreviation="FAC", created_by=self.user)
        self.project = Project.objects.create(name="Proj", facility=self.facility, description="d", created_by=self.user)
        self.dataset = Dataset.objects.create(name="Data", project=self.project, description="d", created_by=self.user)
        patcher = patch("onedata_api.sync.threading.Thread")
        self.thread = patcher.start()
        self.addCleanup(patcher.stop)

    def _scheduled_ids(self):
        self.thread.assert_called_once()
        self.assertIs(self.thread.call_args.kwargs["target"], sync.sync_objects)
        self.thread.return_value.start.assert_called_once()
        return [str(i) for i in self.thread.call_args.kwargs["args"][0]]

    def test_share_schedules_sync(self):
        other = User.objects.create_user(username="other", password="x")
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.patch(f"/api/v1/projects/{self.project.id}/",
                                         {"shares": [{"id": other.id, "perms": "viewer"}]}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self._scheduled_ids(), [str(self.project.id)])

    @patch("onedata_api.sync.connection")
    @patch("onedata_api.sync.OnezoneClient")
    def test_sync_disabled_does_nothing(self, mock_client, _):
        sync.sync_objects([self.project.id])
        mock_client.assert_not_called()

    @patch("api.views.views.establish_dataset", return_value=("od-dataset", None))
    @patch("api.views.views.create_public_share", return_value=(MockedShare(), None))
    @patch("api.views.views.create_new_dataset", return_value=(MockedFolder(), None))
    def test_dataset_create_schedules_sync(self, *_):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post("/api/v1/datasets/", {"name": "New", "description": "d", "project": str(self.project.id)}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(self._scheduled_ids(), [str(response.data["id"])])

    @override_settings(ONEDATA_SYNC_ENABLED=True)
    @patch("onedata_api.sync.connection")
    @patch("onedata_api.sync._advisory_lock", return_value=nullcontext(False))
    @patch("onedata_api.sync.OnezoneClient")
    def test_global_lock_busy(self, mock_client, *_):
        sync.sync_objects([self.project.id])
        mock_client.assert_not_called()
        self.project.refresh_from_db()
        self.assertEqual(self.project.onedata_sync_status, OnedataSyncState.PENDING)

    @override_settings(ONEDATA_SYNC_ENABLED=True)
    @patch("onedata_api.sync.connection")
    @patch("onedata_api.sync._advisory_lock", return_value=nullcontext(True))
    @patch("onedata_api.sync.OnezoneClient")
    @patch("onedata_api.sync._run")
    def test_only_given_ids_in_model_order(self, mock_run, *_):
        Project.objects.create(name="Other", facility=self.facility, description="d", created_by=self.user)

        sync.sync_objects([self.dataset.id, self.project.id, self.facility.id])

        calls = [(c.args[1], c.args[2].id, c.args[3]) for c in mock_run.call_args_list]
        self.assertEqual(calls, [
            (sync.sync_facility, self.facility.id, False),
            (sync.sync_project, self.project.id, False),
            (sync.sync_dataset, self.dataset.id, False),
        ])
