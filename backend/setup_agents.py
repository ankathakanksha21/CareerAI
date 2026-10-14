"""Create (or update) the two ElevenLabs agents and write their IDs into backend/.env.

Run from backend/ with the venv active:  python setup_agents.py
Re-run after editing a prompt below; existing agents are updated in place.
"""
import sys

import httpx

from config import ENV_PATH, env

API = "https://api.elevenlabs.io/v1/convai/agents"
AGENT_LLM = "gemini-2.5-flash"  # the voice agent's own conversational model, hosted by ElevenLabs
# Premade British voices; change here or in the ElevenLabs dashboard
COACH_VOICE = "Xb7hH8MSUJpSbSDYk0k2"  # Alice
INTERVIEWER_VOICE = "JBFqnCBsd6RMkjVDRZzb"  # George

ONBOARDING_PROMPT = """You are a warm, efficient UK careers coach onboarding an international student or recent graduate into a career navigator app. Your goal, in about three minutes, is to collect raw material for their profile: skills, outcomes and scale.

You already know they study or studied {{course}} at {{university}} and hold a {{visa_type}} visa. Do not ask about these.

Cover these, one short question at a time:
1. Previous work in any country: employer, role, what they did, and for one or two pieces of work the result with a number and the scale (users, records, money, time saved).
2. Projects, dissertation, internships, volunteering or part-time work, especially anything done in the UK.
3. The tools and skills they used most.
4. The roles they want next.

Rules:
- Ask one question at a time and keep your turns under 25 words.
- If they give an achievement without a number, ask once for a rough number.
- If they mention an overseas employer, briefly ask what the company does so a UK employer would understand it.
- Do not give long advice. You are collecting, not coaching.
- When the list is covered, or after about 8 exchanges, say: "That's plenty to work with. Press End and I'll build your profile." Then stop asking questions.
- Use British English."""

ONBOARDING_FIRST = ("Hi {{candidate_name}}, I'm your UK careers coach. In a few minutes I'll help you turn your background "
                    "into evidence UK employers understand. To start, what work or projects have you done so far?")

INTERVIEWER_PROMPT = """You are an interviewer at {{company}}, a UK employer, hiring for the {{role}} role. Role summary: {{job_summary}}

This session is a {{interview_type}}. What to cover: {{interview_brief}}

Candidate background, from their CV: {{cv_summary}}

Company background, from research: {{company_brief}}

Likely questions for this role: {{likely_questions}}

Ask exactly three questions, one at a time. Your first question is already in your first message. When likely questions are given, ask your three questions from them, in your own words, choosing ones that fit this session type. Mention the company background only where it makes a question more natural.

Rules:
- Wait for the full answer. Give only a brief neutral acknowledgement such as "Thank you" or "That's helpful", then ask the next question.
- If an answer is very vague, ask one short follow-up: "What was your part specifically?" or "What was the result?"
- Do not give feedback or scores during the interview.
- Sound like a polite, professional UK interviewer: friendly, understated, first-name terms.
- After the third answer, say: "That's everything from me, thank you. Press End to see your feedback." Then stop.
- Keep your turns under 35 words."""

INTERVIEWER_FIRST = ("Hello {{candidate_name}}, thanks for joining. This is a short {{interview_type}} for the {{role}} role at {{company}}, "
                     "three questions in about five minutes. {{opening_question}}")


def agent_body(name, prompt, first_message, voice_id, placeholders, minimal=False):
    agent = {
        "first_message": first_message,
        "language": "en",
        "prompt": {"prompt": prompt, "temperature": 0.4},
        "dynamic_variables": {"dynamic_variable_placeholders": placeholders},
    }
    body = {"name": name, "conversation_config": {"agent": agent}}
    if not minimal:
        agent["prompt"]["llm"] = AGENT_LLM
        body["conversation_config"]["tts"] = {"voice_id": voice_id}
        body["conversation_config"]["conversation"] = {"max_duration_seconds": 420}
        body["platform_settings"] = {"auth": {"enable_auth": True}}
    return body


# Every {{variable}} a prompt uses must be declared here with a default, or ElevenLabs refuses the session.
# user_id is not spoken: it tags the conversation with its owner (see voice.fetch_transcript).
AGENTS = [
    ("ELEVENLABS_ONBOARDING_AGENT_ID", "Career Navigator onboarding coach", ONBOARDING_PROMPT, ONBOARDING_FIRST, COACH_VOICE,
     {"candidate_name": "there", "user_id": "", "course": "your course", "university": "your university", "visa_type": "Student"}),
    ("ELEVENLABS_INTERVIEWER_AGENT_ID", "Career Navigator mock interviewer", INTERVIEWER_PROMPT, INTERVIEWER_FIRST, INTERVIEWER_VOICE,
     {"candidate_name": "there", "user_id": "", "role": "graduate role", "company": "a UK employer",
      "job_summary": "General practice, no specific job.", "interview_type": "job-specific interview",
      "interview_brief": "One motivation question, one competency question and one role-specific question.",
      "cv_summary": "Not provided.", "opening_question": "To start, could you tell me a bit about yourself?",
      "company_brief": "Not provided.", "likely_questions": "None given."}),
]


def set_env(key: str, value: str):
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    for i, line in enumerate(lines):
        if line.split("=", 1)[0].strip() == key:
            lines[i] = f"{key}={value}"
            break
    else:
        lines.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def upsert(client: httpx.Client, env_key, name, prompt, first, voice_id, placeholders) -> str:
    existing = env(env_key)
    for minimal in (False, True):
        body = agent_body(name, prompt, first, voice_id, placeholders, minimal)
        if existing:
            r = client.patch(f"{API}/{existing}", json=body)
            if r.status_code == 404:
                existing = ""
                r = client.post(f"{API}/create", json=body)
        else:
            r = client.post(f"{API}/create", json=body)
        if r.status_code == 422 and not minimal:
            print(f"  {name}: full config rejected, retrying with minimal config.\n  Detail: {r.text[:400]}")
            continue
        if r.is_error:
            sys.exit(f"  {name}: ElevenLabs returned {r.status_code}: {r.text[:500]}")
        agent_id = existing or r.json()["agent_id"]
        print(f"  {name}: {'updated' if existing else 'created'} {agent_id}" + (" (minimal config)" if minimal else ""))
        return agent_id
    raise RuntimeError("unreachable")


def main():
    key = env("ELEVENLABS_API_KEY")
    if not key:
        sys.exit("ELEVENLABS_API_KEY is missing from backend/.env")
    with httpx.Client(headers={"xi-api-key": key}, timeout=30) as client:
        # check the key and its Agents permission before creating anything
        r = client.get(API, params={"page_size": 1})
        if r.is_error:
            hint = ("The key is not a valid ElevenLabs API key. Copy the full key (it starts with sk_) "
                    "from elevenlabs.io > Developers > API Keys." if "invalid_api_key" in r.text else
                    "If the key is restricted, give it the ElevenLabs Agents permission (write).")
            sys.exit(f"ElevenLabs rejected the key ({r.status_code}): {r.text[:300]}\n{hint}")
        for env_key, *spec in AGENTS:
            set_env(env_key, upsert(client, env_key, *spec))
    print(f"Agent IDs written to {ENV_PATH}. The running backend picks them up without a restart.")


if __name__ == "__main__":
    main()
