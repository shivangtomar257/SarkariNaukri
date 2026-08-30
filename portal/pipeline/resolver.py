from urllib.parse import urlparse
from portal.models import DiscoverySignal, SourceDocument
from .dedupe import similarity

def reconcile_signal(signal: DiscoverySignal):
    candidates=SourceDocument.objects.filter(source__source_type="official").order_by("-last_fetched_at")[:500]
    best=None; best_score=0.0
    for doc in candidates:
        score=max(similarity(signal.headline,doc.title), similarity(signal.headline,doc.excerpt[:300]))
        if score>best_score: best,best_score=doc,score
    if best and best_score>=0.56:
        signal.official_resolved_url=best.url; signal.status="resolved"; signal.save(update_fields=["official_resolved_url","status"])
        return best,best_score
    signal.status="review"; signal.save(update_fields=["status"])
    return None,best_score
