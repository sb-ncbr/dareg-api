
from django.apps import AppConfig
from job_engine.job_engine import JobEngine
import threading
import time



class ApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "api"

    def ready(self):
        from django.conf import settings

        job_loop_interval = getattr(settings, "JOB_LOOP_INTERVAL", 60)

        def job_loop():
            engine = JobEngine()
            recovery_interval = getattr(settings, "JOB_RECOVERY_INTERVAL", 5)  # Run recovery every 5 cycles by default
            cycle_count = 0

            while True:
                try:
                    engine.schedule()
                    engine.poll()

                    # Run recovery cycle less frequently
                    cycle_count += 1
                    if cycle_count >= recovery_interval:
                        engine.recover()
                        cycle_count = 0

                except Exception as e:
                    # This will catch any exception in schedule, poll, or recover and keep the loop running
                    print(f"Exception in job loop: {e}", flush=True)
                time.sleep(job_loop_interval)

        t = threading.Thread(target=job_loop, daemon=True)
        t.start()
