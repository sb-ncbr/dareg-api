import uuid
from unittest.mock import patch, MagicMock

from django.contrib.auth.models import User
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings
from knox.models import AuthToken
from rest_framework import status
from rest_framework.test import APITestCase

from api.models import Facility, Project, Instrument
from api.onboarding import validate_onedata_settings
from onedata_api.onezone import OnedataError
from tests.test_8_onedata_access import ONEDATA_SETTINGS, BEARER, ONEZONE_TOKEN, NOT_ACCEPTED, link_user

SYNC_URL = "/api/v1/profile/onedata-sync/"
GATED = {"code": "onedata_not_linked", "detail": "Link your Onedata account in DAREG onboarding first."}


@override_settings(**ONEDATA_SETTINGS, ONEDATA_REQUIRED=True, ONEDATA_AUTO_LINK_ENABLED=True, ONEDATA_IDP_TOKEN_PREFIX="einfracz:")
class OnboardingTestCase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="user", password="x")
        self.oidc_user = self.user

        # a Bearer header authenticates self.oidc_user, anything else falls through like the real class
        def oidc_authenticate(request):
            if request.META.get("HTTP_AUTHORIZATION", "").startswith("Bearer "):
                return self.oidc_user, BEARER
            return None
        oidc = patch("mozilla_django_oidc.contrib.drf.OIDCAuthentication.authenticate", side_effect=oidc_authenticate)
        oidc.start()
        self.addCleanup(oidc.stop)

        self.onezone = MagicMock()
        self.onezone.whoami.return_value = "od-user"
        mocks = {}
        for target, kwargs in (
            ("api.views.views.OnezoneClient", {"return_value": self.onezone}),
            ("api.views.views.mark_pending", {}),
            ("api.views.views.schedule_sync", {}),
            ("api.views.views.join_user_groups", {"return_value": ([], [])}),
        ):
            patcher = patch(target, **kwargs)
            mocks[target] = patcher.start()
            self.addCleanup(patcher.stop)
        self.mark_pending = mocks["api.views.views.mark_pending"]
        self.schedule_sync = mocks["api.views.views.schedule_sync"]
        self.join_user_groups = mocks["api.views.views.join_user_groups"]

    def bearer(self, method, url, data=None):
        return getattr(self.client, method)(url, data or {}, format="json", HTTP_AUTHORIZATION=f"Bearer {BEARER}")

    def knox(self, method, url, user, data=None):
        _, token = AuthToken.objects.create(user)
        return getattr(self.client, method)(url, data or {}, format="json", HTTP_AUTHORIZATION=f"Token {token}")

    def profile(self, user=None):
        user = user or self.user
        user.userprofile.refresh_from_db()
        return user.userprofile

    def assertGated(self, response):
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.json(), GATED)

    def assertNotGated(self, response):
        self.assertFalse(response.status_code == status.HTTP_403_FORBIDDEN
                         and response.json().get("code") == "onedata_not_linked", response.content)


class OnedataSyncDryRunTests(OnboardingTestCase):
    @override_settings(ONEDATA_SYNC_ENABLED=True)
    @patch("api.views.views.user_sync_lock")
    def test_dry_run_success_writes_nothing(self, lock):
        response = self.bearer("post", SYNC_URL, {"dry_run": True})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["found_onedata_user_id"], "od-user")
        self.assertIsNone(response.data["reason"])
        self.assertEqual(response.data["onedata_user_id"], "")
        self.onezone.whoami.assert_called_once_with(ONEZONE_TOKEN)
        profile = self.profile()
        self.assertEqual((profile.onedata_user_id, profile.onedata_last_sync_at, profile.onedata_linked_at), ("", None, None))
        lock.assert_not_called()
        self.mark_pending.assert_not_called()
        self.schedule_sync.assert_not_called()
        self.join_user_groups.assert_not_called()

    def test_dry_run_no_account(self):
        self.onezone.whoami.side_effect = OnedataError(401, "unauthorized", "no account")

        response = self.bearer("post", SYNC_URL, {"dry_run": True})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["reason"], "no_onedata_account")
        self.assertEqual(response.data["error"], NOT_ACCEPTED)
        self.assertEqual(response.data["found_onedata_user_id"], "")
        profile = self.profile()
        self.assertEqual((profile.onedata_last_sync_at, profile.onedata_last_sync_error), (None, ""))

    def test_dry_run_unavailable(self):
        for error in (OnedataError(503, "unavailable", "down"), ConnectionError("down")):
            with self.subTest(error=error):
                self.onezone.whoami.side_effect = error

                response = self.bearer("post", SYNC_URL, {"dry_run": True})

                self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
                self.assertEqual(response.data["reason"], "onedata_unavailable")
                profile = self.profile()
                self.assertEqual((profile.onedata_user_id, profile.onedata_last_sync_at, profile.onedata_last_sync_error), ("", None, ""))

    def test_confirm_links(self):
        response = self.bearer("post", SYNC_URL, {"dry_run": False})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["reason"])
        self.assertEqual(response.data["onedata_user_id"], "od-user")
        self.assertEqual(response.data["found_onedata_user_id"], "od-user")
        profile = self.profile()
        self.assertEqual(profile.onedata_user_id, "od-user")
        self.assertIsNotNone(profile.onedata_linked_at)
        self.assertIsNotNone(profile.onedata_last_sync_at)
        self.mark_pending.assert_called_once()
        self.schedule_sync.assert_called_once()

    def test_confirm_unchanged_id_keeps_linked_at(self):
        link_user(self.user, "od-user")

        response = self.bearer("post", SYNC_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(self.profile().onedata_linked_at)

    def test_confirm_failure_records_error(self):
        self.onezone.whoami.side_effect = OnedataError(401, "unauthorized", "no account")

        response = self.bearer("post", SYNC_URL)

        self.assertEqual(response.data["reason"], "no_onedata_account")
        self.assertEqual(self.profile().onedata_last_sync_error, NOT_ACCEPTED)

    @override_settings(ONEDATA_REQUIRED=False, ONEDATA_AUTO_LINK_ENABLED=False)
    def test_disabled_reason(self):
        response = self.bearer("post", SYNC_URL, {"dry_run": True})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["reason"], "auto_link_disabled")

    def test_not_oidc(self):
        self.client.force_login(self.user)
        for dry_run in (True, False):
            with self.subTest(dry_run=dry_run):
                response = self.client.post(SYNC_URL, {"dry_run": dry_run}, format="json")
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertEqual(response.data["reason"], "not_oidc")
        self.client.logout()
        for dry_run in (True, False):
            with self.subTest(knox=True, dry_run=dry_run):
                response = self.knox("post", SYNC_URL, self.user, {"dry_run": dry_run})
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertEqual(response.data["reason"], "not_oidc")
        self.onezone.whoami.assert_not_called()


class OnedataGateTests(OnboardingTestCase):
    def test_unlinked_oidc_user_is_gated(self):
        self.assertGated(self.bearer("get", "/api/v1/experiments/"))
        self.assertGated(self.bearer("get", "/api/v1/projects/"))

    def test_unlinked_oidc_user_reaches_onboarding_routes(self):
        response = self.bearer("get", "/api/v1/profile/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["results"][0]["onedata_access_allowed"], False)
        self.assertEqual(self.bearer("post", SYNC_URL, {"dry_run": True}).status_code, status.HTTP_200_OK)
        self.assertEqual(self.bearer("post", SYNC_URL).status_code, status.HTTP_200_OK)
        self.assertEqual(self.profile().onedata_user_id, "od-user")
        self.assertEqual(self.bearer("get", "/api/v1/experiments/").status_code, status.HTTP_200_OK)

    def test_unlinked_profile_patch_is_gated(self):
        self.assertGated(self.bearer("patch", f"/api/v1/profile/{self.user.userprofile.id}/", {"default_theme": "dark"}))

    def test_linked_oidc_user(self):
        link_user(self.user, "od-user")
        self.assertEqual(self.bearer("get", "/api/v1/experiments/").status_code, status.HTTP_200_OK)

    def test_instrument_knox_token_on_lab_client_routes(self):
        owner = User.objects.create_superuser(username="owner", password="x")
        instrument_user = User.objects.create_user(username="instrument", password="x")
        facility = Facility.objects.create(name="Fac", abbreviation="FAC", created_by=owner)
        project = Project.objects.create(name="Proj", facility=facility, description="d", created_by=owner)
        Instrument.objects.create(facility=facility, name="Instr", method="m", support="s", contact="c",
                                  user=instrument_user, created_by=owner)
        missing = uuid.uuid4()
        for method, url in (
            ("get", "/api/v1/reservation/?date_from=2026-01-01T00:00:00%2B00:00&date_to=2026-01-02T00:00:00%2B00:00"),
            ("get", "/api/v1/reservation/b171517a-a79a-4170-bef5-ffe93519ba92/"),
            ("get", "/api/v1/instrument/metadata/"),
            ("get", f"/api/v1/projects/{project.id}/"),
            ("get", f"/api/v1/datasets/{missing}/get_by_reservation_id/"),
            ("post", "/api/v1/experiments/"),
            ("post", f"/api/v1/temp-token/{missing}/"),
        ):
            with self.subTest(url=url):
                self.assertNotGated(self.knox(method, url, instrument_user))

    def test_non_instrument_knox_token_is_gated(self):
        self.assertGated(self.knox("get", "/api/v1/experiments/", self.user))

    def test_session(self):
        self.client.force_login(self.user)
        self.assertGated(self.client.get("/api/v1/experiments/"))

        superuser = User.objects.create_superuser(username="admin", password="x")
        self.client.force_login(superuser)
        self.assertEqual(self.client.get("/api/v1/experiments/").status_code, status.HTTP_200_OK)

    @override_settings(ONEDATA_REQUIRED=False)
    def test_gate_off(self):
        self.assertEqual(self.bearer("get", "/api/v1/experiments/").status_code, status.HTTP_200_OK)
        self.assertEqual(self.knox("get", "/api/v1/experiments/", self.user).status_code, status.HTTP_200_OK)
        self.assertEqual(self.bearer("get", "/api/v1/profile/").data["results"][0]["onedata_access_allowed"], True)


class KnoxRouteTests(OnboardingTestCase):
    def setUp(self):
        super().setUp()
        self.superuser = User.objects.create_superuser(username="admin", password="x")

    def test_login(self):
        link_user(self.user, "od-user")
        self.assertEqual(self.bearer("post", "/api/token/login/").status_code, status.HTTP_403_FORBIDDEN)
        self.oidc_user = self.superuser
        response = self.bearer("post", "/api/token/login/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("token", response.data)

    def test_logoutall(self):
        link_user(self.user, "od-user")
        self.assertEqual(self.knox("post", "/api/token/logoutall/", self.user).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.knox("post", "/api/token/logoutall/", self.superuser).status_code, status.HTTP_204_NO_CONTENT)

    def test_unlinked_user_can_logout(self):
        self.assertEqual(self.knox("post", "/api/token/logout/", self.user).status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(AuthToken.objects.filter(user=self.user).exists())

    def test_unlinked_user_login_is_gated(self):
        self.assertGated(self.bearer("post", "/api/token/login/"))


class ProfileFieldsTests(OnboardingTestCase):
    def test_profile_fields(self):
        data = self.bearer("get", "/api/v1/profile/").data["results"][0]

        self.assertEqual(data["onedata_required"], True)
        self.assertEqual(data["is_superuser"], False)
        self.assertEqual(data["onedata_access_allowed"], False)
        self.assertIsNone(data["onedata_linked_at"])

    def test_superuser_without_id_is_allowed(self):
        self.oidc_user = User.objects.create_superuser(username="admin", password="x")
        data = self.bearer("get", "/api/v1/profile/").data["results"][0]

        self.assertEqual((data["is_superuser"], data["onedata_access_allowed"]), (True, True))


class SettingsValidationTests(SimpleTestCase):
    @override_settings(ONEDATA_REQUIRED=True, ONEDATA_AUTO_LINK_ENABLED=False)
    def test_required_needs_auto_link(self):
        with self.assertRaises(ImproperlyConfigured):
            validate_onedata_settings()

    def test_valid_combinations(self):
        for required, auto_link in ((True, True), (False, False), (False, True)):
            with self.subTest(required=required, auto_link=auto_link), \
                    override_settings(ONEDATA_REQUIRED=required, ONEDATA_AUTO_LINK_ENABLED=auto_link):
                validate_onedata_settings()
