# Write a code that wakes up every minute, lists all jobs that are not running and submits them
import logging
from django.conf import settings


# Module-level constant for default job engine limit
JOB_ENGINE_SUBMIT_LIMIT: int = 20
JOB_ENGINE_POLL_LIMIT: int = 20

class JobEngine:

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.logger.info("JobEngine initialized")

    # Run this method every minute
    def schedule(self):
        from api.models import Job, JobStatus
        from api.utility import send_job, verify_job
        self.logger.info("JobEngine started running")
        max_jobs = getattr(settings, "JOB_ENGINE_SUBMIT_LIMIT", JOB_ENGINE_SUBMIT_LIMIT)
        jobs = Job.objects.filter(status=JobStatus.NEW)[:max_jobs]
        for job in jobs:
            try:
                self.logger.info(f"Verifying job {job.id}")
                verify_job(job)
                self.logger.info(f"Sending job {job.id} for processing")
                send_job(job)
                self.logger.info(f"Job with ID {job.id} was submitted")
            except Exception as e:
                self.logger.error(f"Error processing job {job.id}: {e}")
        self.logger.info("JobEngine finished scheduling.")


    def poll(self):
        from api.models import Job, JobStatus
        from api.utility import get_job_status
        self.logger.info("Fetching job statuses")
        max_jobs = getattr(settings, "JOB_ENGINE_POLL_LIMIT", JOB_ENGINE_POLL_LIMIT)
        jobs = Job.objects.all().order_by('created')[:max_jobs]
        for job in jobs:
            status = job.status
            get_job_status(job)
            self.logger.info(f"Job ID: {job.id}, OldStatus: {status}, NewStatus: {job.status}")
        self.logger.info("JobEngine finished polling.")