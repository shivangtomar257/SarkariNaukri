from __future__ import annotations

import json
import re
from datetime import date
from urllib.parse import urlparse

import httpx
from dateutil import parser as date_parser
from django.conf import settings

QUALIFICATIONS = [
    ("10th Pass", ["10th", "matric", "matriculation"]),
    ("12th Pass", ["12th", "10+2", "intermediate", "senior secondary"]),
    ("ITI", ["iti", "industrial training institute"]),
    ("Diploma", ["diploma"]),
    ("Engineering", ["b.e.", "b.tech", "btech", "engineering degree", "bachelor of engineering"]),
    ("Post Graduate", ["post graduate", "postgraduate", "master's degree", "masters degree", "m.tech", "mba", "m.sc", "m.a."]),
    ("Graduate", ["graduate", "graduation", "bachelor's degree", "bachelors degree", "any degree"]),
]
GROUP_PRIORITY = ["Post Graduate", "Engineering", "Graduate", "Diploma", "ITI", "12th Pass", "10th Pass"]
STATES = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa", "Gujarat", "Haryana",
    "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur",
    "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana",
    "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal", "Delhi", "Jammu and Kashmir", "Ladakh", "Chandigarh",
]
SECTORS = {
    "Railway": ["railway", "rrb", "railways"],
    "Banking": ["bank", "ibps", "rbi", "sbi"],
    "SSC": ["staff selection commission", "ssc"],
    "Defence": ["army", "navy", "air force", "defence", "drdo"],
    "Police": ["police", "constable", "sub-inspector"],
    "Education": ["teacher", "professor", "lecturer", "school", "university"],
    "PSU": ["limited", "corporation", "psu", "public sector undertaking"],
}
DATE_LABELS = {
    "application_end_date": ["last date", "closing date", "last date for submission", "last date to apply", "online application end"],
    "application_start_date": ["starting date", "opening date", "online application start", "application begins"],
    "exam_date": ["date of examination", "exam date", "date of exam", "written examination"],
    "admit_card_date": ["admit card date", "admit card release", "hall ticket date"],
    "result_date": ["result date", "date of result", "result declaration"],
    "age_as_on": ["age as on", "cut-off date for age", "cutoff date for age"],
}


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _date_near_labels(text: str, labels: list[str]):
    for label in labels:
        m = re.search(rf"{re.escape(label)}[^\n:]{{0,80}}[:\-]?\s*([^\n]{{0,80}})", text, re.I)
        if not m:
            continue
        s = m.group(1)
        dm = re.search(
            r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4})",
            s,
            re.I,
        )
        if dm:
            try:
                dt = date_parser.parse(dm.group(1), dayfirst=True, fuzzy=True).date()
                if date(2020, 1, 1) <= dt <= date(2040, 12, 31):
                    return dt
            except Exception:
                pass
    return None


def _vacancies(text: str):
    patterns = [
        r"(?:total\s+)?(?:vacancies|vacancy|posts?)\s*[:\-]?\s*([\d,]{1,10})",
        r"([\d,]{1,10})\s+(?:vacancies|posts)\b",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            try:
                return int(m.group(1).replace(",", ""))
            except ValueError:
                pass
    return None


def _field(text: str, labels: list[str], max_chars=220):
    for label in labels:
        m = re.search(rf"{re.escape(label)}\s*[:\-]?\s*([^\n]{{3,{max_chars}}})", text, re.I)
        if m:
            return clean(m.group(1))[:max_chars]
    return ""


def _qualifications(text: str):
    lower = text.lower()
    found = []
    for group, needles in QUALIFICATIONS:
        if any(n in lower for n in needles):
            found.append(group)
    order = {q[0]: i for i, q in enumerate(QUALIFICATIONS)}
    return sorted(set(found), key=lambda x: order[x])


def _sector(text: str):
    lower = text.lower()
    for sector, needles in SECTORS.items():
        if any(n in lower for n in needles):
            return sector
    return "Government"


def _same_or_subdomain(url: str, official_url: str) -> bool:
    try:
        a = urlparse(url).hostname or ""
        b = urlparse(official_url).hostname or ""
        return a == b or a.endswith("." + b) or b.endswith("." + a)
    except Exception:
        return False


def _host_allowed(url: str, official_url: str, extra_domains: list[str] | None = None) -> bool:
    if _same_or_subdomain(url, official_url):
        return True
    host = (urlparse(url).hostname or "").lower()
    for item in (extra_domains or []):
        h = (urlparse(item).hostname or item).lower().strip("/")
        if host == h or host.endswith("." + h):
            return True
    return False


def _apply_url(links: list[dict], official_url: str, extra_domains: list[str] | None = None):
    ranked = []
    for link in links:
        label = (link.get("label") or "").lower()
        url = link.get("url") or ""
        score = sum(k in label for k in ["apply online", "online application", "register", "apply now"])
        if score and _host_allowed(url, official_url, extra_domains):
            ranked.append((score, url))
    return sorted(ranked, reverse=True)[0][1] if ranked else ""


def _age_range(age_text: str) -> tuple[int | None, int | None]:
    if not age_text:
        return None, None
    m = re.search(r"\b(\d{2})\s*(?:to|[-–—])\s*(\d{2})\s*(?:years?|yrs?)?", age_text, re.I)
    if m:
        low, high = int(m.group(1)), int(m.group(2))
        if 14 <= low <= 65 and low <= high <= 70:
            return low, high
    min_m = re.search(r"(?:minimum|min\.?)[^\d]{0,20}(\d{2})", age_text, re.I)
    max_m = re.search(r"(?:maximum|max\.?|upper age)[^\d]{0,20}(\d{2})", age_text, re.I)
    low = int(min_m.group(1)) if min_m else None
    high = int(max_m.group(1)) if max_m else None
    return (low if low and 14 <= low <= 65 else None, high if high and 14 <= high <= 70 else None)


def _experience_months(text: str) -> int:
    # Conservative: only capture explicit experience clauses near the word experience.
    snippets = re.findall(r"[^\n]{0,100}experience[^\n]{0,100}", text, re.I)
    for s in snippets[:20]:
        y = re.search(r"(\d{1,2})\s*(?:years?|yrs?)", s, re.I)
        if y:
            return int(y.group(1)) * 12
        m = re.search(r"(\d{1,3})\s*months?", s, re.I)
        if m:
            return int(m.group(1))
    return 0


def deterministic_extract(title: str, text: str, links: list[dict], source_url: str, extra_allowed_domains: list[str] | None = None) -> dict:
    sample = text[:250000]
    q = _qualifications(sample)
    group = next((x for x in GROUP_PRIORITY if x in q), "")
    ad = _field(sample, ["advertisement no", "advertisement number", "advt. no", "advt no"], 100)
    org = _field(sample, ["organization", "department", "recruiting authority"], 180)
    if not org:
        org = clean(title.split("|")[0].split("-")[0])[:180] or (urlparse(source_url).hostname or "Government Authority")
    post = _field(sample, ["name of post", "post name", "posts"], 180)
    end = _date_near_labels(sample, DATE_LABELS["application_end_date"])
    start = _date_near_labels(sample, DATE_LABELS["application_start_date"])
    exam = _date_near_labels(sample, DATE_LABELS["exam_date"])
    admit = _date_near_labels(sample, DATE_LABELS["admit_card_date"])
    result = _date_near_labels(sample, DATE_LABELS["result_date"])
    age_as_on = _date_near_labels(sample, DATE_LABELS["age_as_on"])
    salary = _field(sample, ["pay scale", "salary", "pay level", "scale of pay"], 220)
    age = _field(sample, ["age limit", "age criteria"], 220)
    min_age, max_age = _age_range(age)
    fee = _field(sample, ["application fee", "examination fee", "fee"], 260)
    selection = _field(sample, ["selection process", "mode of selection", "selection procedure"], 500)
    confidence = 0.48
    confidence += 0.10 if end else 0
    confidence += 0.10 if q else 0
    confidence += 0.10 if _vacancies(sample) is not None else 0
    confidence += 0.08 if ad else 0
    confidence += 0.05 if "apply" in sample.lower() else 0
    confidence += 0.05 if "eligib" in sample.lower() else 0
    return {
        "organization": org,
        "advertisement_no": ad,
        "post_name": post,
        "vacancies": _vacancies(sample),
        "qualifications": q,
        "qualification_group": group,
        "accepted_disciplines": [],
        "eligible_categories": [],
        "eligible_genders": [],
        "sector": _sector(f"{title}\n{sample[:30000]}"),
        "state": ("All India" if "all india" in sample.lower() else next((st for st in STATES if st.lower() in sample.lower()), "")),
        "employment_type": "Government",
        "salary": salary,
        "age_limit": age,
        "min_age": min_age,
        "max_age": max_age,
        "age_as_on": age_as_on,
        "category_age_relaxation": {},
        "age_relaxations": [],
        "min_experience_months": _experience_months(sample),
        "application_fee": fee,
        "fee_by_category": {},
        "selection_process": selection,
        "application_start_date": start,
        "application_end_date": end,
        "exam_date": exam,
        "admit_card_date": admit,
        "result_date": result,
        "official_apply_url": _apply_url(links, source_url, extra_allowed_domains),
        "confidence": min(confidence, 0.96),
    }


OPENAI_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "organization": {"type": "string"},
        "advertisement_no": {"type": "string"},
        "post_name": {"type": "string"},
        "vacancies": {"type": ["integer", "null"]},
        "qualifications": {"type": "array", "items": {"type": "string"}},
        "qualification_group": {"type": "string"},
        "accepted_disciplines": {"type": "array", "items": {"type": "string"}},
        "eligible_categories": {"type": "array", "items": {"type": "string"}},
        "eligible_genders": {"type": "array", "items": {"type": "string"}},
        "sector": {"type": "string"},
        "state": {"type": "string"},
        "employment_type": {"type": "string"},
        "salary": {"type": "string"},
        "age_limit": {"type": "string"},
        "min_age": {"type": ["integer", "null"]},
        "max_age": {"type": ["integer", "null"]},
        "age_as_on": {"type": ["string", "null"]},
        "age_relaxations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"category": {"type": "string"}, "years": {"type": "integer"}},
                "required": ["category", "years"],
            },
        },
        "min_experience_months": {"type": "integer"},
        "application_fee": {"type": "string"},
        "fee_by_category": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"category": {"type": "string"}, "fee": {"type": "string"}},
                "required": ["category", "fee"],
            },
        },
        "selection_process": {"type": "string"},
        "application_start_date": {"type": ["string", "null"]},
        "application_end_date": {"type": ["string", "null"]},
        "exam_date": {"type": ["string", "null"]},
        "admit_card_date": {"type": ["string", "null"]},
        "result_date": {"type": ["string", "null"]},
        "summary": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": [
        "organization", "advertisement_no", "post_name", "vacancies", "qualifications", "qualification_group",
        "accepted_disciplines", "eligible_categories", "eligible_genders", "sector", "state", "employment_type", "salary", "age_limit", "min_age", "max_age",
        "age_as_on", "age_relaxations", "min_experience_months", "application_fee", "fee_by_category", "selection_process",
        "application_start_date", "application_end_date", "exam_date", "admit_card_date", "result_date", "summary", "confidence",
    ],
}


def ai_extract(title: str, text: str) -> dict | None:
    if not settings.OPENAI_API_KEY:
        return None
    prompt = (
        "Extract recruitment facts ONLY from the supplied official notification text. Do not infer missing facts. "
        "Dates must be YYYY-MM-DD or null. Eligible categories, gender restrictions, disciplines, age rules and fees must only be structured when explicitly stated. "
        "Summary must be original, factual, neutral, <=90 words, and must not reproduce long source wording. "
        "Confidence is 0..1 and should be low if key fields conflict. For fee_by_category return category/fee pairs.\n\n"
        "TITLE:\n" + title + "\n\nOFFICIAL TEXT:\n" + text[:120000]
    )
    payload = {
        "model": settings.OPENAI_MODEL,
        "input": prompt,
        "text": {"format": {"type": "json_schema", "name": "recruitment_record", "strict": True, "schema": OPENAI_SCHEMA}},
    }
    try:
        r = httpx.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}", "Content-Type": "application/json"},
            json=payload,
            timeout=90,
        )
        r.raise_for_status()
        data = r.json()
        raw = data.get("output_text")
        if not raw:
            for item in data.get("output", []):
                for content in item.get("content", []):
                    if content.get("type") in {"output_text", "text"} and content.get("text"):
                        raw = content["text"]
        return json.loads(raw) if raw else None
    except Exception:
        return None
