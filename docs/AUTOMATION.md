# Automation design

## Hands-off publishing loop
1. Celery Beat schedules official scans every 4 hours.
2. Fetching checks robots rules and blocks private/reserved-network targets.
3. Official index pages are scored using link text plus nearby list/table context so generic links such as `View More` can still resolve to recruitment notices.
4. Candidate HTML/PDF content is hashed, classified and extracted in memory.
5. Deterministic extraction runs first; optional structured AI extraction can improve messy notices.
6. Publication requires an official source and the configured confidence/publishing gate. Uncertain/conflicting records stay in review.
7. Duplicate checks prevent the same advertisement from becoming multiple public jobs.
8. Re-fetches detect source changes and create field-level change events.
9. Cancellation/postponement/date-extension updates alter the existing record instead of creating a misleading duplicate.
10. Exam/admit/result dates synchronize into the exam calendar.
11. Closed jobs automatically expire.

## Discovery layer
Third-party job portals may be configured only as optional discovery signals after reviewing their current terms/robots rules. Their article bodies are not stored for republication. A signal must resolve to an official recruiting-authority document before it can pass the publishing gate.

Optional official-web discovery can also search broadly for recent government recruitment signals. It is constrained to return an official authority URL; the URL is then fetched and verified by the same normal pipeline.

## User automation
- Instant matching alerts: hourly.
- Important change alerts: hourly.
- Deadline reminders: 7, 3, 1 and 0 days before closing.
- Daily digest: scheduled daily.
- Notification deliveries use deduplication records.
- Alert email enrollment uses signed double-opt-in confirmation links and signed unsubscribe links.

## Operations automation
- Source health: every 2 hours.
- Published official links: every 6 hours.
- 401/403/429 responses are treated as automation-restricted/reachable warnings rather than automatically declaring a link broken, because many official portals block automated probes.
- URL indexing submission: every 2 hours when enabled and only for eligible active job pages.
- Calendar rebuild/expiry/reverification: nightly/daily.
- Old operational history cleanup: weekly.

## AI extraction
Set `OPENAI_API_KEY` to enable structured extraction. AI is not the source of truth: extracted values are tied to the official notice and publication is still confidence/official-source gated. Leaving the key blank keeps deterministic ingestion operational.
