from __future__ import annotations
from urllib.parse import urlparse
from django.utils import timezone
from portal.models import Source, CrawlRun, SourceDocument, DiscoverySignal
from .fetch import fetch
from .classify import classify
from .dedupe import normalized_key
from .publisher import upsert_job, upsert_simple_notice, apply_status_notice

INTEREST = ("recruit", "vacan", "advert", "apply", "notice", "admit", "result", "merit", "score", "exam")

def _same_domain(a,b):
    x=(urlparse(a).hostname or "").lower(); y=(urlparse(b).hostname or "").lower()
    return x==y or x.endswith("."+y) or y.endswith("."+x)

def _candidate_links(fetched, source):
    scored=[]
    for link in fetched.links:
        label=(link.get("label") or "").lower(); context=(link.get("context") or "").lower(); url=(link.get("url") or "")
        if source.source_type=="official" and not _same_domain(url,source.base_url): continue
        blob=label+" "+context+" "+url.lower()
        score=sum(k in blob for k in INTEREST)
        score += 2 if any(k in blob for k in ["view more","more details","read more","click here","cen-","crp-"]) else 0
        score += 1 if url.lower().endswith(".pdf") else 0
        score += 1 if any(y in blob for y in ["2026","2027"]) else 0
        if score: scored.append((score,url,(link.get("context") or link.get("label") or "")[:500]))
    scored.sort(reverse=True)
    seen=set(); out=[]
    for _,url,label in scored:
        if url not in seen:
            seen.add(url); out.append((url,label))
        if len(out)>=source.max_links_per_scan: break
    return out

def scan_source(source: Source):
    run=CrawlRun.objects.create(source=source)
    log=[]; pub=upd=err=0
    try:
        entry=fetch(source.entry_url, source.user_agent)
        links=_candidate_links(entry,source)
        for url,label in links:
            try:
                if source.source_type=="discovery":
                    DiscoverySignal.objects.get_or_create(source=source,external_url=url,defaults={"headline":label[:500] or url,"normalized_key":normalized_key(label,url)})
                    continue
                f=fetch(url,source.user_agent)
                effective_title = label if (not f.title or f.title == "PDF notification") else f.title
                kind,score=classify(effective_title,f.text)
                body=f.text if source.allow_store_body else ""
                doc,created=SourceDocument.objects.update_or_create(url=f.url,defaults={"source":source,"title":effective_title[:500],"classification":kind,"content_hash":f.content_hash,"content_text":body,"excerpt":f.text[:8000],"links":f.links[:300],"http_etag":f.etag,"http_last_modified":f.last_modified})
                status_notice, status_job = apply_status_notice(doc, text_override=f.text)
                if status_notice:
                    upd += int(status_job is not None)
                elif kind=="job":
                    _,c,u=upsert_job(doc, text_override=f.text); pub += int(c); upd += int(u)
                elif kind in {"admit_card","result"}:
                    upsert_simple_notice(doc,kind,text_override=f.text); pub += 1 if created else 0
            except Exception as exc:
                err+=1; log.append({"url":url,"error":str(exc)[:500]})
        source.last_scanned_at=timezone.now(); source.last_status="ok" if not err else f"partial: {err} errors"; source.save(update_fields=["last_scanned_at","last_status"])
        run.status="ok" if not err else "partial"
        run.discovered_count=len(links); run.published_count=pub; run.updated_count=upd; run.error_count=err; run.log=log
    except Exception as exc:
        run.status="failed"; run.error_count=1; run.log=[{"error":str(exc)[:1000]}]
        source.last_scanned_at=timezone.now(); source.last_status=f"failed: {str(exc)[:90]}"; source.save(update_fields=["last_scanned_at","last_status"])
    run.completed_at=timezone.now(); run.save()
    return run
