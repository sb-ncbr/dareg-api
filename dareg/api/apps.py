
from django.apps import AppConfig
from job_engine.job_engine import JobEngine
import sys
import threading
import time



class ApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "api"

    def ready(self):
        from django.conf import settings

        job_loop_interval = getattr(settings, "JOB_LOOP_INTERVAL", 60)
        # never reconcile real Onedata from a test run (it could create real groups from test data)
        onedata_sync_allowed = sys.argv[1:2] != ["test"]

        def job_loop():
            from django.db import connections
            engine = JobEngine()
            recovery_interval = getattr(settings, "JOB_RECOVERY_INTERVAL", 5)  # Run recovery every 5 cycles by default
            cycle_count = 0
            onedata_cycle_count = 0

            while True:
                try:
                    # Close all old connections before each iteration
                    for conn in connections.all():
                        conn.close_if_unusable_or_obsolete()

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

                # Onedata groups/ACLs reconciler, independent of the job engine
                if settings.ONEDATA_SYNC_ENABLED and onedata_sync_allowed:
                    onedata_cycle_count += 1
                    if onedata_cycle_count >= settings.ONEDATA_SYNC_EVERY_N_CYCLES:
                        onedata_cycle_count = 0
                        try:
                            from onedata_api.sync import sync_onedata
                            sync_onedata()
                        except Exception as e:
                            print(f"Exception in Onedata sync: {e}", flush=True)
                time.sleep(job_loop_interval)

        t = threading.Thread(target=job_loop, daemon=True)
        t.start()
