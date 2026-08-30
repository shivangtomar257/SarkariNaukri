from __future__ import annotations
import json
from urllib.parse import urlparse
import httpx
from django.conf import settings
from portal.models import Source, SourceDocument
from .fetch import fetch
from .classify import classify
from .publisher import upsert_job, upsert_simple_notice

SCHEMA = {
    "type":"object","additionalProperties":False,
    "properties":{"candidates":{"type":"array","maxItems":30,"items":{
        "type":"object","additionalProperties":False,
        "properties":{"title":{"type":"string"},"url":{"type":"string"},"organization":{"type":"string"}},
        "required":["title","url","organization"]
    }}},
    "required":["candidates"]
}

def _known_official_host(host: str) -> Source | None:
    host=host.lower()
    for source in Source.objects.filter(source_type="official"):
        base=(urlparse(source.base_url).hostname or "").lower()
        if host == base or host.endswith("."+base) or base.endswith("."+host): return source
    return None

def _government_host(host: str) -> bool:
    h=host.lower().rstrip(".")
    return h.endswith(".gov.in") or h.endswith(".nic.in") or h in {"gov.in","nic.in"}

def discover_and_ingest() -> dict:
    if not settings.AI_WEB_DISCOVERY_ENABLED or not settings.OPENAI_API_KEY:
        return {"skipped":"AI web discovery disabled or API key absent"}
    prompt = (
        "Find Indian government/public recruiting-authority job recruitment, admit-card, and recruitment-result notices "
        "announced or materially updated in approximately the last 72 hours. Discovery may use the public web, but the returned URL MUST be the official recruiting authority/government source, not a job aggregator, news story, coaching site, or social post. "
        "Prefer direct notification/detail pages. Return at most 30 candidates. Do not invent URLs."
    )
    payload={
        "model":settings.WEB_DISCOVERY_MODEL,
        "tools":[{"type":"web_search_preview","search_context_size":"medium","user_location":{"type":"approximate","country":"IN","timezone":"Asia/Kolkata"}}],
        "input":prompt,
        "text":{"format":{"type":"json_schema","name":"official_recruitment_candidates","strict":True,"schema":SCHEMA}},
    }
    r=httpx.post("https://api.openai.com/v1/responses",headers={"Authorization":f"Bearer {settings.OPENAI_API_KEY}","Content-Type":"application/json"},json=payload,timeout=120)
    r.raise_for_status(); response=r.json(); raw=response.get("output_text")
    if not raw:
        for item in response.get("output",[]):
            if item.get("type")=="message":
                for c in item.get("content",[]):
                    if c.get("type")=="output_text" and c.get("text"): raw=c["text"]
    parsed=json.loads(raw or '{"candidates":[]}')
    processed=published=reviewed=rejected=0
    for candidate in parsed.get("candidates",[]):
        url=(candidate.get("url") or "").strip(); host=(urlparse(url).hostname or "").lower()
        if not host: rejected+=1; continue
        source=_known_official_host(host)
        if not source and not _government_host(host):
            rejected+=1; continue
        if not source:
            source,_=Source.objects.get_or_create(
                name=f"AI-discovered official: {host}",
                defaults={"source_type":"official","base_url":f"https://{host}","entry_url":url,"enabled":False,"trust_score":0.95,"allow_store_body":False,"notes":"Auto-created from web discovery. Disabled for recurring crawl until explicitly curated; candidate URLs can still be processed once."},
            )
        try:
            f=fetch(url,source.user_agent); kind,_=classify(candidate.get("title") or f.title,f.text)
            title=(candidate.get("title") or f.title)[:500]
            doc,_=SourceDocument.objects.update_or_create(url=f.url,defaults={"source":source,"title":title,"classification":kind,"content_hash":f.content_hash,"content_text":"","excerpt":f.text[:8000],"links":f.links[:300],"http_etag":f.etag,"http_last_modified":f.last_modified})
            processed+=1
            if kind=="job":
                obj,created,changed=upsert_job(doc,discovered_via="AI official-web discovery",discovery_url=url,text_override=f.text)
                published += int(obj.status=="published"); reviewed += int(obj.status=="review")
            elif kind in {"admit_card","result"}:
                obj,_=upsert_simple_notice(doc,kind,text_override=f.text); published += int(obj.status=="published"); reviewed += int(obj.status=="review")
        except Exception:
            rejected+=1
    return {"processed":processed,"published":published,"review":reviewed,"rejected":rejected}
