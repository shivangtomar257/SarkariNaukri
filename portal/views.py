from __future__ import annotations

from datetime import timedelta
import json
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.core import signing
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.sitemaps import Sitemap
from django.contrib.syndication.views import Feed
from django.core.paginator import Paginator
from django.db import connection
from django.db.models import Count, F, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .eligibility import evaluate, fee_for_category
from .forms import AlertForm, EligibilityForm, PreferenceForm, SignUpForm
from .notifications import send_alert_confirmation
from .middleware import validate_totp
from .models import (
    AdmitCard,
    AlertSubscription,
    AnalyticsEvent,
    ChangeEvent,
    CrawlRun,
    DiscoverySignal,
    ExamEvent,
    Job,
    LinkCheck,
    Result,
    SavedJob,
    SearchQuery,
    Source,
    SourceHealthCheck,
    UserPreference,
    WebPushSubscription,
)

QUALS = ["10th Pass", "12th Pass", "Graduate", "Engineering", "Post Graduate", "ITI", "Diploma"]

TRANSLATIONS = {
    "en": {
        "home": "Home", "latest_jobs": "Latest Jobs", "closing_soon": "Closing Soon", "admit_cards": "Admit Cards",
        "results": "Results", "exam_calendar": "Exam Calendar", "browse_jobs": "Browse Jobs", "saved_jobs": "My Jobs",
        "alerts": "Alerts", "login": "Log in", "logout": "Log out", "profile": "Profile", "search_placeholder": "Search exam, post or department",
        "any_qualification": "Any qualification", "find_jobs": "Find Jobs", "hero_title": "Government jobs, without the clutter.",
        "hero_subtitle": "Verified vacancies, deadlines, admit cards and results — automatically monitored from official sources.",
        "recommended": "Recommended for you", "recently_updated": "Recently updated", "trending": "Trending searches",
        "verified": "Official source verified", "last_date": "Last date", "vacancies": "Vacancies", "qualification": "Qualification",
        "sector": "Sector", "state": "State", "save_job": "Save job", "saved": "Saved", "can_i_apply": "Can I apply?",
        "check_eligibility": "Check eligibility", "official_notification": "Official Notification", "apply_online": "Apply Online",
        "official_website": "Official Website", "source_policy": "Source Policy", "install_app": "Install app", "dark_mode": "Dark mode",
        "language": "हिन्दी", "create_alert": "Create job alert", "account": "Account", "all_jobs": "All Jobs",
    },
    "hi": {
        "home": "होम", "latest_jobs": "नई नौकरियाँ", "closing_soon": "जल्द बंद होने वाली", "admit_cards": "एडमिट कार्ड",
        "results": "रिज़ल्ट", "exam_calendar": "परीक्षा कैलेंडर", "browse_jobs": "नौकरियाँ देखें", "saved_jobs": "मेरी नौकरियाँ",
        "alerts": "अलर्ट", "login": "लॉग इन", "logout": "लॉग आउट", "profile": "प्रोफ़ाइल", "search_placeholder": "परीक्षा, पद या विभाग खोजें",
        "any_qualification": "कोई भी योग्यता", "find_jobs": "नौकरी खोजें", "hero_title": "सरकारी नौकरियाँ, साफ़ और आसान तरीके से।",
        "hero_subtitle": "आधिकारिक स्रोतों से स्वतः सत्यापित रिक्तियाँ, अंतिम तिथियाँ, एडमिट कार्ड और रिज़ल्ट।",
        "recommended": "आपके लिए सुझाव", "recently_updated": "हाल में अपडेट", "trending": "लोकप्रिय खोजें",
        "verified": "आधिकारिक स्रोत सत्यापित", "last_date": "अंतिम तिथि", "vacancies": "रिक्तियाँ", "qualification": "योग्यता",
        "sector": "क्षेत्र", "state": "राज्य", "save_job": "नौकरी सेव करें", "saved": "सेव की गई", "can_i_apply": "क्या मैं आवेदन कर सकता/सकती हूँ?",
        "check_eligibility": "योग्यता जाँचें", "official_notification": "आधिकारिक नोटिफिकेशन", "apply_online": "ऑनलाइन आवेदन",
        "official_website": "आधिकारिक वेबसाइट", "source_policy": "सोर्स नीति", "install_app": "ऐप इंस्टॉल करें", "dark_mode": "डार्क मोड",
        "language": "English", "create_alert": "जॉब अलर्ट बनाएँ", "account": "अकाउंट", "all_jobs": "सभी नौकरियाँ",
    },
}



def _safe_next(request, value, default="/"):
    if value and url_has_allowed_host_and_scheme(value, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return value
    return default


def _user_pref(request):
    if not request.user.is_authenticated:
        return None
    pref, _ = UserPreference.objects.get_or_create(user=request.user)
    return pref


def site_context(request):
    pref = _user_pref(request)
    lang = request.session.get("lang") or (pref.language if pref else "en")
    if lang not in TRANSLATIONS:
        lang = "en"
    return {
        "SITE_NAME": settings.SITE_NAME,
        "SITE_URL": settings.SITE_URL,
        "QUALIFICATIONS": QUALS,
        "QUALIFICATION_LINKS": [{"name": q, "slug": slugify(q)} for q in QUALS],
        "T": TRANSLATIONS[lang],
        "LANG": lang,
        "NEXT_LANG": "hi" if lang == "en" else "en",
        "USER_PREF": pref,
        "VAPID_PUBLIC_KEY": settings.VAPID_PUBLIC_KEY,
    }


def _session_key(request):
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key or ""


def _log_event(request, event_type, job=None, metadata=None):
    try:
        AnalyticsEvent.objects.create(
            event_type=event_type,
            job=job,
            user=request.user if request.user.is_authenticated else None,
            session_key=_session_key(request),
            path=request.path[:500],
            metadata=metadata or {},
        )
    except Exception:
        pass


def _recommended_queryset(pref):
    qs = Job.objects.filter(status="published")
    if not pref:
        return qs.none()
    quals = pref.preferred_qualifications or ([pref.education] if pref.education else [])
    sectors = pref.preferred_sectors or []
    states = pref.preferred_states or ([pref.state] if pref.state else [])
    if quals:
        qs = qs.filter(qualification_group__in=quals)
    if sectors:
        qs = qs.filter(sector__in=sectors)
    if states:
        qs = qs.filter(Q(state__in=states) | Q(state="All India"))
    return qs.order_by("-published_at")


def home(request):
    jobs = Job.objects.filter(status="published")
    pref = _user_pref(request)
    today = timezone.localdate()
    return render(request, "portal/home.html", {
        "latest": jobs[:10],
        "closing": jobs.filter(application_end_date__range=(today, today + timedelta(days=10))).order_by("application_end_date")[:8],
        "admits": AdmitCard.objects.filter(status="published")[:6],
        "results": Result.objects.filter(status="published")[:6],
        "job_count": jobs.count(),
        "recommended": _recommended_queryset(pref)[:8] if pref else [],
        "updated_jobs": jobs.filter(change_version__gt=1).order_by("-updated_at")[:6],
        "trending": SearchQuery.objects.all()[:8],
        "upcoming_events": ExamEvent.objects.filter(event_date__range=(today, today + timedelta(days=30)))[:8],
        "popular_sectors": [{"name": row["sector"], "slug": slugify(row["sector"]), "total": row["total"]} for row in jobs.exclude(sector="").values("sector").annotate(total=Count("id")).order_by("-total")[:10]],
        "popular_states": [{"name": row["state"], "slug": slugify(row["state"]), "total": row["total"]} for row in jobs.exclude(state="").values("state").annotate(total=Count("id")).order_by("-total")[:12]],
        "popular_organizations": [{"name": row["organization"], "slug": slugify(row["organization"]), "total": row["total"]} for row in jobs.exclude(organization="").values("organization").annotate(total=Count("id")).order_by("-total")[:10]],
    })


def _track_search(request, q):
    if not q or len(q) > 240:
        return
    normalized = " ".join(q.lower().split())
    obj, created = SearchQuery.objects.get_or_create(normalized=normalized, defaults={"query": q, "count": 1})
    if not created:
        SearchQuery.objects.filter(pk=obj.pk).update(count=F("count") + 1, query=q)
    _log_event(request, "search", metadata={"q": q})


def _jobs_view(request, forced=None, landing_title=None, landing_description=None):
    forced = forced or {}
    qs = Job.objects.filter(status="published")
    q = request.GET.get("q", "").strip()
    qual = forced.get("qualification", request.GET.get("qualification", "").strip())
    sector = forced.get("sector", request.GET.get("sector", "").strip())
    state = forced.get("state", request.GET.get("state", "").strip())
    organization = forced.get("organization", request.GET.get("organization", "").strip())
    discipline = request.GET.get("discipline", "").strip()
    category = request.GET.get("category", "").strip()
    gender = request.GET.get("gender", "").strip()
    age_raw = request.GET.get("age", "").strip()
    experience_raw = request.GET.get("experience", "").strip()
    sort = request.GET.get("sort", "latest")
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(organization__icontains=q) | Q(post_name__icontains=q) | Q(advertisement_no__icontains=q))
        _track_search(request, q)
    if qual:
        qs = qs.filter(qualification_group=qual)
    if sector:
        qs = qs.filter(sector=sector)
    if state:
        qs = qs.filter(state=state)
    if organization:
        qs = qs.filter(organization=organization)
    try:
        age = int(age_raw) if age_raw else None
    except ValueError:
        age = None
    if age is not None and 14 <= age <= 80:
        qs = qs.filter(Q(min_age__isnull=True) | Q(min_age__lte=age)).filter(Q(max_age__isnull=True) | Q(max_age__gte=age))
    try:
        experience = int(experience_raw) if experience_raw else None
    except ValueError:
        experience = None
    if experience is not None and experience >= 0:
        qs = qs.filter(min_experience_months__lte=experience)
    # JSON array containment is optimized for the production PostgreSQL target. Empty arrays mean "not explicitly restricted".
    if connection.vendor == "postgresql":
        if discipline:
            qs = qs.filter(Q(accepted_disciplines=[]) | Q(accepted_disciplines__contains=[discipline]))
        if category:
            qs = qs.filter(Q(eligible_categories=[]) | Q(eligible_categories__contains=[category]))
        if gender:
            qs = qs.filter(Q(eligible_genders=[]) | Q(eligible_genders__contains=[gender]))
    if request.GET.get("closing") == "1":
        qs = qs.filter(application_end_date__range=(timezone.localdate(), timezone.localdate() + timedelta(days=14)))
        sort = "deadline"
    if request.GET.get("updated") == "1":
        qs = qs.filter(change_version__gt=1)
    if sort == "deadline":
        qs = qs.order_by("application_end_date", "-published_at")
    elif sort == "vacancies":
        qs = qs.order_by("-vacancies", "-published_at")
    else:
        qs = qs.order_by("-published_at")
    paginator = Paginator(qs, 30)
    page = paginator.get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "portal/jobs.html", {
        "jobs": page,
        "page_obj": page,
        "q": q,
        "qual": qual,
        "sector": sector,
        "state": state,
        "organization": organization,
        "discipline": discipline,
        "category": category,
        "gender": gender,
        "age": age_raw,
        "experience": experience_raw,
        "sort": sort,
        "base_query": params.urlencode(),
        "sectors": Job.objects.filter(status="published").exclude(sector="").values_list("sector", flat=True).distinct().order_by("sector"),
        "states": Job.objects.filter(status="published").exclude(state="").values_list("state", flat=True).distinct().order_by("state"),
        "organizations": Job.objects.filter(status="published").exclude(organization="").values_list("organization", flat=True).distinct().order_by("organization")[:300],
        "landing_title": landing_title,
        "landing_description": landing_description,
    })


def jobs(request):
    return _jobs_view(request)


def qualification_jobs(request, slug):
    value = next((x for x in QUALS if slugify(x) == slug), None)
    if not value:
        raise Http404
    return _jobs_view(request, {"qualification": value}, f"{value} Government Jobs", f"Verified active government recruitment for {value} candidates.")


def _resolve_distinct(field, slug):
    values = Job.objects.filter(status="published").exclude(**{field: ""}).values_list(field, flat=True).distinct()[:1000]
    return next((x for x in values if slugify(x) == slug), None)


def sector_jobs(request, slug):
    value = _resolve_distinct("sector", slug)
    if not value:
        raise Http404
    return _jobs_view(request, {"sector": value}, f"{value} Government Jobs", f"Latest verified {value} recruitment notifications.")


def state_jobs(request, slug):
    value = _resolve_distinct("state", slug)
    if not value:
        raise Http404
    return _jobs_view(request, {"state": value}, f"Government Jobs in {value}", f"Latest verified government recruitment notifications for {value}.")


def organization_jobs(request, slug):
    value = _resolve_distinct("organization", slug)
    if not value:
        raise Http404
    return _jobs_view(request, {"organization": value}, f"{value} Recruitment", f"Latest verified jobs and recruitment notices from {value}.")


def _schema_for_job(job):
    if not settings.PUBLIC_JOB_SCHEMA_ENABLED or job.status != "published" or not job.official_apply_url:
        return None
    schema = {
        "@context": "https://schema.org/",
        "@type": "JobPosting",
        "title": job.post_name or job.title,
        "description": job.summary or job.title,
        "datePosted": (job.published_at or job.first_seen_at).date().isoformat(),
        "hiringOrganization": {"@type": "Organization", "name": job.organization, "sameAs": job.official_website_url or job.source_url},
        "url": f"{settings.SITE_URL}{job.get_absolute_url()}",
    }
    allowed_employment_types = {"FULL_TIME", "PART_TIME", "CONTRACTOR", "TEMPORARY", "INTERN", "VOLUNTEER", "PER_DIEM", "OTHER"}
    if (job.employment_type or "").upper() in allowed_employment_types:
        schema["employmentType"] = job.employment_type.upper()
    if job.application_end_date:
        schema["validThrough"] = f"{job.application_end_date.isoformat()}T23:59:59+05:30"
    if job.location:
        schema["jobLocation"] = {"@type": "Place", "address": {"@type": "PostalAddress", "addressLocality": job.location, "addressRegion": job.state or "India", "addressCountry": "IN"}}
    elif job.state and job.state != "All India":
        schema["jobLocation"] = {"@type": "Place", "address": {"@type": "PostalAddress", "addressRegion": job.state, "addressCountry": "IN"}}
    return schema


def job_detail(request, slug):
    job = get_object_or_404(Job, slug=slug, status__in=["published", "expired"])
    _log_event(request, "view", job)
    pref = _user_pref(request)
    initial = {}
    if pref:
        initial = {"education": pref.education, "discipline": pref.discipline, "date_of_birth": pref.date_of_birth, "category": pref.category, "experience_months": pref.experience_months}
    eligibility_form = EligibilityForm(initial=initial)
    eligibility_result = None
    if request.method == "POST" and request.POST.get("action") == "eligibility":
        eligibility_form = EligibilityForm(request.POST)
        if eligibility_form.is_valid():
            eligibility_result = evaluate(job, **{
                "education": eligibility_form.cleaned_data.get("education") or "",
                "discipline": eligibility_form.cleaned_data.get("discipline") or "",
                "dob": eligibility_form.cleaned_data.get("date_of_birth"),
                "category": eligibility_form.cleaned_data.get("category") or "General",
                "gender": eligibility_form.cleaned_data.get("gender") or "",
                "experience_months": eligibility_form.cleaned_data.get("experience_months") or 0,
            })
            _log_event(request, "eligibility", job, {"status": eligibility_result.status})
    elif pref and any([pref.education, pref.date_of_birth, pref.discipline]):
        eligibility_result = evaluate(job, education=pref.education, discipline=pref.discipline, dob=pref.date_of_birth, category=pref.category, experience_months=pref.experience_months)

    fee_category = request.GET.get("fee_category") or (pref.category if pref else "General")
    fee_value = fee_for_category(job, fee_category)
    saved = SavedJob.objects.filter(user=request.user, job=job).first() if request.user.is_authenticated else None

    recent_ids = [x for x in request.session.get("recent_jobs", []) if x != job.pk]
    recent_jobs = list(Job.objects.filter(pk__in=recent_ids[:5], status__in=["published", "expired"]))
    request.session["recent_jobs"] = [job.pk] + recent_ids[:9]
    related = Job.objects.filter(status="published").exclude(pk=job.pk).filter(Q(sector=job.sector) | Q(qualification_group=job.qualification_group) | Q(state=job.state)).order_by("-published_at")[:6]
    changes = ChangeEvent.objects.filter(object_type="job", object_pk=job.pk)[:10]
    latest_links = {}
    for check in LinkCheck.objects.filter(job=job).order_by("kind", "-checked_at"):
        latest_links.setdefault(check.kind, check)
    schema = _schema_for_job(job)
    return render(request, "portal/job_detail.html", {
        "job": job,
        "eligibility_form": eligibility_form,
        "eligibility_result": eligibility_result,
        "fee_category": fee_category,
        "fee_value": fee_value,
        "saved_job": saved,
        "related": related,
        "recent_jobs": recent_jobs,
        "changes": changes,
        "link_checks": latest_links,
        "job_schema_json": json.dumps(schema, ensure_ascii=False) if schema else "",
        "canonical_url": f"{settings.SITE_URL}{job.get_absolute_url()}",
        "organization_slug": slugify(job.organization),
        "sector_slug": slugify(job.sector),
        "state_slug": slugify(job.state),
        "qualification_slug": slugify(job.qualification_group),
        "notification_is_pdf": ".pdf" in (job.official_notification_url or "").lower(),
    })


def admit_cards(request):
    return render(request, "portal/notices.html", {"kind": "Admit Cards", "items": AdmitCard.objects.filter(status="published")[:200], "notice_type": "admit"})


def results(request):
    return render(request, "portal/notices.html", {"kind": "Results", "items": Result.objects.filter(status="published")[:200], "notice_type": "result"})


def policy(request):
    return render(request, "portal/policy.html")


def exam_calendar(request):
    today = timezone.localdate()
    event_type = request.GET.get("type", "")
    qs = ExamEvent.objects.filter(event_date__gte=today)
    if event_type:
        qs = qs.filter(event_type=event_type)
    return render(request, "portal/calendar.html", {"events": qs[:500], "event_type": event_type, "today": today})


def calendar_ics(request):
    today = timezone.localdate()
    events = ExamEvent.objects.filter(event_date__gte=today)[:500]
    def esc(v):
        return str(v).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//SarkariNaukri//Exam Calendar//EN", "CALSCALE:GREGORIAN"]
    stamp = timezone.now().strftime("%Y%m%dT%H%M%SZ")
    for e in events:
        lines += [
            "BEGIN:VEVENT", f"UID:exam-{e.pk}@sarkarinaukri", f"DTSTAMP:{stamp}", f"DTSTART;VALUE=DATE:{e.event_date:%Y%m%d}",
            f"SUMMARY:{esc(e.title)}", f"DESCRIPTION:{esc(e.get_event_type_display())}",
            *( [f"URL:{e.official_url}"] if e.official_url else [] ), "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    response = HttpResponse("\r\n".join(lines), content_type="text/calendar; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="sarkarinaukri-exam-calendar.ics"'
    return response


@require_POST
@login_required
def save_job(request, job_id):
    job = get_object_or_404(Job, pk=job_id)
    obj = SavedJob.objects.filter(user=request.user, job=job).first()
    if request.POST.get("action") == "unsave":
        if obj:
            obj.delete()
        messages.success(request, "Job removed from your saved list.")
    else:
        SavedJob.objects.get_or_create(user=request.user, job=job)
        _log_event(request, "save", job)
        messages.success(request, "Job saved to My Jobs.")
    return redirect(_safe_next(request, request.POST.get("next"), job.get_absolute_url()))


@require_POST
@login_required
def update_tracker(request, saved_id):
    saved = get_object_or_404(SavedJob, pk=saved_id, user=request.user)
    status = request.POST.get("status")
    valid = {x[0] for x in SavedJob.STATUSES}
    if status in valid:
        saved.status = status
        saved.notes = request.POST.get("notes", "")[:500]
        saved.save()
        messages.success(request, "Application tracker updated.")
    return redirect("account-dashboard")


@login_required
def account_dashboard(request):
    saved = SavedJob.objects.filter(user=request.user).select_related("job")
    return render(request, "portal/account_dashboard.html", {"saved_jobs": saved, "alerts": AlertSubscription.objects.filter(user=request.user, active=True)})


@login_required
def profile(request):
    pref = _user_pref(request)
    form = PreferenceForm(request.POST or None, instance=pref)
    if request.method == "POST" and form.is_valid():
        form.save()
        request.session["lang"] = form.cleaned_data.get("language") or "en"
        messages.success(request, "Your preferences were updated.")
        return redirect("profile")
    return render(request, "portal/profile.html", {"form": form})


def signup(request):
    if request.user.is_authenticated:
        return redirect("account-dashboard")
    form = SignUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        UserPreference.objects.get_or_create(user=user)
        AlertSubscription.objects.filter(user__isnull=True, email__iexact=user.email).update(user=user)
        login(request, user)
        messages.success(request, "Account created. Add your profile to get personalized eligibility and alerts.")
        return redirect("profile")
    return render(request, "registration/signup.html", {"form": form})


@login_required
def alerts(request):
    form = AlertForm(request.POST or None, initial={"email": request.user.email})
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.user = request.user
        obj.confirmed = False
        obj.active = False
        obj.save()
        send_alert_confirmation(obj)
        _log_event(request, "alert_signup")
        messages.success(request, "Check your email to confirm and activate the new alert.")
        return redirect("alerts")
    return render(request, "portal/alerts.html", {"form": form, "subscriptions": AlertSubscription.objects.filter(user=request.user)})


@require_POST
def public_alert_signup(request):
    # Honeypot field used by the homepage form.
    if request.POST.get("company"):
        return redirect("home")
    form = AlertForm(request.POST)
    if form.is_valid():
        obj = form.save(commit=False)
        if request.user.is_authenticated:
            obj.user = request.user
        obj.confirmed = False
        obj.active = False
        obj.save()
        send_alert_confirmation(obj)
        _log_event(request, "alert_signup")
        messages.success(request, "Check your email to confirm and activate the job alert.")
    else:
        messages.error(request, "Please enter a valid email for alerts.")
    return redirect(_safe_next(request, request.POST.get("next"), reverse("home")))


def confirm_alert(request, token):
    try:
        data = signing.loads(token, salt="sarkarinaukri-alert-confirm", max_age=60 * 60 * 24 * 7)
        sub = AlertSubscription.objects.get(pk=data["id"], email__iexact=data["email"])
        sub.confirmed = True
        sub.active = True
        sub.save(update_fields=["confirmed", "active"])
        messages.success(request, "Your SarkariNaukri job alert is now active.")
    except Exception:
        messages.error(request, "This alert confirmation link is invalid or expired.")
    return redirect("alerts" if request.user.is_authenticated else "home")


def unsubscribe_alert(request, token):
    try:
        data = signing.loads(token, salt="sarkarinaukri-alert-unsubscribe")
        sub = AlertSubscription.objects.get(pk=data["id"], email__iexact=data["email"])
        sub.active = False
        sub.save(update_fields=["active"])
        messages.success(request, "The job alert has been unsubscribed.")
    except Exception:
        messages.error(request, "This unsubscribe link is invalid.")
    return redirect("home")


@require_POST
@login_required
def delete_alert(request, alert_id):
    sub = get_object_or_404(AlertSubscription, pk=alert_id, user=request.user)
    sub.active = False
    sub.save(update_fields=["active"])
    messages.success(request, "Alert disabled.")
    return redirect("alerts")


def set_language(request, code):
    if code not in TRANSLATIONS:
        raise Http404
    request.session["lang"] = code
    if request.user.is_authenticated:
        pref = _user_pref(request)
        pref.language = code
        pref.save(update_fields=["language", "updated_at"])
    return redirect(_safe_next(request, request.GET.get("next") or request.META.get("HTTP_REFERER"), "/"))


def autocomplete(request):
    q = request.GET.get("q", "").strip()
    if len(q) < 2:
        return JsonResponse({"results": []})
    rows = Job.objects.filter(status="published").filter(Q(title__icontains=q) | Q(organization__icontains=q) | Q(post_name__icontains=q)).values("title", "organization", "slug")[:10]
    return JsonResponse({"results": [{"label": x["title"], "sub": x["organization"], "url": reverse("job-detail", kwargs={"slug": x["slug"]})} for x in rows]})


@require_POST
@login_required
def webpush_subscribe(request):
    try:
        data = json.loads(request.body.decode("utf-8"))
        endpoint = data["endpoint"]
        keys = data["keys"]
        WebPushSubscription.objects.update_or_create(
            endpoint=endpoint,
            defaults={"user": request.user, "p256dh": keys["p256dh"], "auth": keys["auth"], "active": True},
        )
        pref = _user_pref(request)
        pref.push_alerts = True
        pref.save(update_fields=["push_alerts", "updated_at"])
        return JsonResponse({"ok": True})
    except Exception as exc:
        return JsonResponse({"ok": False, "error": str(exc)[:200]}, status=400)


def external_redirect(request, job_id, kind):
    job = get_object_or_404(Job, pk=job_id, status__in=["published", "expired"])
    mapping = {
        "apply": (job.official_apply_url, "apply_click"),
        "notification": (job.official_notification_url, "notification_click"),
        "website": (job.official_website_url, "website_click"),
    }
    if kind not in mapping or not mapping[kind][0]:
        raise Http404
    _log_event(request, mapping[kind][1], job)
    return redirect(mapping[kind][0])


@staff_member_required
def ops(request):
    sources = list(Source.objects.all())
    source_rows = [{"source": s, "health": SourceHealthCheck.objects.filter(source=s).first()} for s in sources]
    broken = LinkCheck.objects.filter(ok=False).select_related("job")[:30]
    return render(request, "portal/ops.html", {
        "sources": sources,
        "source_rows": source_rows,
        "runs": CrawlRun.objects.all()[:20],
        "review_jobs": Job.objects.filter(status="review")[:25],
        "signals": DiscoverySignal.objects.filter(status__in=["new", "review"])[:25],
        "broken_links": broken,
    })


@staff_member_required
def analytics_dashboard(request):
    since = timezone.now() - timedelta(days=30)
    events = AnalyticsEvent.objects.filter(created_at__gte=since)
    event_counts = events.values("event_type").annotate(total=Count("id")).order_by("-total")
    top_jobs = Job.objects.filter(analytics_events__created_at__gte=since).annotate(traffic=Count("analytics_events")).order_by("-traffic")[:15]
    top_searches = SearchQuery.objects.all()[:15]
    sources_unhealthy = SourceHealthCheck.objects.filter(status__in=["warn", "fail"], checked_at__gte=timezone.now() - timedelta(days=1)).values("source__name").annotate(total=Count("id")).order_by("-total")[:15]
    return render(request, "portal/analytics.html", {
        "event_counts": event_counts,
        "top_jobs": top_jobs,
        "top_searches": top_searches,
        "sources_unhealthy": sources_unhealthy,
        "published_jobs": Job.objects.filter(status="published").count(),
        "saved_count": SavedJob.objects.count(),
        "alert_count": AlertSubscription.objects.filter(active=True).count(),
        "broken_count": LinkCheck.objects.filter(ok=False, checked_at__gte=timezone.now() - timedelta(days=1)).count(),
    })


def staff_2fa(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        return redirect(settings.LOGIN_URL)
    if not settings.ADMIN_TOTP_SECRET:
        request.session["staff_2fa_ok"] = True
        return redirect(_safe_next(request, request.GET.get("next"), "/admin/"))
    error = ""
    if request.method == "POST":
        if validate_totp(settings.ADMIN_TOTP_SECRET, request.POST.get("code", "")):
            request.session["staff_2fa_ok"] = True
            return redirect(_safe_next(request, request.POST.get("next"), "/admin/"))
        error = "Invalid or expired code."
    return render(request, "portal/staff_2fa.html", {"error": error, "next": request.GET.get("next", "/admin/")})


def health(request):
    checks = {"database": False}
    try:
        with connection.cursor() as c:
            c.execute("SELECT 1")
            c.fetchone()
            checks["database"] = True
    except Exception:
        pass
    ok = all(checks.values())
    return JsonResponse({"ok": ok, "checks": checks, "time": timezone.now().isoformat()}, status=200 if ok else 503)


def api_jobs(request):
    qs = Job.objects.filter(status="published")[:100]
    data = [{
        "title": j.title,
        "organization": j.organization,
        "vacancies": j.vacancies,
        "qualification": j.qualification_group,
        "sector": j.sector,
        "state": j.state,
        "last_date": j.application_end_date.isoformat() if j.application_end_date else None,
        "verified_at": j.verified_at.isoformat() if j.verified_at else None,
        "url": f"{settings.SITE_URL}{j.get_absolute_url()}",
    } for j in qs]
    return JsonResponse({"results": data})


def robots_txt(request):
    body = f"User-agent: *\nAllow: /\nDisallow: /admin/\nDisallow: /ops/\nDisallow: /analytics/\nDisallow: /account/\nSitemap: {settings.SITE_URL}/sitemap.xml\n"
    return HttpResponse(body, content_type="text/plain")


def service_worker(request):
    path = Path(settings.BASE_DIR) / "portal" / "static" / "portal" / "service-worker.js"
    response = HttpResponse(path.read_text(encoding="utf-8"), content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache"
    return response


class JobSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.9

    def items(self):
        return Job.objects.filter(status="published")

    def lastmod(self, obj):
        return obj.updated_at


class LandingSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.7

    def items(self):
        items = [("qualification-jobs", slugify(x)) for x in QUALS]
        items += [("sector-jobs", slugify(x)) for x in Job.objects.filter(status="published").exclude(sector="").values_list("sector", flat=True).distinct()]
        items += [("state-jobs", slugify(x)) for x in Job.objects.filter(status="published").exclude(state="").values_list("state", flat=True).distinct()]
        items += [("organization-jobs", slugify(x)) for x in Job.objects.filter(status="published").exclude(organization="").values_list("organization", flat=True).distinct()[:500]]
        return items

    def location(self, item):
        return reverse(item[0], kwargs={"slug": item[1]})


class StaticSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.6

    def items(self):
        return ["home", "jobs", "admit-cards", "results", "exam-calendar", "policy"]

    def location(self, item):
        return reverse(item)


class LatestJobsFeed(Feed):
    title = "SarkariNaukri — Latest Government Jobs"
    link = "/jobs/"
    description = "Latest verified Indian government recruitment notifications."

    def items(self):
        return Job.objects.filter(status="published").order_by("-published_at")[:50]

    def item_title(self, item):
        return item.title

    def item_description(self, item):
        return item.summary or f"{item.organization} recruitment. Verify the official notification before applying."

    def item_pubdate(self, item):
        return item.published_at or item.first_seen_at
