from __future__ import annotations

import json
from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse
from .models import Job, AlertSubscription, NotificationDelivery, WebPushSubscription


def job_matches_subscription(job: Job, sub: AlertSubscription) -> bool:
    if sub.qualifications and job.qualification_group not in sub.qualifications:
        return False
    if sub.sectors and job.sector not in sub.sectors:
        return False
    if sub.states and job.state not in sub.states and "All India" not in sub.states:
        return False
    if sub.keywords:
        hay = f"{job.title} {job.organization} {job.post_name}".lower()
        if not any(k.lower() in hay for k in sub.keywords):
            return False
    return True


def absolute_job_url(job: Job) -> str:
    return f"{settings.SITE_URL}{job.get_absolute_url()}"


def send_job_email(sub: AlertSubscription, job: Job, notification_type: str, subject_prefix: str = "New job") -> bool:
    key = f"email:{sub.pk}:{job.pk}:{notification_type}"
    if NotificationDelivery.objects.filter(dedupe_key=key).exists():
        return False
    subject = f"{subject_prefix}: {job.title}"
    body = (
        f"{job.title}\n{job.organization}\n\n"
        f"Qualification: {job.qualification_group or 'See official notice'}\n"
        f"Last date: {job.application_end_date or 'See official notice'}\n\n"
        f"View verified details: {absolute_job_url(job)}\n\n"
        "SarkariNaukri is an independent information portal. Always verify the official notification before applying.\n\n"
        f"Unsubscribe: {settings.SITE_URL}{reverse('unsubscribe-alert', kwargs={'token': unsubscribe_token(sub)})}"
    )
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [sub.email], fail_silently=False)
        NotificationDelivery.objects.create(subscription=sub, job=job, channel="email", notification_type=notification_type, dedupe_key=key, status="sent")
        return True
    except Exception as exc:
        NotificationDelivery.objects.create(subscription=sub, job=job, channel="email", notification_type=notification_type, dedupe_key=key, status="failed", detail=str(exc)[:500])
        return False


def send_web_push(subscription: WebPushSubscription, title: str, body: str, url: str, dedupe_key: str, job: Job | None = None) -> bool:
    if NotificationDelivery.objects.filter(dedupe_key=dedupe_key).exists():
        return False
    if not settings.VAPID_PRIVATE_KEY or not subscription.active:
        return False
    try:
        from pywebpush import webpush
        webpush(
            subscription_info={"endpoint": subscription.endpoint, "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth}},
            data=json.dumps({"title": title, "body": body, "url": url}),
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": settings.VAPID_SUBJECT},
        )
        NotificationDelivery.objects.create(user=subscription.user, job=job, channel="push", notification_type="web_push", dedupe_key=dedupe_key, status="sent")
        return True
    except Exception as exc:
        subscription.active = False if "410" in str(exc) or "404" in str(exc) else subscription.active
        subscription.save(update_fields=["active", "updated_at"])
        NotificationDelivery.objects.create(user=subscription.user, job=job, channel="push", notification_type="web_push", dedupe_key=dedupe_key, status="failed", detail=str(exc)[:500])
        return False


def confirmation_token(sub: AlertSubscription) -> str:
    from django.core import signing
    return signing.dumps({"id": sub.pk, "email": sub.email}, salt="sarkarinaukri-alert-confirm")


def unsubscribe_token(sub: AlertSubscription) -> str:
    from django.core import signing
    return signing.dumps({"id": sub.pk, "email": sub.email}, salt="sarkarinaukri-alert-unsubscribe")


def send_alert_confirmation(sub: AlertSubscription) -> bool:
    from django.urls import reverse
    token = confirmation_token(sub)
    url = f"{settings.SITE_URL}{reverse('confirm-alert', kwargs={'token': token})}"
    body = (
        "Confirm your SarkariNaukri job alert\n\n"
        f"Activate this alert: {url}\n\n"
        "If you did not request this alert, ignore this message. The alert will remain inactive."
    )
    try:
        send_mail("Confirm your SarkariNaukri job alert", body, settings.DEFAULT_FROM_EMAIL, [sub.email], fail_silently=False)
        return True
    except Exception:
        return False
