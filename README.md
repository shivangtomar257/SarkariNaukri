# SarkariNaukri Autopilot — Enhanced Production Build

A production-oriented, self-updating Indian government-jobs portal. It combines official-source ingestion, scheduled background automation, a public jobs product, user personalization, eligibility assistance, notifications, SEO infrastructure and an operations/admin layer.

## Public product included
- Homepage top navigation/cards: **Latest Jobs, Closing Soon, Admit Cards, Results, Exam Calendar**.
- Qualification, sector, state and organization landing pages.
- Advanced job search: keyword, qualification, state, sector, organization, age, experience, discipline, category and structured gender restrictions.
- Job detail pages with official links, important dates, salary/fee/age/qualification facts, source verification time, change history, related jobs and recently viewed jobs.
- **Can I Apply?** eligibility assistant using structured education, discipline, age, category, experience and notice restrictions. It is advisory and always points users back to the official notification for final eligibility.
- Category-specific application-fee lookup.
- Accounts, saved jobs and application tracking: Saved → Applied → Exam → Result.
- User preference profile and personalized recommendations.
- Email alerts with double opt-in, daily/instant delivery and 7/3/1/0-day deadline reminders.
- Optional browser push notifications.
- English/Hindi interface labels.
- Dark mode, mobile navigation, accessible skip link and responsive layout.
- PWA manifest/service worker and install prompt.
- RSS feed and calendar `.ics` export.

## Automation included
- PostgreSQL-backed Django application.
- Redis + Celery workers and Celery Beat scheduler.
- Official-source HTML/PDF ingestion with robots checks, SSRF protections, retries and content-size limits.
- Optional discovery sources used as **signals only**; competitor article bodies are not republished.
- Optional OpenAI official-web discovery that only feeds official authority URLs into the verification pipeline.
- Deterministic fact extraction plus optional structured AI extraction.
- Duplicate controls, official-source confidence gate and review queue for uncertain records.
- Source-content hashes and field-level change history.
- Deadline extension/update detection, cancellation/postponement handling and automatic expiry.
- Admit-card/result classification and exam-calendar synchronization.
- Source-health checks and official-link monitoring.
- Search/click/view analytics and staff analytics dashboard.
- Optional Google indexing notifications for eligible active job-detail URLs.
- Daily PostgreSQL backups, Sentry hook, health endpoint and CI configuration.
- Cache-backed rate limiting, security headers/CSP, secure cookies and optional staff TOTP gate.

## Quick local start
```bash
cp .env.example .env
# For localhost set:
# DJANGO_DEBUG=1
# SECURE_SSL_REDIRECT=0
# SESSION_COOKIE_SECURE=0
# CSRF_COOKIE_SECURE=0

docker compose up --build
```

Create the first admin:
```bash
docker compose exec web python manage.py createsuperuser
```

Run one official-source scan immediately:
```bash
docker compose exec web python manage.py run_pipeline --type official
```

Open:
- Site: `http://localhost:8000/`
- Operations: `http://localhost:8000/ops/`
- Analytics: `http://localhost:8000/analytics/`
- Admin: `http://localhost:8000/admin/`
- Health: `http://localhost:8000/healthz/`

## Background schedule
- Official source scans: every 4 hours
- Optional discovery sources: every 6 hours
- Optional official-web discovery: every 6 hours
- Discovery reconciliation: hourly
- Instant job alerts: hourly
- Important update alerts: hourly
- Deadline alerts: every 6 hours
- Daily digest: daily at 19:15
- Source-health checks: every 2 hours
- Official-link checks: every 6 hours
- Search-engine indexing submission: every 2 hours when enabled
- Expiry/calendar rebuild/reverification: nightly/daily
- Operational-history cleanup: weekly

## One-time production requirements
A live autonomous website still needs real infrastructure values once: domain/DNS, PostgreSQL/Redis credentials, an admin account, SMTP credentials for email, and optional OpenAI/VAPID/Google Indexing/Sentry credentials. Once deployed, Celery workers and Beat run the update loop without manual HTML editing.

See:
- `docs/PRODUCT_FEATURES.md`
- `docs/AUTOMATION.md`
- `docs/DEPLOYMENT.md`
- `docs/SOURCE_POLICY.md`
