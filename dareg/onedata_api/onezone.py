import base64
import logging
import time
from datetime import datetime, timezone, timedelta

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

TIMEOUT = 15
# Space privileges given to DAREG groups, read-only access is granted by ACLs
SPACE_READ_PRIVILEGES = ["space_view", "space_read_data"]


class OnedataError(Exception):
    def __init__(self, status: int, errno: str, message: str):
        self.status = status
        self.errno = errno
        super().__init__(f"HTTP {status} {errno}: {message}")


def raise_for_onedata_error(response: requests.Response):
    """Onedata returns error details in the body (e.g. posix errors as HTTP 400 + errno)."""

    if response.status_code < 400:
        return
    try:
        error = response.json().get("error", {})
    except ValueError:
        error = {}
    details = error.get("details") or {}
    errno = details.get("errno") or error.get("id", "")
    raise OnedataError(response.status_code, errno, error.get("description") or response.text[:500])


class OnezoneClient:
    """Thin Onezone REST wrapper. Tokens are never logged."""

    def __init__(self, token: str | None = None, base_url: str | None = None):
        self.token = token if token is not None else settings.ONEDATA_SERVICE_TOKEN
        self.base_url = (base_url or settings.ONEDATA_ONEZONE_URL).rstrip("/")

    def _request(self, method: str, path: str, token: str | None = None, json=None, ok_conflict=False):
        response = requests.request(
            method,
            f"{self.base_url}{path}",
            headers={"X-Auth-Token": token or self.token, "Content-Type": "application/json"},
            json=json,
            timeout=TIMEOUT,
        )
        # 409 = relation already exists, treated as success for idempotency
        if ok_conflict and response.status_code == 409:
            return response
        raise_for_onedata_error(response)
        return response

    def create_group(self, name: str) -> str:
        response = self._request("POST", "/user/groups", json={"name": name})
        return response.headers["Location"].rstrip("/").split("/")[-1]

    def get_group(self, group_id: str) -> dict:
        return self._request("GET", f"/groups/{group_id}").json()

    def add_child_group(self, parent_id: str, child_id: str):
        self._request("PUT", f"/groups/{parent_id}/children/{child_id}", ok_conflict=True)

    def list_child_groups(self, group_id: str) -> set[str]:
        return set(self._request("GET", f"/groups/{group_id}/children").json().get("groups", []))

    def remove_child_group(self, parent_id: str, child_id: str):
        try:
            self._request("DELETE", f"/groups/{parent_id}/children/{child_id}")
        except OnedataError as e:
            if e.status != 404:
                raise

    def delete_group(self, group_id: str):
        # 403 propagates, the caller falls back to remove_child_group
        try:
            self._request("DELETE", f"/groups/{group_id}")
        except OnedataError as e:
            if e.status != 404:
                raise

    def list_group_users(self, group_id: str) -> set[str]:
        return set(self._request("GET", f"/groups/{group_id}/users").json().get("users", []))

    def add_user_to_group(self, group_id: str, user_id: str):
        self._request("PUT", f"/groups/{group_id}/users/{user_id}", ok_conflict=True)

    def remove_user_from_group(self, group_id: str, user_id: str):
        try:
            self._request("DELETE", f"/groups/{group_id}/users/{user_id}")
        except OnedataError as e:
            if e.status != 404:
                raise

    def add_group_to_space(self, space_id: str, group_id: str, privileges: list[str] = SPACE_READ_PRIVILEGES):
        self._request("PUT", f"/spaces/{space_id}/groups/{group_id}", json={"privileges": privileges}, ok_conflict=True)

    def whoami(self, token: str) -> str:
        return self._request("GET", "/user", token=token).json()["userId"]

    def create_group_invite_token(self, group_id: str, valid_minutes: int = 5) -> str:
        valid_until = int((datetime.now(timezone.utc) + timedelta(minutes=valid_minutes)).timestamp())
        response = self._request("POST", "/user/tokens/temporary", json={
            "type": {"inviteToken": {"inviteType": "userJoinGroup", "groupId": group_id}},
            "caveats": [{"type": "time", "validUntil": valid_until}],
        })
        return response.json()["token"]

    def join_group(self, user_token: str, invite_token: str):
        self._request("POST", "/user/groups/join", token=user_token, json={"token": invite_token}, ok_conflict=True)


_provider_ids: dict[str, tuple[str | None, float]] = {}
PROVIDER_ID_RETRY_SECONDS = 300


def get_provider_id(provider_url: str) -> str | None:
    """providerId from the unauthenticated provider configuration endpoint, cached per process."""

    cached = _provider_ids.get(provider_url)
    if cached and (cached[0] or time.monotonic() - cached[1] < PROVIDER_ID_RETRY_SECONDS):
        return cached[0]
    provider_id = None
    try:
        response = requests.get(f"{provider_url.rstrip('/')}/configuration", timeout=5)
        raise_for_onedata_error(response)
        provider_id = response.json().get("providerId")
    except Exception as e:
        logger.warning(f"Failed to get Onedata provider id for {provider_url}: {e}")
    _provider_ids[provider_url] = (provider_id, time.monotonic())
    return provider_id


def onedata_gui_url(dataset) -> str | None:
    """Onezone GUI deep link to the dataset folder."""

    space_id = dataset.onedata_space_id
    if not dataset.onedata_file_id or not space_id:
        return None
    try:
        # CDMI object id = 8-byte header (16 hex chars) + hex(GUID)
        guid = bytes.fromhex(dataset.onedata_file_id[16:])
    except ValueError:
        return None
    options = f"dir.{base64.urlsafe_b64encode(guid).rstrip(b'=').decode()}"
    provider_url = dataset.project.facility.onedata_provider_url
    provider_id = get_provider_id(provider_url) if provider_url else None
    if provider_id:
        options = f"oneproviderId.{provider_id}..{options}"
    return f"{settings.ONEDATA_ONEZONE_GUI_URL}#/onedata/spaces/{space_id}/data?options={options}"
