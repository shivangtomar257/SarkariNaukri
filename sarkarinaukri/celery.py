import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sarkarinaukri.settings")
app = Celery("sarkarinaukri")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
app.conf.beat_schedule = {
    "scan-official-sources-every-4-hours": {"task": "portal.tasks.scan_official_sources", "schedule": crontab(minute=12, hour="*/4")},
    "scan-discovery-sources-every-6-hours": {"task": "portal.tasks.scan_discovery_sources", "schedule": crontab(minute=27, hour="*/6")},
    "ai-web-discovery-every-6-hours": {"task": "portal.tasks.ai_web_discovery", "schedule": crontab(minute=7, hour="*/6")},
    "reconcile-signals-hourly": {"task": "portal.tasks.reconcile_discovery_signals", "schedule": crontab(minute=42)},
    "instant-alerts-hourly": {"task": "portal.tasks.send_instant_job_alerts", "schedule": crontab(minute=18)},
    "important-change-alerts-hourly": {"task": "portal.tasks.send_change_alerts", "schedule": crontab(minute=48)},
    "deadline-alerts-every-6-hours": {"task": "portal.tasks.send_deadline_alerts", "schedule": crontab(minute=5, hour="*/6")},
    "daily-digest-evening": {"task": "portal.tasks.send_daily_job_digests", "schedule": crontab(minute=15, hour=19)},
    "expire-jobs-nightly": {"task": "portal.tasks.expire_jobs", "schedule": crontab(minute=5, hour=1)},
    "reverify-published-daily": {"task": "portal.tasks.reverify_recent_records", "schedule": crontab(minute=35, hour=2)},
    "rebuild-exam-calendar-nightly": {"task": "portal.tasks.rebuild_exam_calendar", "schedule": crontab(minute=10, hour=3)},
    "source-health-every-2-hours": {"task": "portal.tasks.check_source_health", "schedule": crontab(minute=50, hour="*/2")},
    "broken-links-every-6-hours": {"task": "portal.tasks.check_published_links", "schedule": crontab(minute=33, hour="*/6")},
    "google-indexing-every-2-hours": {"task": "portal.tasks.submit_recent_urls_to_indexing", "schedule": crontab(minute=25, hour="*/2")},
    "cleanup-history-weekly": {"task": "portal.tasks.cleanup_operational_history", "schedule": crontab(minute=30, hour=4, day_of_week="sun")},
}
