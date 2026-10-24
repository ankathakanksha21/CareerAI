"""The one peers AI task: suggesting a broad field from the user's target roles. The model is scripted."""
import pytest

import ai
import peers


@pytest.fixture
def model(monkeypatch):
    """Script the model: each entry is a parsed reply, or an exception to raise. Returns the calls made."""
    def install(*script):
        replies, calls = list(script), []

        def fake(system, user, max_tokens=1500):
            calls.append({"system": system, "user": user})
            reply = replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return reply
        monkeypatch.setattr(ai, "complete_json", fake)
        return calls
    return install


@pytest.mark.parametrize("answer", ["Data and analytics", " data AND analytics ", "Data  and analytics"])
def test_a_listed_field_is_taken(model, answer):
    model({"field": answer})
    assert ai.suggest_field(["Data Analyst", "Business Intelligence Analyst"]) == "data"


@pytest.mark.parametrize("answer", ["Astronaut", "Data", "data"])
def test_an_answer_outside_the_list_is_ignored(model, answer):
    model({"field": answer})
    assert ai.suggest_field(["Data Analyst"]) is None


def test_the_prompt_holds_the_fields_and_the_roles_only(model):
    calls = model({"field": "Law"})
    assert ai.suggest_field(["Trainee Solicitor", "Paralegal"]) == "law"
    sent = calls[0]["user"]
    assert all(label in sent for label in peers.FIELDS.values())
    assert "Trainee Solicitor" in sent and "Paralegal" in sent


def test_a_malformed_reply_is_retried_then_an_error(model):
    model(ValueError("not json"), ValueError("not json"))
    with pytest.raises(ai.AIError):
        ai.suggest_field(["Data Analyst"])


def test_a_blank_reply_is_retried(model):
    model({"field": ""}, {"field": "Software and IT"})
    assert ai.suggest_field(["Backend Developer"]) == "software"
