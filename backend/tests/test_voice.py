import httpx
import pytest

import voice

ME, SOMEONE_ELSE = "11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"
TURNS = [{"role": "agent", "message": "Hi", "time_in_call_secs": 0},
         {"role": "user", "message": "Hello", "time_in_call_secs": 2},
         {"role": "agent", "message": None, "time_in_call_secs": 3}]


@pytest.fixture
def conversation(monkeypatch, no_env_file):
    """Make ElevenLabs answer with the given conversation fields. Returns the URLs requested."""
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    requested = []

    def install(**fields):
        def fake_get(url, **kwargs):
            requested.append(url)
            return httpx.Response(200, json={"conversation_id": "conv_1", "transcript": TURNS} | fields,
                                  request=httpx.Request("GET", url))
        monkeypatch.setattr(voice.httpx, "get", fake_get)
        return requested
    return install


def test_transcript_owner_top_level(conversation):
    requested = conversation(user_id=ME)
    assert voice.fetch_transcript("conv_1", ME) == [{"role": "agent", "message": "Hi"}, {"role": "user", "message": "Hello"}]
    assert requested == ["https://api.elevenlabs.io/v1/convai/conversations/conv_1"]


def test_transcript_owner_in_initiation_data(conversation):
    conversation(conversation_initiation_client_data={"user_id": ME})
    assert len(voice.fetch_transcript("conv_1", ME)) == 2


def test_transcript_owner_dynamic_variable(conversation):
    conversation(user_id=None, conversation_initiation_client_data={"dynamic_variables": {"user_id": ME}})
    assert len(voice.fetch_transcript("conv_1", ME)) == 2


def test_transcript_mismatch_raises(conversation):
    conversation(user_id=SOMEONE_ELSE, conversation_initiation_client_data={
        "user_id": SOMEONE_ELSE, "dynamic_variables": {"user_id": SOMEONE_ELSE}})
    with pytest.raises(PermissionError):
        voice.fetch_transcript("conv_1", ME)


def test_transcript_without_a_recorded_owner_raises(conversation):
    conversation()
    with pytest.raises(PermissionError):
        voice.fetch_transcript("conv_1", ME)


def test_empty_caller_never_matches_an_unowned_conversation(conversation):
    conversation(user_id="", conversation_initiation_client_data={"user_id": None, "dynamic_variables": {"user_id": ""}})
    with pytest.raises(PermissionError):
        voice.fetch_transcript("conv_1", "")


@pytest.mark.parametrize("conversation_id", ["../agents", "a/b", "", "conv 1", "x" * 101])
def test_odd_conversation_ids_are_refused_before_any_request(conversation, conversation_id):
    requested = conversation(user_id=ME)
    with pytest.raises(PermissionError):
        voice.fetch_transcript(conversation_id, ME)
    assert requested == []
