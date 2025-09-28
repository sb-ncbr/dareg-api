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
        from onedata_api.middleware import send_job
        self.logger.info("JobEngine started running")
        max_jobs = getattr(settings, "JOB_ENGINE_SUBMIT_LIMIT", JOB_ENGINE_SUBMIT_LIMIT)
        jobs = Job.objects.filter(status=JobStatus.NEW)[:max_jobs]
        for job in jobs:
            try:
                self.logger.info(f"Sending job {job.id} for processing (attempt {job.job_submission_counter + 1})")
                # Increment submission counter before attempting to send
                job.job_submission_counter += 1
                job.save(update_fields=['job_submission_counter'])

                send_job(job)
                self.logger.info(f"Job with ID {job.id} was submitted successfully")
            except Exception as e:
                self.logger.error(f"Error processing job {job.id} (attempt {job.job_submission_counter}): {e}")

                # Check if this was the third failed attempt
                if job.job_submission_counter >= 3:
                    self.logger.error(f"Job {job.id} failed 3 times, setting status to UNKNOWN_ERROR")
                    job.set_status(JobStatus.UNKNOWN_ERROR)
                else:
                    # Reset status to NEW for retry (if it was changed to ASSIGNING by send_job)
                    if job.status != JobStatus.NEW:
                        job.status = JobStatus.NEW
                        job.save(update_fields=['status'])
                    self.logger.info(f"Job {job.id} will be retried. Attempts: {job.job_submission_counter}/3")
        self.logger.info("JobEngine finished scheduling.")


    def poll(self):
        from api.models import Job, JobStatus
        from onedata_api.middleware import get_job_status
        self.logger.info("Fetching job statuses")
        max_jobs = getattr(settings, "JOB_ENGINE_POLL_LIMIT", JOB_ENGINE_POLL_LIMIT)
        jobs = Job.objects.filter(status__in=[JobStatus.RUNNING, JobStatus.ASSIGNED]).order_by('created')[:max_jobs]
        for job in jobs:
            status = job.status
            get_job_status(job)
            self.logger.info(f"Job ID: {job.id}, OldStatus: {status}, NewStatus: {job.status}")
        self.logger.info("JobEngine finished polling.")