import re
from datetime import date
from pathlib import Path

import visa

ROOT = Path(__file__).resolve().parents[2]


def test_rules_file_has_figures_sources_and_the_date_checked():
    rules = visa.rules()
    assert isinstance(rules["standard_salary"], int) and isinstance(rules["lower_salary"], int)
    assert rules["standard_salary"] > rules["lower_salary"] > 0
    assert date.fromisoformat(rules["checked_on"]) <= date.today()
    assert len(rules["sources"]) >= 2
    for name in ("salary", "paid_less", "eligible_occupations", "going_rates", "register", "graduate_visa", "student_visa"):
        assert rules["links"][name].startswith("https://www.gov.uk/"), name
    assert all(s["url"].startswith("https://www.gov.uk/") and s["label"] for s in rules["sources"])


def test_facts_always_carry_the_source_and_the_date_checked():
    for facts in (visa.salary_facts(36000, 40000, True), visa.salary_facts(None, None, False), visa.salary_facts(450, 450, False)):
        assert facts["checked_on"] == visa.rules()["checked_on"]
        assert facts["sources"] and all(s["url"].startswith("https://www.gov.uk/") for s in facts["sources"])
        assert facts["standard_salary"] == visa.rules()["standard_salary"] and facts["lower_salary"] == visa.rules()["lower_salary"]


def test_an_annual_salary_is_reported_as_advertised():
    assert visa.salary_facts(36000, 40000, True)["advertised"] == {"min": 36000, "max": 40000}
    assert visa.salary_facts(38000.0, None, True)["advertised"] == {"min": 38000, "max": 38000}  # one figure given
    assert visa.salary_facts(None, 38000, True)["advertised"] == {"min": 38000, "max": 38000}


def test_no_salary_means_no_comparison():
    assert visa.salary_facts(None, None, True)["advertised"] is None
    assert visa.salary_facts(0, 0, True)["advertised"] is None


def test_a_rate_is_not_compared():
    assert visa.salary_facts(450, 500, False)["advertised"] is None


def test_facts_give_no_verdict():
    facts = visa.salary_facts(50000, 60000, True)
    assert not {"eligible", "meets", "verdict", "ok", "qualifies", "sponsorable"} & set(facts)


def test_figures_live_only_in_the_rules_file():
    """A threshold typed into code or copy would go stale silently when gov.uk changes it."""
    rules = visa.rules()
    figures = {str(rules[k]) for k in ("standard_salary", "lower_salary")}
    figures |= {f"{int(n):,}" for n in figures}
    offenders = []
    for folder, pattern in (("backend", "*.py"), ("frontend/src", "**/*.js*")):
        for path in (ROOT / folder).glob(pattern):
            if "tests" in path.parts or ".venv" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            offenders += [f"{path.name}: {n}" for n in figures if re.search(rf"(?<![\d,]){re.escape(n)}(?![\d,])", text)]
    assert offenders == []
