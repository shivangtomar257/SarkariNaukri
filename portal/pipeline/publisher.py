from __future__ import annotations

from datetime import datetime
import re
from django.conf import settings
from django.utils import timezone
from django.utils.text import slugify
from portal.models import Job, AdmitCard, Result, ChangeEvent, ExamEvent
from .extract import deterministic_extract, ai_extract
from .dedupe import similarity


def _date(value):
    if not value:
        return None
    if hasattr(value, "year"):
        return value
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except Exception:
        return None


def _headline(data: dict) -> str:
    org = data.get("organization") or "Government Department"
    post = data.get("post_name") or "Recruitment"
    vac = data.get("vacancies")
    return f"{org} {post} Recruitment — {vac:,} Vacancies" if isinstance(vac, int) else f"{org} {post} Recruitment"


def _status(conf: float, end_date, official: bool):
    threshold = settings.AUTO_PUBLISH_CONFIDENCE
    if official and conf >= threshold and end_date and end_date >= timezone.localdate():
        return "published"
    return "review"


def _relaxation_dict(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        out = {}
        for item in value:
            if isinstance(item, dict) and item.get("category") and item.get("years") is not None:
                try:
                    out[str(item["category"])] = int(item["years"])
                except (TypeError, ValueError):
                    pass
        return out
    return {}


def _fee_dict(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        out = {}
        for item in value:
            if isinstance(item, dict) and item.get("category") and item.get("fee"):
                out[str(item["category"])] = str(item["fee"])
        return out
    return {}


def sync_exam_events(job: Job):
    ExamEvent.objects.filter(job=job, auto_generated=True).delete()
    mapping = [
        ("apply_start", job.application_start_date, "Application opens"),
        ("apply_end", job.application_end_date, "Application deadline"),
        ("exam", job.exam_date, "Exam date"),
        ("admit", job.admit_card_date, "Admit card"),
        ("result", job.result_date, "Result"),
    ]
    for event_type, event_date, label in mapping:
        if not event_date:
            continue
        ExamEvent.objects.create(
            job=job,
            event_type=event_type,
            event_date=event_date,
            title=f"{job.organization} — {label}: {job.post_name or job.title}",
            organization=job.organization,
            official_url=job.official_notification_url,
            auto_generated=True,
        )



def apply_status_notice(document, text_override: str = "") -> tuple[bool, Job | None]:
    """Detect cancellation/postponement notices and update the closest existing recruitment record."""
    text = text_override or document.content_text or document.excerpt
    title_blob = (document.title or "").lower()
    body_blob = text[:60000].lower()
    cancellation = bool(
        re.search(r"\b(cancelled|canceled|cancellation|withdrawn)\b", title_blob)
        or re.search(r"(?:recruitment|advertisement|advt\.?|vacancy|notification)[^\n.]{0,100}\b(cancelled|canceled|withdrawn)\b", body_blob)
        or re.search(r"\b(cancelled|canceled|withdrawn)\b[^\n.]{0,100}(?:recruitment|advertisement|advt\.?|vacancy|notification)", body_blob)
    )
    postponement = bool(
        re.search(r"\b(postponed|deferred|rescheduled)\b", title_blob)
        or re.search(r"(?:exam|examination|interview|schedule)[^\n.]{0,100}\b(postponed|deferred|rescheduled)\b", body_blob)
    )
    if not cancellation and not postponement:
        return False, None
    data = deterministic_extract(document.title, text, document.links, document.url, document.source.extra_allowed_domains)
    ad = (data.get("advertisement_no") or "").strip()
    candidates = Job.objects.all()
    if ad:
        candidates = candidates.filter(advertisement_no__icontains=ad)
    else:
        candidates = candidates.filter(official_website_url=document.source.base_url)
    candidates = list(candidates.order_by("-updated_at")[:80])
    target = None
    if candidates:
        cleaned = re.sub(r"cancel(?:led|lation)|withdrawn|postponed|deferred|rescheduled|notice|notification", " ", document.title, flags=re.I)
        target = max(candidates, key=lambda j: similarity(j.title, cleaned))
        if not ad and similarity(target.title, cleaned) < 0.35:
            target = None
    if not target:
        return True, None
    changes = {}
    if cancellation and target.status != "cancelled":
        changes["status"] = {"old": target.status, "new": "cancelled"}
        target.status = "cancelled"
        target.is_postponed = False
        target.important_update = "Recruitment cancellation/withdrawal notice detected from the official source. Verify the linked official notice."
        changes["important_update"] = {"old": "", "new": target.important_update}
    elif postponement:
        old = target.important_update
        target.is_postponed = True
        target.important_update = "Postponement/rescheduling notice detected from the official source. Check the latest official notice for the revised schedule."
        changes["important_update"] = {"old": old, "new": target.important_update}
        changes["is_postponed"] = {"old": False, "new": True}
        new_exam = _date(data.get("exam_date"))
        if new_exam and new_exam != target.exam_date:
            changes["exam_date"] = {"old": str(target.exam_date), "new": str(new_exam)}
            target.exam_date = new_exam
            target.is_postponed = False
            target.important_update = f"Exam schedule updated from the latest official notice: {new_exam:%d %b %Y}."
    if changes:
        target.change_version += 1
        target.verified_at = timezone.now()
        target.source_hash = document.content_hash
        target.save()
        sync_exam_events(target)
        ChangeEvent.objects.create(object_type="job", object_pk=target.pk, title=target.title, field_changes=changes, source_url=document.url)
    return True, target


def upsert_job(document, discovered_via: str = "", discovery_url: str = "", text_override: str = "") -> tuple[Job, bool, bool]:
    text = text_override or document.content_text or document.excerpt
    det = deterministic_extract(document.title, text, document.links, document.url, document.source.extra_allowed_domains)
    ai = ai_extract(document.title, text)
    data = {**det, **({k: v for k, v in ai.items() if v not in (None, "", [])} if ai else {})}
    conf = max(float(det.get("confidence", 0)), float((ai or {}).get("confidence", 0))) * float(document.source.trust_score)

    end = _date(data.get("application_end_date"))
    start = _date(data.get("application_start_date"))
    exam = _date(data.get("exam_date"))
    admit = _date(data.get("admit_card_date"))
    result = _date(data.get("result_date"))
    age_as_on = _date(data.get("age_as_on"))
    title = _headline(data)

    defaults = {
        "title": title,
        "organization": data.get("organization") or document.source.name,
        "advertisement_no": data.get("advertisement_no", "") or "",
        "post_name": data.get("post_name", "") or "",
        "summary": (ai or {}).get("summary", "")
        or f"{data.get('organization') or document.source.name} has published an official recruitment notice. Verify eligibility, dates and application instructions in the linked official notification before applying.",
        "vacancies": data.get("vacancies"),
        "qualifications": data.get("qualifications") or [],
        "qualification_group": data.get("qualification_group", "") or "",
        "accepted_disciplines": data.get("accepted_disciplines") or [],
        "eligible_categories": data.get("eligible_categories") or [],
        "eligible_genders": data.get("eligible_genders") or [],
        "sector": data.get("sector", "") or "Government",
        "state": data.get("state", "") or "",
        "employment_type": data.get("employment_type", "") or "Government",
        "salary": data.get("salary", "") or "",
        "age_limit": data.get("age_limit", "") or "",
        "min_age": data.get("min_age"),
        "max_age": data.get("max_age"),
        "age_as_on": age_as_on,
        "category_age_relaxation": _relaxation_dict(data.get("age_relaxations") or data.get("category_age_relaxation")),
        "min_experience_months": int(data.get("min_experience_months") or 0),
        "application_fee": data.get("application_fee", "") or "",
        "fee_by_category": _fee_dict(data.get("fee_by_category")),
        "selection_process": data.get("selection_process", "") or "",
        "application_start_date": start,
        "application_end_date": end,
        "exam_date": exam,
        "admit_card_date": admit,
        "result_date": result,
        "official_notification_url": document.url,
        "official_apply_url": det.get("official_apply_url", "") or "",
        "official_website_url": document.source.base_url,
        "source_hash": document.content_hash,
        "discovered_via": discovered_via,
        "discovery_url": discovery_url,
        "evidence_urls": [document.url],
        "verification_confidence": min(conf, 1.0),
        "verified_at": timezone.now(),
    }
    defaults["status"] = _status(defaults["verification_confidence"], end, document.source.source_type == "official")
    if defaults["status"] == "published":
        defaults["published_at"] = timezone.now()

    obj = Job.objects.filter(source_url=document.url).first()
    if not obj and defaults["advertisement_no"]:
        obj = Job.objects.filter(advertisement_no__iexact=defaults["advertisement_no"], organization__iexact=defaults["organization"]).first()
    if not obj:
        for candidate in Job.objects.filter(organization__iexact=defaults["organization"]).order_by("-first_seen_at")[:30]:
            if similarity(candidate.title, title) >= 0.90:
                obj = candidate
                break

    created = obj is None
    if created:
        obj = Job.objects.create(slug=slugify(title)[:210], source_url=document.url, **defaults)
        sync_exam_events(obj)
        return obj, True, False

    changed = False
    changes = {}
    evidence = list(dict.fromkeys((obj.evidence_urls or []) + [document.url]))
    defaults["evidence_urls"] = evidence
    defaults["source_url"] = document.url
    if obj.status == "cancelled":
        defaults["status"] = "cancelled"
    for field, val in defaults.items():
        old = getattr(obj, field)
        if old != val:
            changes[field] = {"old": str(old)[:500], "new": str(val)[:500]}
            setattr(obj, field, val)
    if changes:
        obj.change_version += 1
        obj.save()
        sync_exam_events(obj)
        changed = True
        ChangeEvent.objects.create(object_type="job", object_pk=obj.pk, title=obj.title, field_changes=changes, source_url=document.url)
    return obj, False, changed


def upsert_simple_notice(document, kind: str, text_override: str = ""):
    cls = AdmitCard if kind == "admit_card" else Result
    text = text_override or document.content_text or document.excerpt
    data = deterministic_extract(document.title, text, document.links, document.url, document.source.extra_allowed_domains)
    conf = min(float(data.get("confidence", 0)) + 0.12, 0.99) * float(document.source.trust_score)
    title = document.title[:320] or f"{document.source.name} {kind.replace('_', ' ').title()}"
    slug = slugify(title)[:210]
    defaults = {
        "title": title,
        "organization": data.get("organization") or document.source.name,
        "official_url": document.url,
        "source_hash": document.content_hash,
        "verification_confidence": conf,
        "verified_at": timezone.now(),
        "status": "published" if conf >= settings.AUTO_PUBLISH_CONFIDENCE else "review",
    }
    if cls is AdmitCard:
        defaults.update({"exam_name": data.get("post_name", "") or "", "release_date": timezone.localdate()})
    else:
        defaults.update({"exam_name": data.get("post_name", "") or "", "result_date": timezone.localdate()})
    return cls.objects.update_or_create(source_url=document.url, defaults={"slug": slug, **defaults})
