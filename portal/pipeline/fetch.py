from __future__ import annotations
import hashlib, io, ipaddress, socket, time
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader

MAX_BYTES = 12 * 1024 * 1024

@dataclass
class Fetched:
    url: str
    title: str
    text: str
    links: list[dict]
    content_hash: str
    etag: str = ""
    last_modified: str = ""
    content_type: str = ""


def _public_host(hostname: str) -> bool:
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return False
    for info in infos:
        addr = ipaddress.ip_address(info[4][0])
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved or addr.is_multicast:
            return False
    return True


def validate_public_url(url: str) -> None:
    p = urlparse(url)
    if p.scheme not in {"http","https"} or not p.hostname:
        raise ValueError("Only public http(s) URLs are allowed")
    if not _public_host(p.hostname):
        raise ValueError("Private/reserved network URLs are blocked")

@lru_cache(maxsize=128)
def _robots(origin: str, user_agent: str):
    parser = RobotFileParser()
    robots_url = origin.rstrip("/") + "/robots.txt"
    try:
        r = httpx.get(robots_url, headers={"User-Agent": user_agent}, timeout=10, follow_redirects=True)
        if r.status_code >= 400:
            return None
        parser.set_url(robots_url)
        parser.parse(r.text.splitlines())
        return parser
    except Exception:
        return None

def robots_allowed(url: str, user_agent: str) -> bool:
    p = urlparse(url)
    parser = _robots(f"{p.scheme}://{p.netloc}", user_agent)
    return bool(parser and parser.can_fetch(user_agent, url))


def _pdf_text(content: bytes) -> str:
    reader = PdfReader(io.BytesIO(content))
    chunks = []
    for page in reader.pages[:120]:
        chunks.append(page.extract_text() or "")
    return "\n".join(chunks)


def fetch(url: str, user_agent: str, timeout: int = 30) -> Fetched:
    validate_public_url(url)
    if not robots_allowed(url, user_agent):
        raise PermissionError(f"robots.txt does not allow automated fetch: {url}")
    headers = {"User-Agent": user_agent, "Accept": "text/html,application/pdf;q=0.9,*/*;q=0.8"}
    last_error = None
    for attempt in range(3):
        try:
            with httpx.Client(headers=headers, timeout=timeout, follow_redirects=True) as client:
                with client.stream("GET", url) as resp:
                    resp.raise_for_status()
                    chunks, total = [], 0
                    for chunk in resp.iter_bytes():
                        total += len(chunk)
                        if total > MAX_BYTES: raise ValueError("Document exceeds safe fetch size")
                        chunks.append(chunk)
                    content = b"".join(chunks)
                    final_url = str(resp.url)
                    ctype = resp.headers.get("content-type", "").lower()
                    etag = resp.headers.get("etag", "")
                    modified = resp.headers.get("last-modified", "")
            digest = hashlib.sha256(content).hexdigest()
            if "pdf" in ctype or final_url.lower().endswith(".pdf"):
                text = _pdf_text(content)
                return Fetched(final_url, "PDF notification", text[:1_500_000], [], digest, etag, modified, ctype)
            soup = BeautifulSoup(content, "html.parser")
            for node in soup(["script","style","noscript","svg"]): node.decompose()
            title = soup.title.get_text(" ", strip=True) if soup.title else ""
            text = "\n".join(line.strip() for line in soup.get_text("\n").splitlines() if line.strip())
            links = []
            seen = set()
            for a in soup.find_all("a", href=True):
                href = urljoin(final_url, a.get("href"))
                label = a.get_text(" ", strip=True)[:300]
                parent = a.find_parent(["tr","li","article","section","div"])
                context = parent.get_text(" ", strip=True)[:900] if parent else label
                if href.startswith(("http://","https://")) and href not in seen:
                    seen.add(href); links.append({"url": href, "label": label, "context": context})
            return Fetched(final_url, title[:500], text[:1_500_000], links[:1000], digest, etag, modified, ctype)
        except Exception as exc:
            last_error = exc
            if attempt < 2: time.sleep(1.25 * (attempt + 1))
    raise last_error
