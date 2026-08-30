import hashlib, re
from difflib import SequenceMatcher
from .extract import clean

def normalized_key(*parts: str) -> str:
    blob = " ".join(clean(p).lower() for p in parts if p)
    blob = re.sub(r"[^a-z0-9]+", " ", blob)
    tokens = [t for t in blob.split() if len(t) > 2 and t not in {"recruitment","notification","apply","online","jobs","job"}]
    return hashlib.sha256(" ".join(tokens[:40]).encode()).hexdigest()

def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, clean(a).lower(), clean(b).lower()).ratio()
