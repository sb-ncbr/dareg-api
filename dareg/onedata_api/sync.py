"""
Reconciles DAREG permissions into Onedata groups and dataset folder ACLs.
Design and verified Onedata behaviour: ONEDATA_ACCESS_CONTROL.md
"""

import logging
import re
import threading
from contextlib import contextmanager

from django.conf import settings
from django.contrib.auth.models import User
from django.db import connection, transaction
from django.utils import timezone

from api.models import Facility, Project, Dataset, PermsGroup, UserProfile, OnedataSyncState
from onedata_api.acl import apply_dataset_acl, is_acl_complete
from onedata_api.onezone import OnezoneClient, OnedataError, SPACE_READ_PRIVILEGES

logger = logging.getLogger(__name__)

ADVISORY_LOCK_ID = 7_301_966  # arbitrary, unique for this job
USER_SYNC_LOCK_NAMESPACE = 7_301_967  # arbitrary, first key of the per-user onedata-sync lock
MAX_ERRORS_PER_PASS = 10
MAX_ORPHAN_REMOVALS_PER_PASS = 20
SYNC_MODELS = (Facility, Project, Dataset)

_pass_count = 0
_orphan_removals = 0


def mark_pending(object_ids):
    for model in SYNC_MODELS:
        model.objects.filter(id__in=object_ids).update(onedata_sync_status=OnedataSyncState.PENDING)


def _group_name(prefix: str, name: str, obj_id=None, suffix: str = "") -> str:
    # Onedata group names: max 50 chars of letters, digits, _ - . ( ) and spaces
    label = re.sub(r"[^\w\-.() ]", "_", name)[:20]
    parts = [prefix, label] + ([str(obj_id)[:8]] if obj_id else []) + ([suffix] if suffix else [])
    return "-".join(parts)


def _ensure_group(client: OnezoneClient, obj, field: str, name: str, parent_id: str) -> str:
    """Creates the group (or verifies a manually entered id) and nests it under the parent."""

    group_id = getattr(obj, field)
    if group_id:
        try:
            client.get_group(group_id)
        except OnedataError as e:
            if e.status in (403, 404):
                raise ValueError(f"Onedata group {group_id} ({field}) is not accessible to the service account, "
                                 f"probably deleted. Clear the field in Django admin to recreate it. ({e})") from e
            raise
    else:
        group_id = client.create_group(name)
        # persist immediately so a later failure does not create a duplicate group
        type(obj).objects.filter(id=obj.id).update(**{field: group_id})
        setattr(obj, field, group_id)
    if parent_id:
        client.add_child_group(parent_id, group_id)
    return group_id


def _expected_members(obj) -> set[str]:
    names = [f"{obj.id}_{role}" for role in ("owner", "editor", "viewer")]
    return set(
        UserProfile.objects.filter(user__groups__name__in=names)
        .exclude(onedata_user_id="")
        .values_list("onedata_user_id", flat=True)
    )


def _sync_members(client: OnezoneClient, group_id: str, obj):
    service_user = {settings.ONEDATA_SERVICE_USER_ID}
    expected = _expected_members(obj) - service_user
    current = client.list_group_users(group_id) - service_user
    # in invite mode users are added by the Activate endpoint (no oz_* privileges needed)
    if settings.ONEDATA_MEMBERSHIP_MODE == "direct":
        for user_id in expected - current:
            client.add_user_to_group(group_id, user_id)
    for user_id in current - expected:
        client.remove_user_from_group(group_id, user_id)


def _referenced_group_ids() -> set[str]:
    group_ids = {settings.ONEDATA_ROOT_GROUP_ID, settings.ONEDATA_ADMINS_GROUP_ID}
    for model, fields in (
        (Facility, ("onedata_group_id", "onedata_staff_group_id")),
        (Project, ("onedata_group_id", "onedata_managers_group_id")),
        (Dataset, ("onedata_group_id",)),
    ):
        for field in fields:
            group_ids.update(model.objects.values_list(field, flat=True))
    return {g for g in group_ids if g}


def _cleanup_children(client: OnezoneClient, parent_id: str) -> bool:
    """Removes child groups no database row references. False when the per-pass limit stopped it."""

    global _orphan_removals
    mode = settings.ONEDATA_ORPHAN_CLEANUP
    if mode == "off" or not parent_id:
        return True
    for child_id in client.list_child_groups(parent_id) - _referenced_group_ids():
        if mode != "delete":
            logger.warning(f"Onedata cleanup (report): unused group {child_id} under {parent_id} would be removed")
            continue
        if _orphan_removals >= MAX_ORPHAN_REMOVALS_PER_PASS:
            logger.error("Onedata cleanup limit reached, remaining groups are removed in a later pass")
            return False
        # clean the child's own children first so they are not orphaned for good
        try:
            if not _cleanup_children(client, child_id):
                return False
        except OnedataError as e:
            if e.status not in (403, 404):
                raise
        try:
            client.delete_group(child_id)
            action = "deleted"
        except OnedataError as e:
            if e.status != 403:
                raise
            client.remove_child_group(parent_id, child_id)
            action = "detached"
        _orphan_removals += 1
        logger.info(f"Onedata cleanup: unused group {child_id} {action} from {parent_id}")
    return True


def sync_facility(client: OnezoneClient, facility: Facility, full: bool) -> bool:
    before = (facility.onedata_staff_group_id, facility.onedata_user_id)
    group_id = _ensure_group(client, facility, "onedata_group_id", _group_name("fac", facility.abbreviation), settings.ONEDATA_ROOT_GROUP_ID)
    staff_id = _ensure_group(client, facility, "onedata_staff_group_id", _group_name("fac", facility.abbreviation, suffix="staff"), group_id)
    _sync_members(client, staff_id, facility)
    if not facility.onedata_user_id and facility.onedata_token:
        facility.onedata_user_id = client.whoami(facility.onedata_token)
        Facility.objects.filter(id=facility.id).update(onedata_user_id=facility.onedata_user_id)
    if before != (facility.onedata_staff_group_id, facility.onedata_user_id):
        Dataset.objects.filter(project__facility=facility).update(onedata_sync_status=OnedataSyncState.PENDING)
    return _cleanup_children(client, group_id)


def sync_project(client: OnezoneClient, project: Project, full: bool) -> bool:
    facility = project.facility
    if not facility.onedata_group_id:
        raise ValueError("Facility group does not exist yet")
    if not project.onedata_space_id:
        raise ValueError("Project has no Onedata space")
    before = project.onedata_managers_group_id
    group_id = _ensure_group(client, project, "onedata_group_id", _group_name("prj", project.name, project.id), facility.onedata_group_id)
    managers_id = _ensure_group(client, project, "onedata_managers_group_id", _group_name("prj", project.name, project.id, "mgr"), group_id)
    for space_group_id in (group_id, facility.onedata_staff_group_id, settings.ONEDATA_ADMINS_GROUP_ID):
        if space_group_id:
            client.add_group_to_space(project.onedata_space_id, space_group_id, SPACE_READ_PRIVILEGES)
    _sync_members(client, managers_id, project)
    if before != managers_id:
        Dataset.objects.filter(project=project).update(onedata_sync_status=OnedataSyncState.PENDING)
    return _cleanup_children(client, group_id)


def sync_dataset(client: OnezoneClient, dataset: Dataset, full: bool) -> bool:
    project = dataset.project
    if not project.onedata_group_id:
        raise ValueError("Project group does not exist yet")
    group_id = _ensure_group(client, dataset, "onedata_group_id", _group_name("ds", dataset.name, dataset.id), project.onedata_group_id)
    _sync_members(client, group_id, dataset)
    # the full pass always re-PUTs to repair manual edits in the Onedata GUI
    apply_dataset_acl(dataset, force=full)
    return is_acl_complete(dataset)


def _run(client: OnezoneClient, sync_fn, obj, full: bool) -> bool:
    model = type(obj)
    try:
        complete = sync_fn(client, obj, full)
    except Exception as e:
        logger.warning(f"Onedata sync of {model.__name__} {obj.id} failed: {e}")
        model.objects.filter(id=obj.id).update(onedata_sync_status=OnedataSyncState.ERROR, onedata_sync_error=str(e)[:2000])
        return False
    # incomplete objects stay pending and are retried on the next pass
    model.objects.filter(id=obj.id).update(
        onedata_sync_status=OnedataSyncState.OK if complete else OnedataSyncState.PENDING,
        onedata_sync_error="",
        onedata_synced_at=timezone.now(),
    )
    return True


def _service_configured() -> bool:
    if settings.ONEDATA_SERVICE_TOKEN and settings.ONEDATA_SERVICE_USER_ID:
        return True
    # without the service user id the reconciler would remove the service account from its groups
    logger.error("Onedata sync is enabled but ONEDATA_SERVICE_TOKEN or ONEDATA_SERVICE_USER_ID is not set")
    return False


SYNC_STEPS = (
    (Facility, sync_facility, ()),
    (Project, sync_project, ("facility",)),
    (Dataset, sync_dataset, ("project__facility",)),
)


def sync_onedata():
    """One reconciler pass, called from the job loop when ONEDATA_SYNC_ENABLED."""

    global _pass_count, _orphan_removals
    if not _service_configured():
        return

    with _advisory_lock() as acquired:
        if not acquired:
            return
        full = _pass_count % max(settings.ONEDATA_FULL_PASS_EVERY_N, 1) == 0
        _pass_count += 1
        _orphan_removals = 0
        client = OnezoneClient()
        errors = 0
        for model, sync_fn, related in SYNC_STEPS:
            queryset = model.objects.select_related(*related)
            if not full:
                queryset = queryset.filter(onedata_sync_status__in=[OnedataSyncState.PENDING, OnedataSyncState.ERROR])
            for obj in queryset:
                if not _run(client, sync_fn, obj, full):
                    errors += 1
                    if errors >= MAX_ERRORS_PER_PASS:
                        logger.error("Onedata sync pass aborted after too many errors")
                        return


def sync_objects(object_ids):
    """Targeted pass right after a change, so new shares reach Onedata without waiting for the job loop."""

    try:
        if not settings.ONEDATA_SYNC_ENABLED or not _service_configured():
            return
        with _advisory_lock() as acquired:
            # not acquired: a pass is running, the objects stay pending for the job loop
            if not acquired:
                return
            client = OnezoneClient()
            for model, sync_fn, related in SYNC_STEPS:
                for obj in model.objects.select_related(*related).filter(id__in=object_ids):
                    _run(client, sync_fn, obj, False)
    finally:
        connection.close()  # runs in its own thread


def schedule_sync(object_ids):
    """Runs sync_objects in a background thread once the current transaction commits."""

    object_ids = list(object_ids)
    transaction.on_commit(lambda: threading.Thread(target=sync_objects, args=(object_ids,), daemon=True).start())


@contextmanager
def _advisory_lock():
    """The job loop runs in every process, passes must not run concurrently."""

    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [ADVISORY_LOCK_ID])
        acquired = cursor.fetchone()[0]
    try:
        yield acquired
    finally:
        if acquired:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [ADVISORY_LOCK_ID])


@contextmanager
def user_sync_lock(user: User):
    """Non-blocking per-user lock, so parallel onedata-sync calls of one user (several tabs) do not overlap."""

    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s, hashtext(%s))", [USER_SYNC_LOCK_NAMESPACE, str(user.id)])
        acquired = cursor.fetchone()[0]
    try:
        yield acquired
    finally:
        if acquired:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s, hashtext(%s))", [USER_SYNC_LOCK_NAMESPACE, str(user.id)])


def _safe_error(e: Exception) -> str:
    """OnedataError text holds no request headers; other exceptions (e.g. requests.InvalidHeader) might."""

    return str(e) if isinstance(e, OnedataError) else type(e).__name__


def expected_user_group_ids(user: User) -> list[str]:
    """Onedata groups the user should be a direct member of, following their DAREG perms."""

    object_ids = PermsGroup.objects.filter(user=user).values_list("object_id", flat=True)
    group_ids = [
        *Facility.objects.filter(id__in=object_ids).values_list("onedata_staff_group_id", flat=True),
        *Project.objects.filter(id__in=object_ids).values_list("onedata_managers_group_id", flat=True),
        *Dataset.objects.filter(id__in=object_ids).values_list("onedata_group_id", flat=True),
    ]
    return list(dict.fromkeys(g for g in group_ids if g))


def join_user_groups(user: User, user_token: str, force: bool = False) -> tuple[list[str], list[dict]]:
    """
    Invite mode: joins the user to the groups they should be in, using invite tokens
    created with the service token and consumed with the user's token (never stored).
    Without force only groups the user is not a direct member of yet are joined.
    """

    client = OnezoneClient()
    group_ids = expected_user_group_ids(user)
    if not force:
        try:
            current = client.list_user_groups(user_token)
            group_ids = [g for g in group_ids if g not in current]
        except Exception as e:
            logger.warning(f"Failed to list Onedata groups of user {user.id}, joining all: {_safe_error(e)}")
    joined, failed = [], []
    for group_id in group_ids:
        try:
            client.join_group(user_token, client.create_group_invite_token(group_id))
            joined.append(group_id)
        except Exception as e:
            error = _safe_error(e)
            logger.warning(f"Failed to join user {user.id} to Onedata group {group_id}: {error}")
            failed.append({"group_id": group_id, "error": error})
    return joined, failed
