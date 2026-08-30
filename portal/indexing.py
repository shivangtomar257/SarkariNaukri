from __future__ import annotations

import json
import httpx
from django.conf import settings


def notify_google(url: str, action: str = "URL_UPDATED") -> tuple[bool, str]:
    """Optional Google Indexing API call. Requires Search Console access for the service account."""
    if not settings.GOOGLE_INDEXING_ENABLED or not settings.GOOGLE_INDEXING_SERVICE_ACCOUNT_JSON:
        return False, "disabled"
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request
        info = json.loads(settings.GOOGLE_INDEXING_SERVICE_ACCOUNT_JSON)
        credentials = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/indexing"]
        )
        credentials.refresh(Request())
        r = httpx.post(
            "https://indexing.googleapis.com/v3/urlNotifications:publish",
            headers={"Authorization": f"Bearer {credentials.token}", "Content-Type": "application/json"},
            json={"url": url, "type": action},
            timeout=30,
        )
        r.raise_for_status()
        return True, "submitted"
    except Exception as exc:
        return False, str(exc)[:400]
