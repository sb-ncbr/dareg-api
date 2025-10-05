# Write a code that wakes up every minute, lists all jobs that are not running and submits them
import logging
from django.conf import settings


# Module-level constant for default job engine limits
JOB_ENGINE_SUBMIT_LIMIT: int = 20
JOB_ENGINE_POLL_LIMIT: int = 20
JOB_ENGINE_RECOVERY_LIMIT: int = 10
JOB_ENGINE_RECOVERY_TIMEOUT_MINUTES: int = 5

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
        jobs = Job.objects.filter(status=JobStatus.NEW, claimed=False)[:max_jobs]
        for job in jobs:
            # Try to claim the job atomically
            if not job.claim_job():
                self.logger.info(f"Job {job.id} already claimed by another worker, skipping")
                continue

            try:
                self.logger.info(f"Claimed and sending job {job.id} for processing (attempt {job.job_submission_counter + 1})")
                # Increment submission counter before attempting to send
                job.job_submission_counter += 1
                job.save(update_fields=['job_submission_counter'])

                send_job(job)
                self.logger.info(f"Job with ID {job.id} was submitted successfully")
                # Job will be unclaimed when it transitions to ASSIGNED status in send_job
            except Exception as e:
                self.logger.error(f"Error processing job {job.id} (attempt {job.job_submission_counter}): {e}")

                # Check if this was the third failed attempt
                if job.job_submission_counter >= 3:
                    self.logger.error(f"Job {job.id} failed 3 times, setting status to SUBMISSION_ERROR")
                    job.set_status(JobStatus.SUBMISSION_ERROR)
                    job.unclaim_job()  # Release claim on final failure
                else:
                    job.unclaim_job()  # Release claim so job can be retried
                    self.logger.info(f"Job {job.id} will be retried. Attempts: {job.job_submission_counter}/3")
        self.logger.info("JobEngine finished scheduling.")


    def poll(self):
        from api.models import Job, JobStatus
        from onedata_api.middleware import get_job_status
        self.logger.info("Fetching job statuses")
        max_jobs = getattr(settings, "JOB_ENGINE_POLL_LIMIT", JOB_ENGINE_POLL_LIMIT)
        jobs = Job.objects.filter(status__in=[JobStatus.RUNNING, JobStatus.ASSIGNED], claimed=False).order_by('created')[:max_jobs]
        for job in jobs:
            # Try to claim the job atomically for polling
            if not job.claim_job():
                self.logger.info(f"Job {job.id} already claimed by another worker for polling, skipping")
                continue

            old_status = job.status
            try:
                self.logger.info(f"Claimed and polling job {job.id} status (polling attempt {job.job_polling_counter + 1})")

                # Call get_job_status which may raise an exception
                get_job_status(job)

                # If successful, reset polling counter
                if job.job_polling_counter > 0:
                    job.job_polling_counter = 0
                    job.save(update_fields=['job_polling_counter'])

                # Release claim after successful polling
                job.unclaim_job()
                self.logger.info(f"Job ID: {job.id}, OldStatus: {old_status}, NewStatus: {job.status}")

            except Exception as e:
                self.logger.error(f"Error polling job {job.id} status: {e}")

                # Increment polling counter
                job.job_polling_counter += 1

                # Check if this was the third failed polling attempt
                if job.job_polling_counter >= 3:
                    self.logger.error(f"Job {job.id} polling failed 3 times, setting status to POLLING_ERROR")
                    job.set_status(JobStatus.POLLING_ERROR)
                    job.unclaim_job()  # Release claim on final polling failure
                else:
                    # Save the incremented counter but keep current status for retry
                    job.save(update_fields=['job_polling_counter'])
                    job.unclaim_job()  # Release claim so job can be polled again
                    self.logger.info(f"Job {job.id} polling will be retried. Failed attempts: {job.job_polling_counter}/3")

        self.logger.info("JobEngine finished polling.")

    def recover(self):
        """
        Recovery cycle to handle jobs stuck in ASSIGNING state.

        Jobs stuck in ASSIGNING state for more than 5 minutes are recovered by:
        - If job has execution_id: move to ASSIGNED status
        - If job has no execution_id: move back to NEW status for retry
        """
        from api.models import Job, JobStatus
        from django.utils import timezone
        from datetime import timedelta

        self.logger.info("JobEngine started recovery cycle")

        # Calculate timeout threshold
        timeout_minutes = getattr(settings, "JOB_ENGINE_RECOVERY_TIMEOUT_MINUTES", JOB_ENGINE_RECOVERY_TIMEOUT_MINUTES)
        timeout_threshold = timezone.now() - timedelta(minutes=timeout_minutes)

        max_jobs = getattr(settings, "JOB_ENGINE_RECOVERY_LIMIT", JOB_ENGINE_RECOVERY_LIMIT)

        # Find jobs stuck in ASSIGNING state for more than timeout_minutes
        stuck_jobs = Job.objects.filter(
            status=JobStatus.ASSIGNING,
            claimed=False,  # Only process unclaimed jobs
            modified__lt=timeout_threshold  # Modified more than timeout_minutes ago
        ).order_by('modified')[:max_jobs]

        if stuck_jobs.exists():
            self.logger.info(f"Found {stuck_jobs.count()} jobs stuck in ASSIGNING state for recovery")

        for job in stuck_jobs:
            # Try to claim the job atomically for recovery
            if not job.claim_job():
                self.logger.info(f"Job {job.id} already claimed by another worker for recovery, skipping")
                continue

            try:
                minutes_stuck = (timezone.now() - job.modified).total_seconds() / 60
                self.logger.info(f"Recovering job {job.id} stuck in ASSIGNING for {minutes_stuck:.1f} minutes")

                if job.onedata_workflow_execution_id:
                    # Job has execution ID, likely submitted successfully but status not updated
                    self.logger.info(f"Job {job.id} has execution ID {job.onedata_workflow_execution_id}, moving to ASSIGNED")
                    job.set_status(JobStatus.ASSIGNED)
                else:
                    # Job has no execution ID, submission likely failed, retry
                    self.logger.info(f"Job {job.id} has no execution ID, moving back to NEW for retry")
                    job.set_status(JobStatus.NEW)

                # Release claim after recovery
                job.unclaim_job()
                self.logger.info(f"Job {job.id} recovered successfully")

            except Exception as e:
                self.logger.error(f"Error recovering job {job.id}: {e}")
                # Release claim on error
                job.unclaim_job()

        self.logger.info("JobEngine finished recovery cycle")