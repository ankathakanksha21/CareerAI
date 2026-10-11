import re

import setup_agents

VARIABLE = re.compile(r"\{\{(\w+)\}\}")
AGENTS = {env_key: (prompt, first, placeholders) for env_key, _name, prompt, first, _voice, placeholders in setup_agents.AGENTS}
COACH = AGENTS["ELEVENLABS_ONBOARDING_AGENT_ID"]
INTERVIEWER = AGENTS["ELEVENLABS_INTERVIEWER_AGENT_ID"]


def test_every_variable_used_is_declared():
    # ElevenLabs refuses a session whose prompt uses a variable the agent does not declare
    for env_key, (prompt, first, placeholders) in AGENTS.items():
        used = set(VARIABLE.findall(prompt + first))
        assert used <= set(placeholders), f"{env_key} uses undeclared {used - set(placeholders)}"


def test_coach_knows_the_details_form_answers():
    prompt, _first, placeholders = COACH
    assert set(placeholders) == {"candidate_name", "user_id", "course", "university", "visa_type"}
    for variable in ("{{course}}", "{{university}}", "{{visa_type}}"):
        assert variable in prompt
    assert "Do not ask about these." in prompt


def test_coach_no_longer_asks_for_what_the_form_collected():
    prompt, first, _ = COACH
    text = (prompt + first).lower()
    for phrase in ("visa situation", "graduation date", "what are you studying", "evidence bank"):
        assert phrase not in text
    assert "press end and i'll build your profile." in text


def test_both_agents_carry_the_user_id():
    assert "user_id" in COACH[2] and "user_id" in INTERVIEWER[2]
