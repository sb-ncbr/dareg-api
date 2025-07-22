# Write a code that wakes up every minute, lists all jobs that are not running and submits them
import logging
from django.conf import settings

class JobEngine:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.logger.info("JobEngine initialized")

    # Run this method every minute


    def run(self):
        from api.models import Job, JobStatus
        from api.utility import send_job, verify_job
        self.logger.info("JobEngine started running")
        jobs = Job.objects.filter(status=JobStatus['NEW'])
        for job in jobs:
            try:
                self.logger.info(f"Verifying job {job.id}")
                verify_job(job)
                self.logger.info(f"Sending job {job.id} for processing")
                send_job(job)
                self.logger.info(f"Job with ID {job.id} was submitted")
            except Exception as e:
                self.logger.error(f"Error processing job {job.id}: {e}")