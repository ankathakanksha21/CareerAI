from datetime import date

import pytest

import prep

WRITTEN = {"talking_points": [{"text": "t", "fact_id": "f1", "achievement_id": "a"}], "pitch": "My pitch.",
           "likely_questions": [{"question": f"Q{i}?", "competency": "teamwork", "story_id": None, "why": ""} for i in range(8)],
           "questions_to_ask": [{"question": f"Ask {i}?", "fact_id": None} for i in range(5)]}
BRIEF = {"facts": [{"id": "f1", "section": "what_they_do", "text": "Zzqx builds payment software."},
                   {"id": "f2", "section": "size", "text": "Registered at Companies House as ZZQX LIMITED."},
                   {"id": "f3", "section": "products", "text": "It sells a council tax app."},
                   {"id": "f4", "section": "news", "text": "Zzqx opened a Leeds office."},
                   {"id": "f5", "section": "values", "text": "It values honesty.", "quote": "honesty"}],
         "missing": [], "notice": None}


def content(**kw):
    return prep.content(written=WRITTEN, brief=BRIEF, researched_at="2026-10-14T09:00:00+00:00", interview_type="video",
                        right_to_work="I have the right to work in the UK on a Graduate visa until 30 January 2027.") | kw


@pytest.mark.parametrize("visa, ends, line", [
    ("graduate", date(2027, 1, 30), "I have the right to work in the UK on a Graduate visa until 30 January 2027."),
    ("student", date(2027, 1, 30), "I am in the UK on a Student visa until 30 January 2027."),
    ("graduate", None, ""), (None, date(2027, 1, 30), "")])
def test_right_to_work_wording(visa, ends, line):
    assert prep.right_to_work({"visa_type": visa, "visa_end_date": ends}) == line


def test_right_to_work_note_says_it_is_not_advice():
    assert prep.RIGHT_TO_WORK_NOTE == ("Employers often ask next whether you will need sponsorship. That answer is yours to add. "
                                       "This is not immigration advice.")


@pytest.mark.parametrize("stage, kind", [("screening", "phone"), ("interview", "video"), ("applied", "video"), (None, "video")])
def test_default_type_from_stage(stage, kind):
    assert prep.default_type(stage) == kind


def test_content_starts_with_nothing_ticked_or_edited():
    c = content()
    assert (c["ticked"], c["pitch_edited"], c["right_to_work_edited"], c["interview_type"]) == ([], False, False, "video")
    assert c["brief"] == BRIEF | {"researched_at": "2026-10-14T09:00:00+00:00"} and c["pitch"] == "My pitch."


@pytest.mark.parametrize("ticked", [[0, 1, 2], [], [4]])
def test_edit_ticks(ticked):
    assert prep.edit(content(), {"ticked": ticked})["ticked"] == ticked


@pytest.mark.parametrize("ticked", [[0, 1, 2, 3], [5], [-1], [1, 1]])
def test_edit_ticks_validated(ticked):
    with pytest.raises(ValueError):
        prep.edit(content(), {"ticked": ticked})


def test_edit_marks_pitch_and_line_as_the_users():
    c = prep.edit(content(), {"pitch": "My own words.", "right_to_work": "My own line."})
    assert (c["pitch"], c["pitch_edited"], c["right_to_work"], c["right_to_work_edited"]) == ("My own words.", True, "My own line.", True)


def test_edit_interview_type_validated():
    assert prep.edit(content(), {"interview_type": "in_person"})["interview_type"] == "in_person"
    with pytest.raises(ValueError):
        prep.edit(content(), {"interview_type": "carrier pigeon"})


def test_edit_leaves_the_stored_pack_alone():
    before = content()
    prep.edit(before, {"pitch": "Changed.", "ticked": [1]})
    assert before["pitch"] == "My pitch." and before["ticked"] == []


def test_rebuild_keeps_edited_pitch_and_line_and_clears_ticks():
    old = prep.edit(content(), {"pitch": "Mine.", "right_to_work": "My line.", "ticked": [1], "interview_type": "phone"})
    new = content(pitch="A new pitch.", right_to_work="A new line.")
    got = prep.rebuild(old, new)
    assert (got["pitch"], got["pitch_edited"], got["right_to_work"], got["right_to_work_edited"]) == ("Mine.", True, "My line.", True)
    assert got["ticked"] == [] and got["interview_type"] == "phone"


def test_rebuild_takes_new_pitch_when_not_edited():
    got = prep.rebuild(content(), content(pitch="A new pitch."))
    assert got["pitch"] == "A new pitch." and got["pitch_edited"] is False


def test_for_interviewer_uses_what_they_do_products_and_news():
    got = prep.for_interviewer(content())
    assert got["company_brief"] == "Zzqx builds payment software. It sells a council tax app. Zzqx opened a Leeds office."
    assert got["likely_questions"].startswith("Q0? Q1?") and got["likely_questions"].endswith("Q7?")


def test_for_interviewer_caps_lengths():
    long_facts = {"facts": [{"id": f"f{i}", "section": "products", "text": f"Product line {i} does many useful things for people."} for i in range(40)],
                  "missing": [], "notice": None}
    long_questions = dict(WRITTEN, likely_questions=[{"question": "Tell me about a time you " + "really " * 30 + f"tried {i}?",
                                                      "competency": "role", "story_id": None, "why": ""} for i in range(8)])
    c = prep.content(written=long_questions, brief=long_facts, researched_at="x", interview_type="video", right_to_work="")
    got = prep.for_interviewer(c)
    assert len(got["company_brief"]) <= prep.COMPANY_SUMMARY_CHARS and got["company_brief"].endswith(".")
    assert len(got["likely_questions"]) <= prep.QUESTIONS_CHARS and got["likely_questions"].endswith("?")


def test_for_interviewer_with_an_empty_brief():
    c = prep.content(written=WRITTEN, brief={"facts": [], "missing": [], "notice": "x"}, researched_at="x", interview_type="video", right_to_work="")
    assert prep.for_interviewer(c)["company_brief"] == "Not provided."
