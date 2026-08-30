from __future__ import annotations

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify


class Source(models.Model):
    OFFICIAL = "official"
    DISCOVERY = "discovery"
    SOURCE_TYPES = [(OFFICIAL, "Official authority"), (DISCOVERY, "Discovery/reference only")]

    name = models.CharField(max_length=160)
    source_type = models.CharField(max_length=16, choices=SOURCE_TYPES, default=OFFICIAL)
    base_url = models.URLField()
    entry_url = models.URLField()
    enabled = models.BooleanField(default=True)
    trust_score = models.FloatField(default=1.0)
    crawl_interval_minutes = models.PositiveIntegerField(default=240)
    max_links_per_scan = models.PositiveIntegerField(default=80)
    allow_store_body = models.BooleanField(default=False)
    extra_allowed_domains = models.JSONField(default=list, blank=True)
    user_agent = models.CharField(max_length=200, default="SarkariNaukriBot/1.0 (+source-verification)")
    notes = models.TextField(blank=True)
    last_scanned_at = models.DateTimeField(null=True, blank=True)
    last_status = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["source_type", "name"]

    def __str__(self):
        return self.name


class CrawlRun(models.Model):
    STATUSES = [("running", "Running"), ("ok", "OK"), ("partial", "Partial"), ("failed", "Failed")]

    source = models.ForeignKey(Source, on_delete=models.CASCADE, related_name="runs")
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=STATUSES, default="running")
    discovered_count = models.PositiveIntegerField(default=0)
    published_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    log = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-started_at"]


class SourceDocument(models.Model):
    source = models.ForeignKey(Source, on_delete=models.CASCADE, related_name="documents")
    url = models.URLField(max_length=1000, unique=True)
    title = models.CharField(max_length=500, blank=True)
    classification = models.CharField(max_length=30, blank=True)
    content_hash = models.CharField(max_length=64, db_index=True)
    content_text = models.TextField(blank=True)
    excerpt = models.TextField(blank=True)
    links = models.JSONField(default=list, blank=True)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_fetched_at = models.DateTimeField(auto_now=True)
    http_etag = models.CharField(max_length=300, blank=True)
    http_last_modified = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-last_fetched_at"]


class DiscoverySignal(models.Model):
    STATUSES = [("new", "New"), ("resolved", "Resolved"), ("ignored", "Ignored"), ("review", "Needs review")]

    source = models.ForeignKey(Source, on_delete=models.CASCADE, related_name="signals")
    external_url = models.URLField(max_length=1000)
    headline = models.CharField(max_length=500)
    normalized_key = models.CharField(max_length=64, db_index=True)
    official_resolved_url = models.URLField(max_length=1000, blank=True)
    status = models.CharField(max_length=16, choices=STATUSES, default="new")
    detected_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["source", "external_url"], name="unique_signal_per_source")]
        ordering = ["-detected_at"]


class Job(models.Model):
    STATUSES = [
        ("draft", "Draft"),
        ("review", "Needs review"),
        ("published", "Published"),
        ("expired", "Expired"),
        ("cancelled", "Cancelled"),
    ]

    slug = models.SlugField(max_length=220, unique=True)
    title = models.CharField(max_length=320)
    organization = models.CharField(max_length=240)
    advertisement_no = models.CharField(max_length=120, blank=True)
    post_name = models.CharField(max_length=240, blank=True)
    summary = models.TextField(blank=True)
    vacancies = models.PositiveIntegerField(null=True, blank=True)
    qualifications = models.JSONField(default=list, blank=True)
    qualification_group = models.CharField(max_length=80, blank=True, db_index=True)
    accepted_disciplines = models.JSONField(default=list, blank=True)
    eligible_categories = models.JSONField(default=list, blank=True)
    eligible_genders = models.JSONField(default=list, blank=True)
    sector = models.CharField(max_length=80, blank=True, db_index=True)
    state = models.CharField(max_length=80, blank=True, db_index=True)
    location = models.CharField(max_length=160, blank=True)
    employment_type = models.CharField(max_length=80, default="Government", blank=True)
    salary = models.CharField(max_length=240, blank=True)
    age_limit = models.CharField(max_length=240, blank=True)
    min_age = models.PositiveSmallIntegerField(null=True, blank=True)
    max_age = models.PositiveSmallIntegerField(null=True, blank=True)
    age_as_on = models.DateField(null=True, blank=True)
    category_age_relaxation = models.JSONField(default=dict, blank=True)
    min_experience_months = models.PositiveIntegerField(default=0)
    application_fee = models.CharField(max_length=320, blank=True)
    fee_by_category = models.JSONField(default=dict, blank=True)
    selection_process = models.TextField(blank=True)
    application_start_date = models.DateField(null=True, blank=True)
    application_end_date = models.DateField(null=True, blank=True, db_index=True)
    exam_date = models.DateField(null=True, blank=True, db_index=True)
    admit_card_date = models.DateField(null=True, blank=True)
    result_date = models.DateField(null=True, blank=True)
    official_notification_url = models.URLField(max_length=1000)
    official_apply_url = models.URLField(max_length=1000, blank=True)
    official_website_url = models.URLField(max_length=1000, blank=True)
    source_url = models.URLField(max_length=1000)
    source_hash = models.CharField(max_length=64, db_index=True)
    discovered_via = models.CharField(max_length=160, blank=True)
    discovery_url = models.URLField(max_length=1000, blank=True)
    evidence_urls = models.JSONField(default=list, blank=True)
    verification_confidence = models.FloatField(default=0.0)
    verified_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=STATUSES, default="draft", db_index=True)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)
    change_version = models.PositiveIntegerField(default=1)
    is_featured = models.BooleanField(default=False)
    is_postponed = models.BooleanField(default=False)
    important_update = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-published_at", "application_end_date"]
        indexes = [
            models.Index(fields=["status", "application_end_date"]),
            models.Index(fields=["organization", "advertisement_no"]),
            models.Index(fields=["sector", "qualification_group", "state"]),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title)[:190] or "government-job"
            candidate, n = base, 2
            while Job.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
                candidate = f"{base}-{n}"
                n += 1
            self.slug = candidate
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("job-detail", kwargs={"slug": self.slug})

    @property
    def is_closing_soon(self):
        if not self.application_end_date:
            return False
        delta = (self.application_end_date - timezone.localdate()).days
        return 0 <= delta <= 7

    @property
    def days_left(self):
        if not self.application_end_date:
            return None
        return (self.application_end_date - timezone.localdate()).days

    @property
    def is_active(self):
        return self.status == "published" and (not self.application_end_date or self.application_end_date >= timezone.localdate())


class AdmitCard(models.Model):
    STATUSES = [("review", "Needs review"), ("published", "Published"), ("archived", "Archived")]

    slug = models.SlugField(max_length=220, unique=True)
    title = models.CharField(max_length=320)
    organization = models.CharField(max_length=240)
    exam_name = models.CharField(max_length=240, blank=True)
    release_date = models.DateField(null=True, blank=True)
    exam_date = models.CharField(max_length=180, blank=True)
    official_url = models.URLField(max_length=1000)
    source_url = models.URLField(max_length=1000)
    source_hash = models.CharField(max_length=64)
    verification_confidence = models.FloatField(default=0)
    verified_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=STATUSES, default="review")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-release_date", "-created_at"]

    def __str__(self):
        return self.title


class Result(models.Model):
    STATUSES = [("review", "Needs review"), ("published", "Published"), ("archived", "Archived")]

    slug = models.SlugField(max_length=220, unique=True)
    title = models.CharField(max_length=320)
    organization = models.CharField(max_length=240)
    exam_name = models.CharField(max_length=240, blank=True)
    result_date = models.DateField(null=True, blank=True)
    official_url = models.URLField(max_length=1000)
    source_url = models.URLField(max_length=1000)
    source_hash = models.CharField(max_length=64)
    verification_confidence = models.FloatField(default=0)
    verified_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=STATUSES, default="review")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-result_date", "-created_at"]

    def __str__(self):
        return self.title


class ChangeEvent(models.Model):
    object_type = models.CharField(max_length=30)
    object_pk = models.PositiveBigIntegerField()
    title = models.CharField(max_length=320)
    field_changes = models.JSONField(default=dict)
    source_url = models.URLField(max_length=1000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class UserPreference(models.Model):
    CATEGORIES = [
        ("General", "General"),
        ("EWS", "EWS"),
        ("OBC", "OBC"),
        ("SC", "SC"),
        ("ST", "ST"),
        ("PwBD", "PwBD"),
        ("Other", "Other"),
    ]
    LANGUAGES = [("en", "English"), ("hi", "हिन्दी")]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="job_preferences")
    education = models.CharField(max_length=80, blank=True)
    discipline = models.CharField(max_length=160, blank=True)
    state = models.CharField(max_length=80, blank=True)
    category = models.CharField(max_length=20, choices=CATEGORIES, default="General")
    date_of_birth = models.DateField(null=True, blank=True)
    experience_months = models.PositiveIntegerField(default=0)
    preferred_qualifications = models.JSONField(default=list, blank=True)
    preferred_sectors = models.JSONField(default=list, blank=True)
    preferred_states = models.JSONField(default=list, blank=True)
    language = models.CharField(max_length=4, choices=LANGUAGES, default="en")
    email_alerts = models.BooleanField(default=True)
    push_alerts = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Preferences for {self.user}"


class SavedJob(models.Model):
    STATUSES = [
        ("saved", "Saved"),
        ("applied", "Applied"),
        ("exam", "Exam scheduled"),
        ("result", "Result / completed"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="saved_jobs")
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="saved_by")
    status = models.CharField(max_length=16, choices=STATUSES, default="saved")
    notes = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "job"], name="unique_saved_job")]
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.user}: {self.job}"


class AlertSubscription(models.Model):
    FREQUENCIES = [("instant", "Instant"), ("daily", "Daily digest")]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="job_alerts")
    email = models.EmailField()
    qualifications = models.JSONField(default=list, blank=True)
    sectors = models.JSONField(default=list, blank=True)
    states = models.JSONField(default=list, blank=True)
    keywords = models.JSONField(default=list, blank=True)
    frequency = models.CharField(max_length=12, choices=FREQUENCIES, default="daily")
    confirmed = models.BooleanField(default=False)
    active = models.BooleanField(default=False)
    last_sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["active", "frequency"])]

    def __str__(self):
        return f"{self.email} ({self.frequency})"


class ExamEvent(models.Model):
    EVENT_TYPES = [
        ("apply_start", "Application starts"),
        ("apply_end", "Application deadline"),
        ("exam", "Exam"),
        ("admit", "Admit card"),
        ("result", "Result"),
    ]

    job = models.ForeignKey(Job, null=True, blank=True, on_delete=models.CASCADE, related_name="exam_events")
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES)
    title = models.CharField(max_length=320)
    organization = models.CharField(max_length=240, blank=True)
    event_date = models.DateField(db_index=True)
    official_url = models.URLField(max_length=1000, blank=True)
    auto_generated = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["event_date", "title"]
        constraints = [models.UniqueConstraint(fields=["job", "event_type", "event_date"], name="unique_job_exam_event")]

    def __str__(self):
        return f"{self.event_date}: {self.title}"


class SearchQuery(models.Model):
    query = models.CharField(max_length=240)
    normalized = models.CharField(max_length=240, unique=True)
    count = models.PositiveIntegerField(default=1)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-count", "-last_seen_at"]

    def __str__(self):
        return self.query


class AnalyticsEvent(models.Model):
    EVENT_TYPES = [
        ("view", "Job view"),
        ("search", "Search"),
        ("apply_click", "Apply click"),
        ("notification_click", "Notification click"),
        ("website_click", "Official website click"),
        ("save", "Save job"),
        ("alert_signup", "Alert signup"),
        ("eligibility", "Eligibility check"),
    ]

    event_type = models.CharField(max_length=32, choices=EVENT_TYPES, db_index=True)
    job = models.ForeignKey(Job, null=True, blank=True, on_delete=models.SET_NULL, related_name="analytics_events")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    session_key = models.CharField(max_length=64, blank=True, db_index=True)
    path = models.CharField(max_length=500, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["event_type", "created_at"])]


class SourceHealthCheck(models.Model):
    STATUSES = [("ok", "OK"), ("warn", "Warning"), ("fail", "Failed")]

    source = models.ForeignKey(Source, on_delete=models.CASCADE, related_name="health_checks")
    status = models.CharField(max_length=10, choices=STATUSES)
    http_status = models.PositiveSmallIntegerField(null=True, blank=True)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    message = models.CharField(max_length=500, blank=True)
    checked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-checked_at"]
        indexes = [models.Index(fields=["source", "-checked_at"])]


class LinkCheck(models.Model):
    KINDS = [("apply", "Apply URL"), ("notification", "Notification URL"), ("website", "Official website")]

    job = models.ForeignKey(Job, null=True, blank=True, on_delete=models.CASCADE, related_name="link_checks")
    url = models.URLField(max_length=1000)
    kind = models.CharField(max_length=20, choices=KINDS)
    ok = models.BooleanField(default=False)
    http_status = models.PositiveSmallIntegerField(null=True, blank=True)
    message = models.CharField(max_length=500, blank=True)
    checked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-checked_at"]
        indexes = [models.Index(fields=["job", "kind", "-checked_at"])]


class WebPushSubscription(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="web_push_subscriptions")
    endpoint = models.URLField(max_length=1200, unique=True)
    p256dh = models.CharField(max_length=300)
    auth = models.CharField(max_length=200)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.endpoint[:80]


class NotificationDelivery(models.Model):
    CHANNELS = [("email", "Email"), ("push", "Push")]
    STATUSES = [("sent", "Sent"), ("failed", "Failed"), ("skipped", "Skipped")]

    subscription = models.ForeignKey(AlertSubscription, null=True, blank=True, on_delete=models.SET_NULL)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    job = models.ForeignKey(Job, null=True, blank=True, on_delete=models.SET_NULL)
    channel = models.CharField(max_length=12, choices=CHANNELS)
    notification_type = models.CharField(max_length=40)
    dedupe_key = models.CharField(max_length=180, unique=True)
    status = models.CharField(max_length=12, choices=STATUSES)
    detail = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
