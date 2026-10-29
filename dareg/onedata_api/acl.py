import hashlib
import json
from urllib.parse import quote

import requests
from django.conf import settings

from api.models import Dataset
from onedata_api.onezone import TIMEOUT, raise_for_onedata_error

# CDMI ACL values verified on Onedata 25.1
ACE_ALLOW = "0x0"
FLAG_USER = "0x0"
FLAG_GROUP = "0x40"
MASK_READ = "0x200A9"
MASK_FULL = "0x701FF"


def _ace(identifier: str, flags: str, mask: str) -> dict:
    return {"identifier": identifier, "acetype": ACE_ALLOW, "aceflags": flags, "acemask": mask}


def build_dataset_acl(dataset: Dataset) -> list[dict]:
    """Dataset folder ACL derived from DB (table 4.3). Entries whose group does not exist yet are omitted."""

    project = dataset.project
    facility = project.facility
    acl = []
    full_users = [settings.ONEDATA_SERVICE_USER_ID, facility.onedata_user_id]
    for user_id in dict.fromkeys(u for u in full_users if u):
        acl.append(_ace(f"dareg#{user_id}", FLAG_USER, MASK_FULL))
    read_groups = [
        settings.ONEDATA_ADMINS_GROUP_ID,
        facility.onedata_staff_group_id,
        project.onedata_managers_group_id,
        dataset.onedata_group_id,
    ]
    for group_id in read_groups:
        if group_id:
            acl.append(_ace(f"dareg#{group_id}", FLAG_GROUP, MASK_READ))
    if dataset.doi:
        acl.append(_ace("ANONYMOUS@", FLAG_USER, MASK_READ))
    return acl


def is_acl_complete(dataset: Dataset) -> bool:
    """True when all ids the reconciler is responsible for exist (the rest comes from settings)."""

    project = dataset.project
    facility = project.facility
    return all([facility.onedata_user_id, facility.onedata_staff_group_id, project.onedata_managers_group_id, dataset.onedata_group_id])


def acl_hash(acl: list[dict]) -> str:
    return hashlib.sha256(json.dumps(acl, sort_keys=True).encode()).hexdigest()


def put_acl(provider_url: str, token: str, file_id: str, acl: list[dict]):
    """Replace the whole ACL of a file/folder via CDMI (addressed by path, the verified form)."""

    headers = {"X-Auth-Token": token}
    response = requests.get(f"{provider_url}/data/{file_id}", params={"attributes": "path"}, headers=headers, timeout=TIMEOUT)
    raise_for_onedata_error(response)
    path = response.json()["path"]

    cdmi_url = provider_url.replace("/api/v3/oneprovider", "/cdmi")
    response = requests.put(
        f"{cdmi_url}{quote(path)}/?metadata:cdmi_acl",
        headers={
            **headers,
            "X-CDMI-Specification-Version": "1.1.1",
            "Content-Type": "application/cdmi-container",
        },
        json={"metadata": {"cdmi_acl": acl}},
        timeout=TIMEOUT,
    )
    raise_for_onedata_error(response)


def apply_dataset_acl(dataset: Dataset, force: bool = False) -> list[dict]:
    """Write the dataset folder ACL with the service token; skipped when unchanged unless forced."""
    
    if not dataset.onedata_file_id:
        raise ValueError("Dataset has no Onedata folder")
    acl = build_dataset_acl(dataset)
    new_hash = acl_hash(acl)
    if force or new_hash != dataset.onedata_acl_hash:
        put_acl(dataset.project.facility.onedata_provider_url, settings.ONEDATA_SERVICE_TOKEN, dataset.onedata_file_id, acl)
        Dataset.objects.filter(id=dataset.id).update(onedata_acl_hash=new_hash)
        dataset.onedata_acl_hash = new_hash
    return acl
