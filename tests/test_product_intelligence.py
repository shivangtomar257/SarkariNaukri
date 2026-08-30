from datetime import date
from types import SimpleNamespace

from portal.eligibility import age_on, evaluate, fee_for_category


def job(**overrides):
    values = dict(
        qualification_group="Graduate",
        qualifications=["Graduate"],
        accepted_disciplines=[],
        eligible_categories=[],
        eligible_genders=[],
        min_age=18,
        max_age=30,
        age_as_on=date(2026, 8, 1),
        category_age_relaxation={"OBC": 3},
        min_experience_months=0,
        fee_by_category={"General": "₹100", "OBC": "₹100", "SC": "Nil"},
        application_fee="See official notification",
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def test_age_on_reference_date():
    assert age_on(date(2000, 8, 2), date(2026, 8, 1)) == 25
    assert age_on(date(2000, 8, 1), date(2026, 8, 1)) == 26


def test_eligibility_happy_path():
    result = evaluate(job(), education="Graduate", dob=date(2000, 1, 1), category="General")
    assert result.status == "eligible"


def test_category_age_relaxation_is_applied():
    result = evaluate(job(), education="Graduate", dob=date(1993, 8, 2), category="OBC")
    assert result.status == "eligible"


def test_experience_can_block_eligibility():
    result = evaluate(job(min_experience_months=24), education="Graduate", dob=date(2000, 1, 1), category="General", experience_months=12)
    assert result.status == "not_eligible"


def test_fee_by_category():
    assert fee_for_category(job(), "SC") == "Nil"
