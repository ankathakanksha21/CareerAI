import json

import content


def test_content_sections_and_sizes():
    c = content.load()
    assert {k: len(v) for k, v in c.items()} == {
        "uk_market": 5, "where_to_look": 5, "tone_phrases": 8, "tone_norms": 5, "cv_rules": 4, "interview_day": 3, "networking_guide": 4}


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


# ---------- the networking guide ----------

GUIDE_SOURCES = ("https://www.gov.uk/", "https://www.ukcisa.org.uk/", "https://reachvolunteering.org.uk/", "https://www.prospects.ac.uk/")


def guide() -> dict:
    return {section["id"]: section for section in content.load()["networking_guide"]}


def guide_text(section: dict) -> str:
    return " ".join([section.get("intro", ""), section.get("note", ""), *section.get("steps", []), *section.get("points", [])])


def test_the_guide_has_its_four_sections():
    sections = guide()
    assert list(sections) == ["stranger-to-referral", "recruiters", "uk-experience", "references"]
    assert [s["title"] for s in sections.values()] == ["From stranger to referral in six steps", "Working with recruiters",
                                                        "One UK project, internship or volunteering role", "Who can give a reference"]
    assert len(sections["stranger-to-referral"]["steps"]) == 6
    for section in sections.values():
        assert set(section) <= {"id", "title", "intro", "steps", "points", "note", "sources"}
        assert all(isinstance(x, str) and x for x in section.get("steps", []) + section.get("points", []))


def test_every_guide_source_is_a_checked_site():
    for section in guide().values():
        for source in section.get("sources", []):
            assert set(source) == {"label", "url"} and source["url"].startswith(GUIDE_SOURCES), source["url"]


def test_the_guide_says_what_its_sources_say():
    sections = guide()
    recruiters = guide_text(sections["recruiters"])
    assert "cannot charge you a fee for finding" in recruiters
    assert any(s["url"] == "https://www.gov.uk/agency-workers-your-rights/fees" for s in sections["recruiters"]["sources"])
    experience = guide_text(sections["uk-experience"])
    assert "voluntary work" in experience and "weekly hours" in experience and "This is not immigration advice." in experience
    assert any(s["url"].startswith("https://www.ukcisa.org.uk/") for s in sections["uk-experience"]["sources"])
    assert "few invitations a month" in guide_text(sections["stranger-to-referral"])


def test_the_guide_leaves_out_sites_that_failed_the_check():
    text = json.dumps(content.load()["networking_guide"]).lower()
    assert "do-it" not in text and "do it.org" not in text



def test_every_guide_section_that_mentions_visas_says_it_is_not_immigration_advice():
    for section in guide().values():
        text = guide_text(section)
        if "visa" in text.lower() or "sponsor" in text.lower():
            assert "This is not immigration advice." in text, section["id"]
