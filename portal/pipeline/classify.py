import re

def classify(title: str, text: str) -> tuple[str, float]:
    blob = f"{title}\n{text[:20000]}".lower()
    groups = {
        "admit_card": ["admit card", "hall ticket", "e-call letter", "call letter"],
        "result": ["final result", "result declared", "merit list", "score card", "scorecard"],
        "job": ["recruitment", "vacancy", "vacancies", "applications are invited", "advertisement", "apply online", "notification"],
    }
    scores = {kind: sum(1 for term in terms if term in blob) for kind, terms in groups.items()}
    kind = max(scores, key=scores.get)
    max_score = scores[kind]
    if max_score == 0: return "other", 0.0
    if kind == "result" and re.search(r"result\s+of\s+recruitment|recruitment result", blob): scores["result"] += 2
    return kind, min(0.55 + 0.1 * scores[kind], 0.95)
