import logging
from onedata_api.middleware import create_new_dataset, create_public_share, establish_dataset, rename_entry, \
    create_new_experiment, create_new_temp_token, get_file_metadata, verify_workflow_existence


from .models import Job, JobParams, JobStatus, Project
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
    logger.info(f"{metadata}")

    logger.info(f"Verifying output file existence - needs to be folder: {output_file}")
    metadata, error = get_file_metadata(project, output_file)
    if error:
        raise ValueError(f"Input file verification failed: {error}")
    logger.info(f"{metadata}")

def send_job(job: Job):
    logger.info("Sending job for processing...")
    project = job.workflow_temaplate_id.project_id
    oneprovider_configuration = oneprovider_client.configuration.Configuration()
    oneprovider_configuration.host = project.facility.onedata_provider_url
    oneprovider_configuration.api_key['X-Auth-Token'] = project.facility.onedata_token
    workflow_client = oneprovider_client.WorkflowExecutionApi(oneprovider_client.ApiClient(oneprovider_configuration))

    body = {
        "spaceId": "5eb4f6fdceda76b4c96e02faf7f533acch3af6",
        "atmWorkflowSchemaId": "4a06a83aab017c8f19de25b5dd03c9dbch0b6e",
        "atmWorkflowSchemaRevisionNumber": 1,
        "storeInitialContentOverlay": {
            "096edc876eac03b4872efc92af21138fd2ae3c": [
                {
                    "fileId": "000000000052642E67756964233864323436373633656563626138336330393239306164623662613735653563636835373935233565623466366664636564613736623463393665303266616637663533336163636833616636"
                }
            ],
            "697b068490e687abed7023713298b76e7a1423": ["lol"]
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
    import requests
    project = job.workflow_temaplate_id.project_id
    provider_url = project.facility.onedata_provider_url.rstrip('/')
    token = project.facility.onedata_token
    execution_id = job.workflow_execution_id
    url = f"{provider_url}/api/v3/oneprovider/automation/execution/workflows/{execution_id}"
    headers = {"X-Auth-Token": token}

    logger.info(f"Polling workflow execution for job: {job.id}, execution ID: {execution_id} via direct HTTP request")
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        logger.info("Workflow received successfully.")
        data = response.json()
        status = data.get("status")
        if status == "finished":
            logger.info(f"Job {job.id} finished successfully.")
            job.set_status(JobStatus.SUCCESS)
        elif status != "active":
            logger.info(f"Job {job.id} finished with failure.")
            job.set_status(JobStatus.FAILURE)
    except Exception as e:
        logger.error(f"Failed to poll workflow execution: {e}")
        # TODO: handle properly
