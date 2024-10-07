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
from api.models import Project, Dataset

def create_new_dataset(collection_id, dataset_name):
    oneprovider_configuration = oneprovider_client.configuration.Configuration()
    file_op_api = FileOperationsApi(oneprovider_configuration)
    space_api = SpaceApi(oneprovider_configuration=oneprovider_configuration)
    share_api = ShareApi(oneprovider_configuration)

    project = Project.objects.get(id=collection_id)
    space_id = project.onedata_space_id

    facility_token = project.facility.onedata_token
    if facility_token is None or facility_token == "":
        return {"error": "Dataset doesn't have any supported space. Please contact the administrator of DAREG."}
    
    oneprovider_configuration.host = project.facility.onedata_provider_url
    oneprovider_configuration.api_key['X-Auth-Token'] = facility_token

    space_request = SpaceRequest(space_id=space_id)
    space = space_api.get_space(space_request)
    
    file_id = file_op_api.get_root(space).root_dir.file_id

    parent_er = EntryRequest(file_id=file_id)

    dir_request = NewDirectoryRequest(parent=parent_er, name=dataset_name)
    newfile_entry_request = file_op_api.new_entry(dir_request)
    new_file = file_op_api.get_file(newfile_entry_request, FA_ALL)

    if new_file.file_id is None:
        return {"error": "Failed to create the dataset. Please contact the administrator of DAREG."}
        
    try:
        print(f"Setting permissions for the dataset {dataset_name} to 0645", flush=True)
        url = f"{oneprovider_configuration.host}/data/{new_file.file_id}"
        headers = {
            "X-Auth-Token": facility_token,
            "Content-Type": "application/json"
        }
        data = {
            "mode": "0645"
        }
        print(f"PUT {url} {headers} {data}", flush=True)
        response = requests.put(url, headers=headers, json=data)   
        print(response.status_code, flush=True)
    except Exception as e:
        print(f"Failed to set permissions for the dataset. {e}", flush=True)

    share = NewShareRequest(entry=new_file, name=f"Default share for {dataset_name}", description="Default share for dataset")
    new_share = share_api.new_share(share)

    if new_share.share_id is None:
        return {"error": "Failed to create the share for the dataset. Please contact the administrator of DAREG."}

    return new_file, new_share

def download_file(file_id):
    pass

def create_preshare(collection_id, dataset_name):
    pass