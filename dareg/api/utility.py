import json
import logging
import requests
from onedata_api.middleware import create_new_dataset, create_public_share, establish_dataset, rename_entry, \
    create_new_experiment, create_new_temp_token, get_file_metadata, verify_workflow_existence


from .models import Job, JobParams, JobStatus, Project, WorkflowTemplate
import oneprovider_client

logger = logging.getLogger(__name__)

def verify_job(job: Job):
    # Deserialize input_params to JobParams
    logger.info("Verifying Job params...")
    try:
        job_params = JobParams.from_dict(job.input_params)
    except Exception as e:
        raise ValueError(f"Failed to deserialize input_params: {e}")
    
    input_file = job_params.inputFile
    output_file = job_params.outputFile

    logger.info(f"Verifying input file {input_file} existence - needs to be folder.")

    # get project corresponding to workflow template connected to job
    project_id = job.workflow_temaplate_id.project_id.id
    logger.info(f"Project ID: {project_id}")
    try:
        project = Project.objects.get(id=project_id)
    except Project.DoesNotExist:
        raise ValueError(f"Project with id {project_id} does not exist.")
    logger.info(f"Project found: {project.name} (ID: {project.id})")

    metadata, error = get_file_metadata(project, input_file)
    if error:
        raise ValueError(f"Input file verification failed: {error}")
    else:
        logger.info(f"Input file metadata: {metadata}")
    logger.info(f"{metadata}")

    logger.info(f"Verifying output file existence - needs to be folder: {output_file}")
    metadata, error = get_file_metadata(project, output_file)
    if error:
        raise ValueError(f"Input file verification failed: {error}")
    else:
        logger.info(f"Output file metadata: {metadata}")
    logger.info(f"{metadata}")

def send_job(job: Job):
    logger.info("Sending job for processing...")
    project = job.workflow_temaplate_id.project_id
    oneprovider_configuration = oneprovider_client.configuration.Configuration()
    oneprovider_configuration.host = project.facility.onedata_provider_url
    oneprovider_configuration.api_key['X-Auth-Token'] = project.facility.onedata_token
    workflow_client = oneprovider_client.WorkflowExecutionApi(oneprovider_client.ApiClient(oneprovider_configuration))

    workflow_input_params_dict = json.loads(job.workflow_temaplate_id.input_params)
    job_input_params_dict = json.loads(job.input_params)
    body = {
        "spaceId": f"{job.workflow_temaplate_id.project_id.onedata_space_id}",
        "atmWorkflowSchemaId": f"{job.workflow_temaplate_id.workflow_id}",
        "atmWorkflowSchemaRevisionNumber": 1,
        "storeInitialContentOverlay": {
            f"{workflow_input_params_dict["inputFile"]}": [
                {
                    "fileId": f"{job_input_params_dict["inputFile"]}",
                }
            ],
            f"{workflow_input_params_dict["outputFile"]}": [f"{job_input_params_dict["outputFile"]}"]
        },
        "logLevel": "debug",
        "callback": "https://my-server.example.com/execution-callback"
    }

    logger.info(f"Creating workflow execution with body: {body}")
    # receipt the respone and get atmWorkflowExecutionId from response schema
    try:
        response = workflow_client.schedule_workflow_execution(body)
        logger.info(f"Workflow execution created successfully.")
        job.set_status(JobStatus.RUNNING)
        logger.info(f"Workflow execution ID: {response}")
        job.workflow_execution_id = response.atm_workflow_execution_id
        job.save() 
    except Exception as e:
        logger.error(f"Failed to create workflow execution: {e}")
        raise

def get_job_status(job: Job):


    logger.info(f"Getting status for job with id {job.workflow_execution_id}")
    project = job.workflow_temaplate_id.project_id

    # TODO: this code will be used once we use onedata client for workflow exectuion details
    # oneprovider_configuration = oneprovider_client.configuration.Configuration()
    # oneprovider_configuration.host = project.facility.onedata_provider_url
    # oneprovider_configuration.api_key['X-Auth-Token'] = project.facility.onedata_token
    # workflow_client = oneprovider_client.WorkflowExecutionApi(oneprovider_client.ApiClient(oneprovider_configuration))

    logger.info(f"Polling workflow execution for job: {job.id}, execution ID: {job.workflow_execution_id}")
    # TODO: Use workflow_client.get_workflow_execution_details instead
    status = fetch_workflow_status_via_http(project, job.workflow_execution_id)
    if status:
        logger.info("Workflow received successfully.")
        if status == "finished":
            logger.info(f"Job {job.id} finished successfully.")
            job.set_status(JobStatus.SUCCESS)
        elif status != "active":
            logger.info(f"Job {job.id} finished with failure.")
            job.set_status(JobStatus.FAILURE)
        else:
            logger.info(f"Job {job.id} has status {status}.")
    else:
        logger.error(f"Failed to poll workflow execution: status not available.")
        # TODO: handle properly

    # TODO: Drop this function once library fix is introduced

def fetch_workflow_status_via_http(project, workflow_execution_id):
    provider_url = project.facility.onedata_provider_url
    token = project.facility.onedata_token
    url = f"{provider_url}/automation/execution/workflows/{workflow_execution_id}"
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
    logger.info(f"Verifying workflow with id {workflow.workflow_id} exists in onedata")
    oneprovider_configuration = oneprovider_client.configuration.Configuration()
    oneprovider_configuration.host = workflow.project_id.facility.onedata_provider_url
    oneprovider_configuration.api_key['X-Auth-Token'] = workflow.project_id.facility.onedata_token
    workflow_client = oneprovider_client.WorkflowExecutionApi(oneprovider_client.ApiClient(oneprovider_configuration))
    
    try:
        # TODO: Verify that the workflow with this ID exists
        logger.info(f"Workflow with id {workflow.workflow_id} exists.")
        return True
    except Exception as e:
        logger.error(f"Workflow with id {workflow.workflow_id} does not exist: {e}")
        return False
    
def verify_workflow_template(workflow: WorkflowTemplate):
    logger.info(f"Verifying inputsTemplate for workflow with id {workflow.workflow_id} in onedata")
    assert workflow.input_params is not None, "'inputsTemplate' is missing in schema"
    required_keys = {"inputFile", "outputFile", "appConfig"}
    assert required_keys.issubset(workflow.input_params.keys()), \
        f"'inputsTemplate' must contain keys: {required_keys}"
    for key in required_keys:
        assert isinstance(workflow.input_params[key], str), f"{key} must be a string (store_id)"
    logger.info(f"InputsTemplate for workflow with id {workflow.workflow_id} is valid")
   