from django.contrib.auth import views as auth_views
from django.urls import path
from . import views
from .views import LatestJobsFeed

urlpatterns = [
    path("", views.home, name="home"),
    path("jobs/", views.jobs, name="jobs"),
    path("jobs/<slug:slug>/", views.job_detail, name="job-detail"),
    path("qualification/<slug:slug>/", views.qualification_jobs, name="qualification-jobs"),
    path("sector/<slug:slug>/", views.sector_jobs, name="sector-jobs"),
    path("state/<slug:slug>/", views.state_jobs, name="state-jobs"),
    path("organization/<slug:slug>/", views.organization_jobs, name="organization-jobs"),
    path("admit-cards/", views.admit_cards, name="admit-cards"),
    path("results/", views.results, name="results"),
    path("exam-calendar/", views.exam_calendar, name="exam-calendar"),
    path("exam-calendar.ics", views.calendar_ics, name="calendar-ics"),
    path("source-policy/", views.policy, name="policy"),
    path("language/<str:code>/", views.set_language, name="set-language"),

    path("accounts/signup/", views.signup, name="signup"),
    path("accounts/login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("account/", views.account_dashboard, name="account-dashboard"),
    path("account/profile/", views.profile, name="profile"),
    path("account/alerts/", views.alerts, name="alerts"),
    path("account/alerts/<int:alert_id>/delete/", views.delete_alert, name="delete-alert"),
    path("alerts/subscribe/", views.public_alert_signup, name="public-alert-signup"),
    path("alerts/confirm/<path:token>/", views.confirm_alert, name="confirm-alert"),
    path("alerts/unsubscribe/<path:token>/", views.unsubscribe_alert, name="unsubscribe-alert"),
    path("jobs/<int:job_id>/save/", views.save_job, name="save-job"),
    path("tracker/<int:saved_id>/update/", views.update_tracker, name="update-tracker"),
    path("push/subscribe/", views.webpush_subscribe, name="webpush-subscribe"),

    path("out/<int:job_id>/<str:kind>/", views.external_redirect, name="external-redirect"),
    path("api/v1/jobs/", views.api_jobs, name="api-jobs"),
    path("api/v1/autocomplete/", views.autocomplete, name="autocomplete"),
    path("healthz/", views.health, name="health"),
    path("robots.txt", views.robots_txt, name="robots"),
    path("service-worker.js", views.service_worker, name="service-worker"),
    path("feed/jobs.xml", LatestJobsFeed(), name="jobs-feed"),

    path("staff-2fa/", views.staff_2fa, name="staff-2fa"),
    path("ops/", views.ops, name="ops"),
    path("analytics/", views.analytics_dashboard, name="analytics-dashboard"),
]
