from __future__ import annotations

from datetime import timedelta
import time

import httpx
from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.db.models import Q
from django.utils import timezone

from .indexing import notify_google
from .models import (
    Source,
    DiscoverySignal,
    Job,
    SourceDocument,
    AlertSubscription,
    AnalyticsEvent,
    LinkCheck,
    SourceHealthCheck,
    WebPushSubscription,
    NotificationDelivery,
    ChangeEvent,
)
from .notifications import job_matches_subscription, send_job_email, send_web_push, absolute_job_url, unsubscribe_token
from .pipeline.locks import redis_lock
from .pipeline.scan import scan_source
from .pipeline.resolver import reconcile_signal
from .pipeline.publisher import upsert_job, sync_exam_events
from .pipeline.web_discovery import discover_and_ingest


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def scan_official_sources(self):
    with redis_lock("official-scan", 3600) as acquired:
        if not acquired:
            return {"skipped": "already running"}
        ids = []
        for source in Source.objects.filter(enabled=True, source_type="official"):
            ids.append(scan_source(source).id)
        return {"runs": ids}


@shared_task
def scan_discovery_sources():
    if not settings.ENABLE_COMPETITOR_DISCOVERY:
        return {"skipped": "disabled by policy setting"}
    with redis_lock("discovery-scan", 3600) as acquired:
        if not acquired:
            return {"skipped": "already running"}
        return {"runs": [scan_source(s).id for s in Source.objects.filter(enabled=True, source_type="discovery")]}


@shared_task
def reconcile_discovery_signals():
    resolved = 0
    for signal in DiscoverySignal.objects.filter(status="new")[:200]:
        doc, score = reconcile_signal(signal)
        if doc:
            upsert_job(doc, discovered_via=signal.source.name, discovery_url=signal.external_url)
            resolved += 1
    return {"resolved": resolved}


@shared_task
def expire_jobs():
    today = timezone.localdate()
    expiring = list(Job.objects.filter(status="published", application_end_date__lt=today))
    n = Job.objects.filter(pk__in=[j.pk for j in expiring]).update(status="expired") if expiring else 0
    if settings.GOOGLE_INDEXING_ENABLED:
        for job in expiring[:200]:
            if job.official_apply_url:
                notify_google(f"{settings.SITE_URL}{job.get_absolute_url()}", "URL_UPDATED")
    return {"expired": n}


@shared_task
def reverify_recent_records():
    n = 0
    for job in Job.objects.filter(status__in=["published", "review"]).order_by("verified_at")[:250]:
        try:
            doc = SourceDocument.objects.get(url=job.source_url)
            upsert_job(doc, job.discovered_via, job.discovery_url)
            n += 1
        except SourceDocument.DoesNotExist:
            pass
    return {"reverified": n}


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 2})
def ai_web_discovery(self):
    with redis_lock("ai-web-discovery", 2400) as acquired:
        if not acquired:
            return {"skipped": "already running"}
        return discover_and_ingest()


@shared_task
def rebuild_exam_calendar():
    count = 0
    for job in Job.objects.filter(status__in=["published", "expired"])[:2000]:
        sync_exam_events(job)
        count += 1
    return {"jobs_synced": count}


@shared_task
def check_source_health():
    created = 0
    with httpx.Client(follow_redirects=True, timeout=25) as client:
        source_qs = Source.objects.filter(enabled=True)
        if not settings.ENABLE_COMPETITOR_DISCOVERY:
            source_qs = source_qs.filter(source_type="official")
        for source in source_qs:
            started = time.perf_counter()
            status = "fail"
            http_status = None
            message = ""
            try:
                r = client.get(source.entry_url, headers={"User-Agent": source.user_agent})
                http_status = r.status_code
                status = "ok" if 200 <= r.status_code < 400 else "warn" if r.status_code in {401, 403, 429} else "fail"
                message = f"HTTP {r.status_code}; {len(r.content)} bytes"
            except Exception as exc:
                message = str(exc)[:500]
            latency_ms = int((time.perf_counter() - started) * 1000)
            SourceHealthCheck.objects.create(
                source=source,
                status=status,
                http_status=http_status,
                latency_ms=latency_ms,
                message=message,
            )
            source.last_status = f"health:{status}"
            source.save(update_fields=["last_status", "updated_at"])
            created += 1
    return {"checks": created}


def _check_url(client: httpx.Client, url: str):
    if not url:
        return False, None, "missing"
    try:
        r = client.head(url, follow_redirects=True)
        if r.status_code in {400, 403, 405, 429}:
            r = client.get(url, follow_redirects=True, headers={"Range": "bytes=0-2048"})
        if 200 <= r.status_code < 400:
            return True, r.status_code, str(r.url)[:500]
        # Government portals often rate-limit/block automated checkers while the
        # same URL remains valid for a normal browser. Treat these as reachable
        # but automation-restricted so staff see a warning instead of a false
        # broken-link alarm.
        if r.status_code in {401, 403, 429}:
            return True, r.status_code, f"reachable; automated checker restricted ({r.status_code}) -> {str(r.url)[:380]}"
        return False, r.status_code, str(r.url)[:500]
    except Exception as exc:
        return False, None, str(exc)[:500]


@shared_task
def check_published_links():
    checked = 0
    with httpx.Client(timeout=25, headers={"User-Agent": "SarkariNaukriLinkChecker/1.0"}) as client:
        for job in Job.objects.filter(status="published").order_by("-updated_at")[:500]:
            for kind, url in (
                ("notification", job.official_notification_url),
                ("apply", job.official_apply_url),
                ("website", job.official_website_url),
            ):
                if not url:
                    continue
                ok, code, message = _check_url(client, url)
                LinkCheck.objects.create(job=job, url=url, kind=kind, ok=ok, http_status=code, message=message)
                checked += 1
    return {"checked": checked}


def _new_jobs_since(hours=26):
    return Job.objects.filter(status="published", published_at__gte=timezone.now() - timedelta(hours=hours)).order_by("-published_at")


@shared_task
def send_instant_job_alerts():
    sent = 0
    jobs = list(_new_jobs_since(2)[:200])
    if not jobs:
        return {"sent": 0}
    for sub in AlertSubscription.objects.filter(active=True, frequency="instant"):
        for job in jobs:
            if not job_matches_subscription(job, sub):
                continue
            if send_job_email(sub, job, "instant_new_job", "New government job"):
                sent += 1
            if sub.user_id:
                for push in WebPushSubscription.objects.filter(user_id=sub.user_id, active=True):
                    key = f"push:{push.pk}:{job.pk}:instant"
                    if send_web_push(push, "New SarkariNaukri match", job.title, absolute_job_url(job), key, job):
                        sent += 1
    return {"sent": sent}


@shared_task
def send_daily_job_digests():
    sent = 0
    now = timezone.now()
    for sub in AlertSubscription.objects.filter(active=True, frequency="daily"):
        since = sub.last_sent_at or (now - timedelta(hours=26))
        jobs = [j for j in Job.objects.filter(status="published", published_at__gte=since).order_by("-published_at")[:300] if job_matches_subscription(j, sub)]
        if not jobs:
            sub.last_sent_at = now
            sub.save(update_fields=["last_sent_at"])
            continue
        key = f"email:{sub.pk}:digest:{now.date().isoformat()}"
        if NotificationDelivery.objects.filter(dedupe_key=key).exists():
            continue
        lines = []
        for job in jobs[:25]:
            lines.append(f"• {job.title}\n  Last date: {job.application_end_date or 'See notice'}\n  {absolute_job_url(job)}")
        body = "Your SarkariNaukri daily matches:\n\n" + "\n\n".join(lines) + "\n\nAlways verify the official recruitment notification before applying." + f"\n\nUnsubscribe: {settings.SITE_URL}/alerts/unsubscribe/{unsubscribe_token(sub)}/"
        try:
            send_mail(f"SarkariNaukri daily alert — {len(jobs)} new match(es)", body, settings.DEFAULT_FROM_EMAIL, [sub.email])
            NotificationDelivery.objects.create(subscription=sub, channel="email", notification_type="daily_digest", dedupe_key=key, status="sent")
            sent += 1
        except Exception as exc:
            NotificationDelivery.objects.create(subscription=sub, channel="email", notification_type="daily_digest", dedupe_key=key, status="failed", detail=str(exc)[:500])
        sub.last_sent_at = now
        sub.save(update_fields=["last_sent_at"])
    return {"sent": sent}


@shared_task
def send_deadline_alerts():
    sent = 0
    today = timezone.localdate()
    for days in (7, 3, 1, 0):
        target = today + timedelta(days=days)
        for job in Job.objects.filter(status="published", application_end_date=target):
            label = "today" if days == 0 else f"in {days} day{'s' if days != 1 else ''}"
            for sub in AlertSubscription.objects.filter(active=True):
                if not job_matches_subscription(job, sub):
                    continue
                if send_job_email(sub, job, f"deadline_{days}", f"Application closes {label}"):
                    sent += 1
                if sub.user_id:
                    for push in WebPushSubscription.objects.filter(user_id=sub.user_id, active=True):
                        key = f"push:{push.pk}:{job.pk}:deadline:{days}:{target}"
                        body = f"Last date {target:%d %b %Y}. Verify the official notice before applying."
                        if send_web_push(push, f"Closing {label}", body, absolute_job_url(job), key, job):
                            sent += 1
    return {"sent": sent}


@shared_task
def submit_recent_urls_to_indexing():
    if not settings.GOOGLE_INDEXING_ENABLED:
        return {"skipped": "disabled"}
    submitted = 0
    failed = 0
    cutoff = timezone.now() - timedelta(hours=8)
    for job in Job.objects.filter(status="published", official_apply_url__gt="", updated_at__gte=cutoff)[:200]:
        ok, detail = notify_google(f"{settings.SITE_URL}{job.get_absolute_url()}")
        if ok:
            submitted += 1
        else:
            failed += 1
    return {"submitted": submitted, "failed": failed}


@shared_task
def cleanup_operational_history():
    now = timezone.now()
    a, _ = AnalyticsEvent.objects.filter(created_at__lt=now - timedelta(days=180)).delete()
    l, _ = LinkCheck.objects.filter(checked_at__lt=now - timedelta(days=60)).delete()
    h, _ = SourceHealthCheck.objects.filter(checked_at__lt=now - timedelta(days=90)).delete()
    return {"analytics_deleted": a, "link_checks_deleted": l, "health_checks_deleted": h}


@shared_task
def send_change_alerts():
    sent = 0
    cutoff = timezone.now() - timedelta(hours=2)
    important_fields = {"application_end_date", "exam_date", "admit_card_date", "result_date", "status", "important_update", "vacancies"}
    for event in ChangeEvent.objects.filter(object_type="job", created_at__gte=cutoff)[:300]:
        if not (set(event.field_changes.keys()) & important_fields):
            continue
        job = Job.objects.filter(pk=event.object_pk).first()
        if not job:
            continue
        for sub in AlertSubscription.objects.filter(active=True, confirmed=True):
            if not job_matches_subscription(job, sub):
                continue
            if send_job_email(sub, job, f"change_{event.pk}", "Important official notice update"):
                sent += 1
            if sub.user_id:
                for push in WebPushSubscription.objects.filter(user_id=sub.user_id, active=True):
                    key = f"push:{push.pk}:{job.pk}:change:{event.pk}"
                    if send_web_push(push, "Important job update", job.important_update or f"{job.title} was updated from the official source.", absolute_job_url(job), key, job):
                        sent += 1
    return {"sent": sent}
