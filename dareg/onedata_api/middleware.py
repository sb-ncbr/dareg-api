from datetime import datetime, timezone, timedelta
from http.client import responses
import json
import logging

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
from api.models import Job, JobParams, JobStatus, Project, Dataset, Facility, WorkflowTemplate, WorkflowParams
import base64

logger = logging.getLogger(__name__)

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
    logger.info(f"Url: {oneprovider_configuration.host}/data/{file_id}")
    logger.info(f"Token: {oneprovider_configuration.api_key['X-Auth-Token']}")
    try:
        file_op_api = FileOperationsApi(oneprovider_configuration)
        # metadata = file_op_api.get_file(EntryRequest(file_id), FA_ALL)
    except Exception as e:
        error = {"error": f"Failed to create the dataset. {e}"}

    return metadata, error

def verify_job(job: Job):
    """
    Verify job runtime requirements (external resources).
    Note: app_config validation is done in Job.clean() method.
    """
    logger.info("Verifying Job runtime requirements...")

    # Get the project from the job using the centralized method
    project = job.get_project()
    logger.info(f"Project: {project}")

    # Verify output_resource_object only if it's provided
    if job.output_resource_object:
        if not hasattr(job.output_resource_object, 'onedata_file_id'):
            raise ValueError(f"Output resource {job.output_resource_object.__class__.__name__} does not have onedata_file_id")

        output_file_id = job.output_resource_object.onedata_file_id
        logger.info(f"Verifying output file existence - needs to be folder: {output_file_id}")
        metadata, error = get_file_metadata(project, output_file_id)
        if error:
            raise ValueError(f"Output file validation failed: {error}")
        else:
            logger.info(f"Output file metadata: {metadata}")

    logger.info("Job runtime requirements verified successfully.")

def send_job(job: Job):
    logger.info("Sending job for processing...")

    # Get the project from the job using the centralized method
    project = job.get_project()
    logger.info(f"Creating workflow execution project: {project}")
    oneprovider_configuration = oneprovider_client.configuration.Configuration()
    oneprovider_configuration.host = project.facility.onedata_provider_url
    logger.info(f"Creating workflow execution host: {oneprovider_configuration.host}")
    oneprovider_configuration.api_key['X-Auth-Token'] = project.facility.onedata_token
    logger.info(f"Creating workflow execution api key: {oneprovider_configuration.api_key['X-Auth-Token'] }")
    workflow_client = oneprovider_client.WorkflowExecutionApi(oneprovider_client.ApiClient(oneprovider_configuration))

    # Parse appConfig from workflow template and job, merge with job taking precedence
    workflow_app_config = json.loads(job.workflow_template.input_params['appConfig'])
    # job.app_config is now directly the dict (no nested 'appConfig' key)
    job_app_config = job.app_config

    # Merge appConfigs with job appConfig taking precedence
    merged_app_config = {**workflow_app_config, **job_app_config}

    # Extract storeId from workflow template appConfig (not from merged)
    store_id = workflow_app_config['storeId']

    # Remove storeId from merged config as it's used as the store key
    store_config = {k: v for k, v in merged_app_config.items() if k != 'storeId'}

    # Determine input file ID
    input_file_id = job.root_resource_object.onedata_space_id if hasattr(job.root_resource_object, 'onedata_space_id') and not hasattr(job.root_resource_object, 'onedata_file_id') else job.root_resource_object.onedata_file_id

    # Determine output file ID - use output resource if provided, otherwise use input file ID
    output_file_id = job.output_resource_object.onedata_file_id if job.output_resource_object else input_file_id

    body = {
        "spaceId": f"{project.onedata_space_id}",
        "atmWorkflowSchemaId": f"{job.workflow_template.onedata_workflow_id}",
        "atmWorkflowSchemaRevisionNumber": int(job.workflow_template.revision),
        "storeInitialContentOverlay": {
            f"{job.workflow_template.input_params['onedataInputStore']}": {
                "fileId": f"{input_file_id}"
            },
            f"{job.workflow_template.input_params['onedataOutputStore']}": {
                "fileId": f"{output_file_id}"
            },
            f"{store_id}": store_config
        },
        "logLevel": "debug"
    }

    logger.info(f"Creating workflow execution with body: {json.dumps(body, indent=2)}")

    # Set job status to assigning before sending to OneData
    job.set_status(JobStatus.ASSIGNING)
    logger.info(f"Job status set to ASSIGNING")

    # receipt the respone and get atmWorkflowExecutionId from response schema
    try:
        response = workflow_client.schedule_workflow_execution(body)
        logger.info(f"Workflow execution created successfully.")

        # Set job status to assigned and store execution ID when OneData responds successfully
        job.onedata_workflow_execution_id = response.atm_workflow_execution_id
        job.set_status(JobStatus.ASSIGNED)
        job.unclaim_job()  # Release claim now that job is successfully submitted
        job.save()
        logger.info(f"Job status set to ASSIGNED with execution ID: {response.atm_workflow_execution_id}") 
    except Exception as e:
        logger.error(f"Failed to create workflow execution: {e}")
        job.set_status(JobStatus.NEW)
        job.unclaim_job()  # Release claim now that job is successfully submitted
        job.save()
        raise

def get_job_status(job: Job):
    logger.info(f"Getting status for job with id {job.id}")

    # Get the project from the job using the centralized method
    project = job.get_project()

    # TODO: this code will be used once we use onedata client for workflow exectuion details
    # oneprovider_configuration = oneprovider_client.configuration.Configuration()
    # oneprovider_configuration.host = project.facility.onedata_provider_url
    # oneprovider_configuration.api_key['X-Auth-Token'] = project.facility.onedata_token
    # workflow_client = oneprovider_client.WorkflowExecutionApi(oneprovider_client.ApiClient(oneprovider_configuration))

    logger.info(f"Polling workflow execution for job: {job.id}, execution ID: {job.onedata_workflow_execution_id}")
    # TODO: Use workflow_client.get_workflow_execution_details instead
    status = fetch_workflow_status_via_http(project, job.onedata_workflow_execution_id)
    if status:
        logger.info("Workflow received successfully.")
        if status == "finished":
            logger.info(f"Job {job.id} finished successfully.")
            job.set_status(JobStatus.SUCCESS)
            # Unclaim job since it reached final state
            if job.claimed:
                job.unclaim_job()
        elif status != "finished" and status != "active":
            logger.info(f"Job {job.id} finished with failure.")
            job.set_status(JobStatus.FAILURE)
            # Unclaim job since it reached final state
            if job.claimed:
                job.unclaim_job()
        elif status == "active":
            logger.info(f"Job {job.id} is still running.")
            job.set_status(JobStatus.RUNNING)
        else:
            logger.info(f"Job {job.id} has status {status}.")
    else:
        logger.error(f"Failed to poll workflow execution: status not available.")
        # Raise exception to trigger polling failure counter logic
        raise Exception("Failed to poll workflow execution: status not available")

# TODO: Drop this function once library fix is introduced
def fetch_workflow_status_via_http(project, onedata_workflow_execution_id):
    provider_url = project.facility.onedata_provider_url
    token = project.facility.onedata_token
    url = f"{provider_url}/automation/execution/workflows/{onedata_workflow_execution_id}"
    headers = {
        "X-Auth-Token": token,
        "Accept": "application/json"
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data.get("status")
    except Exception as e:
        logger.error(f"Failed to fetch workflow status via HTTP: {e}")
        return None
    
def verify_workflow_existence(workflow: WorkflowTemplate):
    """
    Verify that the workflow with the given ID exists in the Oneprovider.
    """
    logger.info(f"Verifying workflow with id {workflow.onedata_workflow_id} exists in onedata")

    # Get any project that supports this workflow template
    # projects = workflow.supported_projects.all()
    # if not projects.exists():
    #     raise ValueError("No projects support this workflow template")

    # project = projects.first()

    # oneprovider_configuration = oneprovider_client.configuration.Configuration()
    # oneprovider_configuration.host = project.facility.onedata_provider_url
    # oneprovider_configuration.api_key['X-Auth-Token'] = project.facility.onedata_token
    # workflow_client = oneprovider_client.WorkflowExecutionApi(oneprovider_client.ApiClient(oneprovider_configuration))
    
    try:
        # TODO: Verify that the workflow with this ID exists
        logger.info(f"Workflow with id {workflow.onedata_workflow_id} exists.")
        return True
    except Exception as e:
        logger.error(f"Workflow with id {workflow.onedata_workflow_id} does not exist: {e}")
        return False
    
def verify_workflow_template(workflow: WorkflowTemplate):
    logger.info(f"Verifying inputsTemplate for workflow with id {workflow.onedata_workflow_id} in onedata")
    assert workflow.input_params is not None, "'inputsTemplate' is missing in schema"
    try:
        workflow_params = WorkflowParams.from_dict(workflow.input_params)
        logger.info(f"InputsTemplate for workflow with id {workflow.onedata_workflow_id} is valid")
    except Exception as e:
        raise ValueError(f"Failed to validate workflow input_params: {e}")

    # TODO: Verify that workflow stores exist