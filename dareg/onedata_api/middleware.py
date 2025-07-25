from datetime import datetime, timezone, timedelta
from http.client import responses

import requests
import oneprovider_client
from onedata_wrapper.api.file_operations_api import FileOperationsApi
from onedata_wrapper.api.space_api import SpaceApi
from onedata_wrapper.api.share_api import ShareApi
from onedata_wrapper.models.filesystem.dir_entry import DirEntry
from onedata_wrapper.models.filesystem.file_entry import FileEntry
from onedata_wrapper.models.space.space_request import SpaceRequest
from onedata_wrapper.models.filesystem.entry_request import EntryRequest
from onedata_wrapper.models.filesystem.new_directory_request import NewDirectoryRequest
from onedata_wrapper.models.share.new_share_request import NewShareRequest
from onedata_wrapper.selectors.file_attribute import ALL as FA_ALL
from api.models import Project, Dataset, Facility
import base64



def create_public_share(project: Project, dataset_name: str, dataset_description: str, file_entry: FileEntry):
    oneprovider_configuration = oneprovider_client.configuration.Configuration()
    oneprovider_configuration.host = project.facility.onedata_provider_url
    oneprovider_configuration.api_key['X-Auth-Token'] = project.facility.onedata_token

    share_api = ShareApi(oneprovider_configuration)
    new_share = None
    error = None
    try:
        print(f"Setting permissions for the dataset {dataset_name} to 0645", flush=True)
        url = f"{oneprovider_configuration.host}/data/{file_entry.file_id}"
        headers = {
            "X-Auth-Token": oneprovider_configuration.api_key['X-Auth-Token'],
            "Content-Type": "application/json"
        }
        data = {
            "mode": "0645"
        }
        print(f"PUT {url} {headers} {data}", flush=True)
        response = requests.put(url, headers=headers, json=data)   
    except Exception as e:
        error = {"error": f"Failed to set permissions for the dataset. {e} {response.text}"}
        print(f"Failed to set permissions for the dataset. {e} {response.text}", flush=True)

    try:
        share = NewShareRequest(entry=file_entry, name=f"Default share for {dataset_name}", description=dataset_description)
        new_share = share_api.new_share(share)
    except Exception as e:
        error = {"error": f"Failed to create the share for the dataset. {e}"}
        
    return new_share, error

def establish_dataset(project: Project, file_entry: FileEntry | str):
    oneprovider_configuration = oneprovider_client.configuration.Configuration()
    oneprovider_configuration.host = project.facility.onedata_provider_url
    oneprovider_configuration.api_key['X-Auth-Token'] = project.facility.onedata_token
    error = None
    file_id = ""
    if isinstance(file_entry, FileEntry) or isinstance(file_entry, DirEntry):
        file_id = file_entry.file_id
    else:
        file_id = file_entry

    dataset_id = None
    try:
        print(f"Establishing dataset on top of directory {file_id}", flush=True)
        url = f"{oneprovider_configuration.host}/datasets"
        headers = {
            "X-Auth-Token": oneprovider_configuration.api_key['X-Auth-Token'],
            "Content-Type": "application/json"
        }
        data = {
            "rootFileId": file_id
        }
        response = requests.post(url, headers=headers, json=data)
        print(response.status_code, flush=True)

        if response.status_code == 201:
            dataset_id = response.json().get("datasetId")
    except Exception as e:
        error = {"error": f"Failed to establish dataset on top of directory {file_id}. {e}"}

    return dataset_id, error

def create_new_dataset(project: Project, dataset_name: str):
    oneprovider_configuration = oneprovider_client.configuration.Configuration()
    oneprovider_configuration.host = project.facility.onedata_provider_url
    oneprovider_configuration.api_key['X-Auth-Token'] = project.facility.onedata_token
    error = None

    file_op_api = FileOperationsApi(oneprovider_configuration)
    space_api = SpaceApi(oneprovider_configuration=oneprovider_configuration)

    space_id = project.onedata_space_id
    
    space_request = SpaceRequest(space_id=space_id)
    space = space_api.get_space(space_request)
    
    file_id = file_op_api.get_root(space).root_dir.file_id

    parent_er = EntryRequest(file_id=file_id)
    new_file = None
    try:
        dir_request = NewDirectoryRequest(parent=parent_er, name=dataset_name)
        newfile_entry_request = file_op_api.new_entry(dir_request)
        new_file = file_op_api.get_file(newfile_entry_request, FA_ALL)
    except Exception as e:
        error = {"error": f"Failed to create the dataset. {e}"}

        
    return new_file, error


def rename_entry(project: Project, file_entry_id: str, new_name: str):
    oneprovider_configuration = oneprovider_client.configuration.Configuration()
    oneprovider_configuration.host = project.facility.onedata_provider_url
    oneprovider_configuration.api_key['X-Auth-Token'] = project.facility.onedata_token

    path = None
    try:
        url = f"{oneprovider_configuration.host}/data/{file_entry_id}"
        headers = {
            "X-Auth-Token": oneprovider_configuration.api_key['X-Auth-Token'],
            "Content-Type": "application/json"
        }
        data = {
            "attributes": ["path"]
        }
        response = requests.get(url, headers=headers, json=data)
        if response.status_code == 200:
            path = response.json().get("path")
    except Exception as e:
        return {"error": f"Failed to get path for the directory {file_entry_id}. {e}"}

    try:
        print(f"Rename directory", flush=True)

        from_path = path
        to_path = path.replace(path.split("/")[-1], new_name) # TODO: May replace more than one occurence

        cdmi_url = project.facility.onedata_provider_url.replace("/api/v3/oneprovider", "/cdmi") # TODO: not sure if this is ideal
        url = f"{cdmi_url}{to_path}"
        headers = {
            "X-Auth-Token": oneprovider_configuration.api_key['X-Auth-Token'],
            "Content-Type": "application/cdmi-object",
            "X-CDMI-Specification-Version": "1.1.1"
        }
        data = {
            "move": from_path
        }
        print(f"PUT {url} {headers} {data}", flush=True)
        response = requests.put(url, headers=headers, json=data) 
        print(response.status_code, response.text, flush=True)  
    except Exception as e:
        print(f"Failed to rename directory. {e} {response.text}", flush=True)
        return {"error": f"Failed to rename directory. {e} {response.text}"}


def create_new_experiment(dataset: Dataset, experiment_id: str):
    oneprovider_configuration = oneprovider_client.configuration.Configuration()
    oneprovider_configuration.host = dataset.project.facility.onedata_provider_url
    oneprovider_configuration.api_key['X-Auth-Token'] = dataset.project.facility.onedata_token
    error = None

    file_op_api = FileOperationsApi(oneprovider_configuration)

    parent_er = EntryRequest(file_id=dataset.onedata_file_id)
    new_file = None
    try:
        dir_request = NewDirectoryRequest(parent=parent_er, name=experiment_id)
        newfile_entry_request = file_op_api.new_entry(dir_request)
        new_file = file_op_api.get_file(newfile_entry_request, FA_ALL)
    except Exception as e:
        error = {"error": f"Failed to create the dataset. {e}"}

    try:
        print(f"Setting permissions for the experiment {experiment_id} to 0645", flush=True)
        url = f"{oneprovider_configuration.host}/data/{new_file.file_id}"
        headers = {
            "X-Auth-Token": oneprovider_configuration.api_key['X-Auth-Token'],
            "Content-Type": "application/json"
        }
        data = {
            "mode": "0645"
        }
        print(f"PUT {url} {headers} {data}", flush=True)
        response = requests.put(url, headers=headers, json=data)
    except Exception as e:
        error = {"error": f"Failed to set permissions for the dataset. {e} {response.text}"}
        print(f"Failed to set permissions for the dataset. {e} {response.text}", flush=True)

    return new_file, error


def create_new_temp_token(facility: Facility, project: Project, dataset: Dataset):
    oneprovider_configuration = oneprovider_client.configuration.Configuration()
    oneprovider_configuration.host = facility.onedata_provider_url
    oneprovider_configuration.api_key['X-Auth-Token'] = facility.onedata_token
    error = None
    token = None
    try:
        print(f"Create temp token", flush=True)
        #TODO: configurable url
        url = f"https://onezone.devel.onedata.e-infra.cz/api/v3/onezone/user/tokens/temporary"
        headers = {
            "X-Auth-Token": facility.onedata_token,
            "Content-Type": "application/json"
        }
        data = {
            "accessToken": {},
            "caveats": [
                {
                    "type": "time",
                    "validUntil": int((datetime.now(timezone.utc) + timedelta(hours=5)).timestamp())
                },
                {
                    "type": "data.path",
                    "whitelist": [
                        base64.b64encode(f"/{project.onedata_space_id}/{dataset.name}".encode("ascii")).decode("ascii")
                    ]
                }
            ]
        }
        print(f"POST {url} {headers} {data}", flush=True)
        response = requests.post(url, headers=headers, json=data)
        print(response.status_code, response.text, flush=True)
        if response.status_code == 201:
            token = response.json().get("token")
    except Exception as e:
        error = {"error": f"Failed to set permissions for the dataset. {e} {response.text}"}
        print(f"Failed to set permissions for the dataset. {e} {response.text}", flush=True)

    return token, error


def get_file_metadata(project: Project, file_id: str):
    oneprovider_configuration = oneprovider_client.configuration.Configuration()
    oneprovider_configuration.host = project.facility.onedata_provider_url
    oneprovider_configuration.api_key['X-Auth-Token'] = project.facility.onedata_token
    error = None
    metadata = None

    try:
        file_op_api = FileOperationsApi(oneprovider_configuration)
        metadata = file_op_api.get_file(EntryRequest(file_id), FA_ALL)
    except Exception as e:
        error = {"error": f"Failed to create the dataset. {e}"}

    return metadata, error
