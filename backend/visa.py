"""Visa salary facts, read from data/visa_rules.json: the figures gov.uk publishes, where each
came from and the date they were checked. Facts only, never a verdict on whether a job can be
sponsored, and no figure is written anywhere else in the code.

To update: read the gov.uk pages listed in the file, change the figures and "checked_on" there."""
import json
from pathlib import Path

PATH = Path(__file__).parent / "data" / "visa_rules.json"


def rules() -> dict:
    return json.loads(PATH.read_text(encoding="utf-8"))


def salary_facts(salary_min, salary_max, annual: bool) -> dict:
    """An advert's salary beside the Skilled Worker figures. "advertised" is None when no annual
    salary was stated, so a day rate or a missing salary is never compared with a yearly threshold."""
    r = rules()
    low, high = salary_min or salary_max, salary_max or salary_min
    return {
        "advertised": {"min": int(low), "max": int(high)} if annual and low else None,
        "standard_salary": r["standard_salary"],
        "lower_salary": r["lower_salary"],
        "links": r["links"],
        "sources": r["sources"],
        "checked_on": r["checked_on"],
    }
