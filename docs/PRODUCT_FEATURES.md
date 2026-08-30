# Product features

## Homepage / discovery
The homepage prioritizes the five high-intent destinations: Latest Jobs, Closing Soon, Admit Cards, Results and Exam Calendar. It also surfaces personalized recommendations for signed-in users, qualification categories, state/sector/organization browsing, recently updated notices, upcoming exam events and trending searches.

## Search and landing pages
The jobs view supports keyword, qualification, state, sector, organization, closing-soon, recently-updated, age, experience, discipline, category and structured gender-restriction filters. SEO-oriented landing routes exist for qualification, state, sector and organization pages. Query-heavy filter combinations are not intended to become independent canonical landing pages.

## Job detail intelligence
Each job page can show official notification/apply/website links, verification timestamp, source history, important dates, age range, experience, disciplines, structured category/gender restrictions, fees, salary/pay scale, update/correction history, related jobs and recently viewed jobs.

### Can I Apply?
The eligibility engine compares structured notice fields with user-supplied education, discipline, date of birth, category and experience. Results are deliberately phrased as `appears eligible`, `likely not eligible`, or `needs verification`; the official notice remains authoritative. The engine handles category age-relaxation values when they are structured in the source data.

## User account
Users can save jobs, track application state, store preference filters, receive recommendations and manage alerts. Application tracker states are Saved, Applied, Exam and Result.

## Alerts
Alert subscriptions use double opt-in. Filters can be matched to newly published jobs and deadline reminders. Delivery history is deduplicated so the same notification is not repeatedly sent. Optional browser push subscriptions are supported with VAPID credentials.

## Exam calendar
Structured application/exam/admit-card/result dates are synchronized into calendar events. Users can browse the calendar and export an ICS feed.

## Bilingual / accessibility / PWA
Core interface labels are available in English and Hindi. Theme preference is stored locally for dark mode. The site includes responsive navigation, keyboard-oriented skip navigation, a web-app manifest, service worker and install prompt.

## Analytics and operations
The platform records selected search, job-view and official-link click events. Staff dashboards expose operational status, source-health checks, link-health checks, pending review items and aggregate analytics.

## SEO infrastructure
The project includes canonical handling, XML sitemaps, RSS, robots output, structured job metadata only on appropriate active job-detail pages and optional Google indexing notifications. Expired job pages are prevented from continuing to present active-job structured metadata.

## Security
Included controls cover secure cookies, HTTPS redirect settings, CSP/security headers, cache-backed request rate limiting, SSRF-aware crawler fetching, admin auditability, optional staff TOTP gate, secret-by-environment configuration and production backup/health infrastructure.
