import json

import content


def test_content_sections_and_sizes():
    c = content.load()
    assert {k: len(v) for k, v in c.items()} == {
        "uk_market": 5, "where_to_look": 5, "tone_phrases": 8, "tone_norms": 5, "cv_rules": 4, "interview_day": 3}


def test_interview_day_has_every_type():
    day = content.load()["interview_day"]
    assert set(day) == {"phone", "video", "in_person"}
    assert all(3 <= len(lines) <= 5 and all(isinstance(x, str) and x for x in lines) for lines in day.values())
    assert any("gov.uk/prove-right-to-work" in line for line in day["in_person"])


def test_content_item_shapes():
    c = content.load()
    assert all(set(x) == {"title", "body"} for x in c["uk_market"])
    assert all(set(x) == {"name", "tip"} for x in c["where_to_look"])
    assert all(set(x) == {"phrase", "meaning"} for x in c["tone_phrases"])
    assert all(isinstance(x, str) and x for x in c["tone_norms"] + c["cv_rules"])


def test_content_has_the_phrases_from_the_product_brief():
    phrases = {p["phrase"] for p in content.load()["tone_phrases"]}
    assert {"Not bad at all.", "I'll bear that in mind.", "With respect...", "We'd love to keep in touch."} <= phrases


def test_content_has_no_demo_names_or_em_dashes():
    text = json.dumps(content.load(), ensure_ascii=False)
    for word in ("Aditi", "Exeter", "Infosys", "—"):
        assert word not in text


def test_load_returns_a_fresh_copy():
    content.load()["cv_rules"].append("changed by a caller")
    assert len(content.load()["cv_rules"]) == 4
