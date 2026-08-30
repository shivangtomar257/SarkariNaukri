from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date
from typing import Any


ACADEMIC_RANK = {
    "10th Pass": 1,
    "12th Pass": 2,
    "Graduate": 3,
    "Engineering": 3,
    "Post Graduate": 4,
}


@dataclass
class EligibilityResult:
    status: str
    label: str
    reasons: list[str]
    warnings: list[str]
    age: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def age_on(dob: date, on_date: date) -> int:
    return on_date.year - dob.year - ((on_date.month, on_date.day) < (dob.month, dob.day))


def qualification_compatible(user_education: str, job_group: str, qualifications: list[str] | None = None) -> tuple[bool | None, str]:
    user_education = (user_education or "").strip()
    job_group = (job_group or "").strip()
    qualifications = qualifications or []
    if not user_education:
        return None, "Add your education to check qualification eligibility."
    if not job_group and not qualifications:
        return None, "The official notice has not been structured enough to decide qualification eligibility automatically."
    if user_education == job_group or user_education in qualifications:
        return True, f"Your saved education ({user_education}) matches the detected requirement."
    if job_group in {"ITI", "Diploma"}:
        return None, f"This notice is grouped as {job_group}; equivalence must be checked in the official notification."
    ur = ACADEMIC_RANK.get(user_education)
    jr = ACADEMIC_RANK.get(job_group)
    if ur is not None and jr is not None:
        if ur >= jr:
            return True, f"Your education level is at or above the detected {job_group} level. Subject/discipline conditions can still apply."
        return False, f"The detected requirement is {job_group}, above your saved education level ({user_education})."
    return None, "Qualification equivalence is uncertain; check the official notification."


def evaluate(job, *, education: str = "", discipline: str = "", dob: date | None = None, category: str = "General", gender: str = "", experience_months: int = 0) -> EligibilityResult:
    reasons: list[str] = []
    warnings: list[str] = []
    hard_fail = False
    unknown = False
    computed_age = None

    q_ok, q_reason = qualification_compatible(education, job.qualification_group, job.qualifications)
    if q_ok is False:
        hard_fail = True
        reasons.append(q_reason)
    elif q_ok is True:
        reasons.append(q_reason)
    else:
        unknown = True
        warnings.append(q_reason)

    if getattr(job, "accepted_disciplines", None):
        allowed = [str(x).strip().lower() for x in job.accepted_disciplines if str(x).strip()]
        if discipline:
            if not any(a in discipline.lower() or discipline.lower() in a for a in allowed):
                hard_fail = True
                reasons.append("Your discipline does not match the structured list detected for this recruitment.")
            else:
                reasons.append("Your discipline matches the structured discipline requirement.")
        else:
            unknown = True
            warnings.append("Add your discipline/branch to check the subject-specific requirement.")

    if getattr(job, "eligible_categories", None):
        allowed_categories = {str(x).strip().lower() for x in job.eligible_categories if str(x).strip()}
        if category and category.lower() not in allowed_categories:
            hard_fail = True
            reasons.append("Your selected category is not in the structured eligible-category list for this notice.")
        elif category:
            reasons.append("Your selected category appears in the structured eligible-category list.")

    if getattr(job, "eligible_genders", None):
        allowed_genders = {str(x).strip().lower() for x in job.eligible_genders if str(x).strip()}
        if gender:
            if gender.lower() not in allowed_genders:
                hard_fail = True
                reasons.append("The structured gender eligibility for this notice does not match the selection you provided.")
            else:
                reasons.append("Your selected gender matches the structured restriction detected in the notice.")
        else:
            unknown = True
            warnings.append("This notice has a structured gender restriction; select a value to check it, or verify the official notification.")

    if dob and (job.min_age is not None or job.max_age is not None):
        on_date = job.age_as_on or date.today()
        computed_age = age_on(dob, on_date)
        relaxation = 0
        try:
            relaxation = int((job.category_age_relaxation or {}).get(category, 0) or 0)
        except (TypeError, ValueError):
            relaxation = 0
        if job.min_age is not None and computed_age < job.min_age:
            hard_fail = True
            reasons.append(f"Your age would be {computed_age} on {on_date:%d %b %Y}; the detected minimum is {job.min_age}.")
        if job.max_age is not None and computed_age > job.max_age + relaxation:
            hard_fail = True
            reasons.append(f"Your age would be {computed_age} on {on_date:%d %b %Y}; the detected maximum for your category is {job.max_age + relaxation}.")
        if not hard_fail:
            reasons.append(f"Your age ({computed_age}) appears within the structured age range for {category}.")
    elif job.min_age is not None or job.max_age is not None:
        unknown = True
        warnings.append("Add your date of birth to check the detected age limit.")
    else:
        unknown = True
        warnings.append("Age rules are not structured for this notice; verify them in the official notification.")

    required_exp = int(getattr(job, "min_experience_months", 0) or 0)
    if required_exp:
        if int(experience_months or 0) < required_exp:
            hard_fail = True
            reasons.append(f"The structured requirement is at least {required_exp} months of experience; your profile has {int(experience_months or 0)} months.")
        else:
            reasons.append("Your saved experience meets the structured minimum experience requirement.")

    if hard_fail:
        return EligibilityResult("not_eligible", "Likely not eligible", reasons, warnings, computed_age)
    if unknown:
        return EligibilityResult("check", "Eligibility needs verification", reasons, warnings, computed_age)
    return EligibilityResult("eligible", "You appear eligible", reasons, warnings, computed_age)


def fee_for_category(job, category: str) -> str:
    fees = getattr(job, "fee_by_category", None) or {}
    if category and category in fees:
        return str(fees[category])
    for key in (category.lower() if category else "", "All", "all", "default"):
        if key and key in fees:
            return str(fees[key])
    return job.application_fee or "See official notification"
