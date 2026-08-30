from django.contrib import admin
from .models import (
    Source, CrawlRun, SourceDocument, DiscoverySignal, Job, AdmitCard, Result, ChangeEvent,
    UserPreference, SavedJob, AlertSubscription, ExamEvent, SearchQuery, AnalyticsEvent,
    SourceHealthCheck, LinkCheck, WebPushSubscription, NotificationDelivery,
)


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ("name", "source_type", "enabled", "trust_score", "last_scanned_at", "last_status")
    list_filter = ("source_type", "enabled")
    search_fields = ("name", "base_url", "entry_url")


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ("title", "organization", "qualification_group", "sector", "application_end_date", "verification_confidence", "change_version", "status")
    list_filter = ("status", "qualification_group", "sector", "state", "is_featured")
    search_fields = ("title", "organization", "advertisement_no", "post_name")
    readonly_fields = ("source_hash", "first_seen_at", "updated_at", "verified_at", "published_at", "change_version")
    actions = ["publish_selected", "send_to_review"]
    fieldsets = (
        ("Identity", {"fields": ("slug", "title", "organization", "advertisement_no", "post_name", "summary", "status", "is_featured", "is_postponed", "important_update")}),
        ("Eligibility", {"fields": ("vacancies", "qualifications", "qualification_group", "accepted_disciplines", "eligible_categories", "eligible_genders", "age_limit", "min_age", "max_age", "age_as_on", "category_age_relaxation", "min_experience_months")}),
        ("Classification", {"fields": ("sector", "state", "location", "employment_type")}),
        ("Compensation & fee", {"fields": ("salary", "application_fee", "fee_by_category", "selection_process")}),
        ("Dates", {"fields": ("application_start_date", "application_end_date", "exam_date", "admit_card_date", "result_date")}),
        ("Official sources", {"fields": ("official_notification_url", "official_apply_url", "official_website_url", "source_url", "source_hash", "evidence_urls", "discovered_via", "discovery_url")}),
        ("Verification", {"fields": ("verification_confidence", "verified_at", "published_at", "first_seen_at", "updated_at", "change_version")}),
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        from portal.pipeline.publisher import sync_exam_events
        sync_exam_events(obj)

    @admin.action(description="Publish selected verified jobs")
    def publish_selected(self, request, queryset):
        from django.utils import timezone
        queryset.filter(verification_confidence__gte=0.90).update(status="published", published_at=timezone.now())

    @admin.action(description="Send selected jobs to review")
    def send_to_review(self, request, queryset):
        queryset.update(status="review")


@admin.register(UserPreference)
class UserPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "education", "state", "category", "language", "email_alerts", "push_alerts")
    search_fields = ("user__username", "user__email", "discipline")


@admin.register(SavedJob)
class SavedJobAdmin(admin.ModelAdmin):
    list_display = ("user", "job", "status", "updated_at")
    list_filter = ("status",)
    search_fields = ("user__username", "job__title")


@admin.register(AlertSubscription)
class AlertSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("email", "frequency", "confirmed", "active", "user", "last_sent_at", "created_at")
    list_filter = ("frequency", "confirmed", "active")
    search_fields = ("email", "user__username")


@admin.register(ExamEvent)
class ExamEventAdmin(admin.ModelAdmin):
    list_display = ("event_date", "event_type", "organization", "title", "auto_generated")
    list_filter = ("event_type", "auto_generated")
    search_fields = ("title", "organization")


@admin.register(LinkCheck)
class LinkCheckAdmin(admin.ModelAdmin):
    list_display = ("job", "kind", "ok", "http_status", "checked_at")
    list_filter = ("kind", "ok")
    search_fields = ("job__title", "url")


@admin.register(SourceHealthCheck)
class SourceHealthCheckAdmin(admin.ModelAdmin):
    list_display = ("source", "status", "http_status", "latency_ms", "checked_at")
    list_filter = ("status",)


for model in (
    CrawlRun, SourceDocument, DiscoverySignal, AdmitCard, Result, ChangeEvent,
    SearchQuery, AnalyticsEvent, WebPushSubscription, NotificationDelivery,
):
    admin.site.register(model)
