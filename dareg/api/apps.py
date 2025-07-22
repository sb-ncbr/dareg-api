from django.apps import AppConfig
from job_engine.job_engine import JobEngine
import threading
import time

class ApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "api"

    def ready(self):
        def job_loop():
            engine = JobEngine()
            while True:
                engine.run()
                time.sleep(60)  # 5 minutes

        t = threading.Thread(target=job_loop, daemon=True)
        t.start()
