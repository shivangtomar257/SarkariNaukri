# Production deployment

## One-time server setup
Use a Linux VPS or compatible Docker host. Point the chosen domain's DNS A/AAAA records to the server.

1. Copy `.env.example` to `.env`.
2. Set a strong `DJANGO_SECRET_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `SITE_URL` and production PostgreSQL values.
3. Configure SMTP if you want account/alert email delivery.
4. Configure optional VAPID keys for browser push, OpenAI for AI extraction/discovery, Google service-account credentials for indexing notifications and Sentry for error reporting.
5. Run:
   ```bash
   docker compose -f docker-compose.prod.yml up -d --build
   ```
6. Create the first administrator once:
   ```bash
   docker compose -f docker-compose.prod.yml exec web python manage.py createsuperuser
   ```
7. Run an immediate initial official-source scan:
   ```bash
   docker compose -f docker-compose.prod.yml exec web python manage.py run_pipeline --type official
   ```

Caddy provisions HTTPS automatically when DNS is correctly pointed to the host. Only the web container runs migrations/collectstatic on startup; worker/beat containers do not race migrations.

## Production endpoints
- `/` public site
- `/jobs/` jobs/search
- `/admit-cards/`
- `/results/`
- `/exam-calendar/`
- `/account/` user dashboard
- `/ops/` staff operations
- `/analytics/` staff analytics
- `/admin/` Django Admin
- `/healthz/` health check
- `/sitemap.xml`
- `/feed/jobs.xml`

## Email alerts
Set SMTP environment variables from `.env.example`. Alert subscriptions are not activated until the user follows the signed confirmation link.

## Browser push
Generate/obtain VAPID keys and set the VAPID public/private values and subject. The public key is sent to the browser; keep the private key secret.

## Staff TOTP gate
Set `ADMIN_TOTP_ENABLED=1` and an appropriate secret to require the additional TOTP challenge on staff-facing operations/analytics flows. This does not replace Django authentication; it adds a second gate.

## Google indexing notifications
Enable only after supplying the required service-account configuration and after confirming that your use of the Indexing API is appropriate for the page type. The application limits submissions to active public job-detail URLs with an official apply URL.

## Backups and monitoring
- Daily compressed PostgreSQL backups are retained for 14 days in the backup volume.
- Configure `SENTRY_DSN` for application error reporting.
- Monitor `/healthz/`, Celery worker health, backup completion, source-health results and link-health results.

## Deployment validation checklist
Before public launch, run inside the deployed environment:
```bash
python manage.py check --deploy
python manage.py migrate --plan
pytest
```
Then smoke-test registration, alert confirmation, save/app tracker, eligibility, staff dashboards, a manual source scan and email delivery with production credentials.
