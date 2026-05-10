from celery import Celery

from shared.settings import get_settings

settings = get_settings()

# Celery is configured centrally so task execution stays environment-driven and process-safe.
celery_app = Celery(
    "mega_ai",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)
celery_app.conf.update(
    task_track_started=True,
    enable_utc=True,
    timezone="UTC",
)
