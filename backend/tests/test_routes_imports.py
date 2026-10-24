"""CV upload, GitHub import, "Improve with AI" and the story bank, through the API. The model and
GitHub are replaced; the files are real PDFs and Word files built in memory."""
import uuid
from datetime import date

import httpx
import pytest

import ai
import cvfile
import github
import repo
from files import CV_LINES, cv_docx, cv_pdf, forbid_disk_writes, locked_pdf, pdf

pytestmark = pytest.mark.db

LIMIT = "You've reached today's limit. It resets at midnight."
AI_FAILED = "The AI did not respond properly. Try again."
CV_TEXT = "\n".join(CV_LINES)
NO_FACTS = {"work_history": [], "education": [], "skills": [], "languages": []}
ITEMS = [{"title": "Delays report", "raw": "Built a weekly delivery delays report", "uk_version": "Built a weekly delays report for 15 managers",
          "skills": ["SQL"], "outcome": "15 managers", "scale": "", "context_note": "", "where": "Zzqx Holdings Ltd"},
         {"title": "Merge script", "raw": "Wrote a Python script", "uk_version": "Wrote a Python script merging three spreadsheets",
          "skills": ["Python"], "outcome": "Add a number: hours saved", "scale": "", "context_note": "", "where": ""}]
JOB = {"employer": "Zzqx Holdings Ltd", "job_title": "Systems Engineer", "location": "Pune", "country": "India", "start_month": None,
       "end_month": None, "is_current": False, "employer_context": ""}
DETAILS = {"full_name": "Test Person", "university": "Zzqx City University", "course": "MSc Course A", "graduation_date": "2026-09-17",
           "visa_type": "student", "visa_end_date": "2027-01-31", "locations": ["London"]}
STORY = {"title": "Story", "competency": "Problem solving", "situation": "s", "task": "t", "action": "a", "result": "r", "strength": "strong", "tip": ""}


@pytest.fixture(autouse=True)
def no_facts(monkeypatch):
    monkeypatch.setattr(ai, "extract_facts", lambda *args, **kwargs: NO_FACTS)


def state(client):
    return client.get("/api/state").json()


def upload(client, data: bytes, **kw):
    return client.post("/api/ai/achievements/upload", content=data, headers={"Content-Type": "application/octet-stream"}, **kw)


def used(client) -> int:
    return state(client)["usage"]["ai"]["used"]


# ---------- uploading a CV ----------

@pytest.mark.parametrize("make", [cv_pdf, cv_docx])
def test_upload_saves_achievements_from_the_cv_and_keeps_only_its_text(client, stub, make):
    calls = stub("extract_achievements", {"items": ITEMS, "pitch": "I am a pitch."})
    r = upload(client, make())
    assert r.status_code == 200
    body = r.json()
    assert [i["title"] for i in body["items"]] == ["Delays report", "Merge script"] and body["cut"] is False and body["notice"] is None
    assert [i["needs_number"] for i in body["items"]] == [False, True]
    assert calls[0][0] == CV_TEXT and calls[0][2] == "cv"   # the model was given the text, as a CV
    s = state(client)
    assert all(a["source"] == "cv" for a in s["achievements"]) and s["profile"]["pitch"] == "I am a pitch."
    entry = s["journal"][0]
    assert (entry["type"], entry["title"], entry["with_whom"]) == ("import", "CV upload", "")
    assert client.get(f"/api/journal/{entry['id']}/transcript").json() == {"transcript": CV_TEXT}
    assert used(client) == 1


def test_the_uploaded_file_is_never_written_to_disk(client, stub, monkeypatch):
    stub("extract_achievements", {"items": ITEMS, "pitch": ""})
    data = cv_pdf()
    forbid_disk_writes(monkeypatch)
    assert upload(client, data).status_code == 200


def test_the_file_itself_is_stored_nowhere(client, stub, conn, user_a):
    stub("extract_achievements", {"items": ITEMS, "pitch": ""})
    upload(client, cv_pdf())
    kept = conn.execute("select transcript from journal_entries where user_id = %s", (user_a,)).fetchone()["transcript"]
    assert kept == CV_TEXT and "%PDF" not in kept


@pytest.mark.parametrize("data, message", [
    (b"", "That file is empty."),
    (b"Zarvin Quillfeather. Systems Engineer at Zzqx Holdings Ltd. " * 10, "Upload a PDF or a Word (.docx) file."),
    (pdf([[]]), "We could not read any text in this file. Paste the text instead."),
    (locked_pdf("secret"), "This PDF is password-protected. Remove the password, or paste the text instead."),
    (cv_pdf()[:200], "We could not open that file. Save it again as PDF or .docx, or paste the text instead."),
])
def test_a_file_that_cannot_be_read_never_reaches_the_ai_and_costs_nothing(client, stub, data, message):
    calls = stub("extract_achievements", {"items": ITEMS, "pitch": ""})
    r = upload(client, data)
    assert r.status_code == 422 and r.json()["detail"] == message
    assert calls == [] and used(client) == 0 and state(client)["journal"] == []


def test_a_file_over_the_limit_is_refused(client, stub):
    calls = stub("extract_achievements", {"items": ITEMS, "pitch": ""})
    r = upload(client, b"%PDF-1.4\n" + b"0" * (5 * 1024 * 1024))
    assert r.status_code == 413 and r.json()["detail"] == "That file is over 4 MB. Upload a smaller one, or paste the text instead."
    assert calls == [] and used(client) == 0


class Incoming:
    """A request body arriving in chunks without end, as a hostile client would send it."""
    def __init__(self, declared=None):
        self.headers = {} if declared is None else {"content-length": str(declared)}
        self.served = 0

    async def stream(self):
        while True:
            self.served += 1
            yield b"0" * 65536


def test_an_upload_stops_being_read_once_it_passes_the_limit():
    import asyncio

    from fastapi import HTTPException

    import main
    request = Incoming()
    with pytest.raises(HTTPException) as refused:
        asyncio.run(main.upload_bytes(request, user=None))
    assert refused.value.status_code == 413
    assert request.served * 65536 <= cvfile.MAX_BYTES + 2 * 65536   # it stopped within a chunk or two of the limit


def test_an_upload_that_declares_itself_too_large_is_not_read_at_all():
    import asyncio

    from fastapi import HTTPException

    import main
    request = Incoming(declared=cvfile.MAX_BYTES + 1)
    with pytest.raises(HTTPException) as refused:
        asyncio.run(main.upload_bytes(request, user=None))
    assert refused.value.status_code == 413 and request.served == 0


def test_upload_at_the_daily_limit_does_not_call_the_ai(client, stub, monkeypatch):
    monkeypatch.setenv("DAILY_AI_LIMIT", "0")
    calls = stub("extract_achievements", {"items": ITEMS, "pitch": ""})
    r = upload(client, cv_pdf())
    assert r.status_code == 429 and r.json()["detail"] == LIMIT and calls == []


def test_a_long_file_is_cut_and_the_answer_says_so(client, stub):
    calls = stub("extract_achievements", {"items": ITEMS, "pitch": ""})
    body = upload(client, pdf([["Analysed delivery records for the operations team every single week. "] * 50 for _ in range(15)])).json()
    assert body["cut"] is True and body["notice"] == "Only the first part of this long file was read."
    assert len(calls[0][0]) == cvfile.MAX_CHARS


def test_upload_fails_whole_when_the_achievements_call_fails(client, stub):
    stub("extract_achievements", ai.AIError("achievements"))
    r = upload(client, cv_pdf())
    assert r.status_code == 502 and r.json()["detail"] == AI_FAILED
    s = state(client)
    assert s["achievements"] == [] and s["journal"] == [] and s["usage"]["ai"]["used"] == 1   # an attempt is counted, as for every AI task


def test_upload_keeps_the_achievements_when_only_the_facts_call_fails(client, stub):
    stub("extract_achievements", {"items": ITEMS, "pitch": ""})
    stub("extract_facts", ai.AIError("cv facts"))
    body = upload(client, cv_pdf()).json()
    assert len(body["items"]) == 2 and body["facts"] is None
    assert body["notice"] == "We could not pick out your work history and education this time. Add them in Profile."
    assert len(state(client)["achievements"]) == 2


def test_upload_offers_what_it_found_and_saves_none_of_it(client, stub):
    stub("extract_achievements", {"items": ITEMS, "pitch": ""})
    stub("extract_facts", NO_FACTS | {"work_history": [JOB], "skills": ["Python"], "languages": [{"language": "Hindi", "level": "Native"}]})
    body = upload(client, cv_pdf()).json()
    facts = body["facts"]
    assert facts["work_history"] == [JOB | {"achievement_ids": [body["items"][0]["id"]]}]   # the achievement that happened there
    assert facts["skills"] == ["Python"] and facts["languages"] == [{"language": "Hindi", "level": "Native"}] and facts["education"] == []
    s = state(client)
    assert s["work_history"] == [] and s["profile"]["skills"] == [] and s["achievements"][0]["work_history_id"] is None


def test_upload_links_an_achievement_to_a_job_already_saved(client, stub, conn, user_a):
    job = repo.add_entry(conn, user_a, "work_history", {"employer": "Zzqx Holdings Limited"})
    stub("extract_achievements", {"items": ITEMS, "pitch": ""})
    body = upload(client, cv_pdf()).json()
    assert [i["work_history_id"] for i in body["items"]] == [job["id"], None]


def test_the_current_course_found_in_a_cv_is_offered_as_what_it_adds(client, stub):
    client.put("/api/profile", json=DETAILS)
    course = state(client)["education"][0]
    stub("extract_achievements", {"items": ITEMS, "pitch": ""})
    stub("extract_facts", NO_FACTS | {"education": [{"institution": "Zzqx City University", "qualification": "MSc", "subject": "Course A",
                                                     "start_month": date(2025, 9, 1), "end_month": date(2026, 9, 1), "grade": "Predicted Merit", "country": "UK"}]})
    offered = upload(client, cv_pdf()).json()["facts"]["education"]
    assert offered == [{"id": course["id"], "name": "MSc Course A, Zzqx City University",
                        "adds": {"start_month": "2025-09-01", "grade": "Predicted Merit"}, "achievement_ids": []}]


def test_the_same_cv_twice_adds_nothing_twice_and_still_offers_its_facts(client, stub):
    stub("extract_achievements", {"items": ITEMS, "pitch": ""})
    upload(client, cv_pdf())
    calls = stub("extract_achievements", {"items": [], "pitch": ""})   # told what is saved, the model returns nothing new
    stub("extract_facts", NO_FACTS | {"work_history": [JOB]})
    r = upload(client, cv_pdf())
    assert r.status_code == 200 and r.json()["items"] == [] and len(r.json()["facts"]["work_history"]) == 1
    assert {a["title"] for a in calls[0][3]} == {"Merge script", "Delays report"}   # the model was told what is already saved
    assert len(state(client)["achievements"]) == 2


def test_an_upload_with_nothing_new_and_no_facts_says_so(client, stub):
    stub("extract_achievements", {"items": [], "pitch": ""})
    r = upload(client, cv_pdf())
    assert r.status_code == 422 and r.json()["detail"] == "We could not find any achievements in that. Add more detail and try again."
    assert state(client)["journal"] == []


def test_no_connection_is_open_while_the_model_reads_a_cv(client, monkeypatch):
    import db
    from contextlib import contextmanager
    inner, open_now = db.transaction, []

    @contextmanager
    def tracking():
        with inner() as c:
            open_now.append(1)
            try:
                yield c
            finally:
                open_now.pop()
    monkeypatch.setattr(db, "transaction", tracking)

    def fake(*args, **kwargs):
        assert open_now == [], "a database transaction was open during the model call"
        return {"items": ITEMS, "pitch": ""}
    monkeypatch.setattr(ai, "extract_achievements", fake)
    assert upload(client, cv_pdf()).status_code == 200


# ---------- pasted text and voice calls now offer facts too ----------

def test_pasted_text_offers_facts_and_links_achievements(client, stub):
    stub("extract_achievements", {"items": ITEMS, "pitch": ""})
    stub("extract_facts", NO_FACTS | {"work_history": [JOB]})
    body = client.post("/api/ai/achievements", json={"transcript": CV_TEXT, "source": "paste"}).json()
    assert body["facts"]["work_history"][0]["achievement_ids"] == [body["items"][0]["id"]] and body["notice"] is None


# ---------- GitHub ----------

REPO = {"name": "delay-report", "description": "Weekly delivery delays report", "language": "Python", "stargazers_count": 3,
        "fork": False, "private": False, "pushed_at": "2026-08-21T15:25:42Z", "html_url": "https://github.com/zzqx-sample/delay-report"}
OTHER = REPO | {"name": "mess-feedback", "description": "", "html_url": "https://github.com/zzqx-sample/mess-feedback"}
README = "# Delay report\nBuilds a weekly delays report in SQL."
PROJECT = {"title": "Delay report", "raw": "Builds a weekly delays report in SQL", "uk_version": "Built a weekly delays report in SQL",
           "skills": ["SQL"], "outcome": "Add a number: depots covered", "scale": "", "context_note": ""}
TOKEN = "github-test-token-0000"


@pytest.fixture
def gh(monkeypatch, no_env_file):
    """GitHub replaced: gh(repositories, readme=...) answers the list and README requests. Returns the requests made."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    def install(repos=(REPO, OTHER), readme=README, fail=None):
        seen = []

        def answer(request):
            seen.append(request.url.path)
            if fail:
                return fail(request)
            if request.url.path.endswith("/readme"):
                return httpx.Response(200, text=readme) if readme else httpx.Response(404, json={"message": "Not Found"})
            return httpx.Response(200, json=list(repos))
        monkeypatch.setattr(github, "_client", lambda: httpx.Client(transport=httpx.MockTransport(answer)))
        return seen
    return install


def repos_of(client, username="zzqx-sample"):
    # a POST: the name a user types travels in the body, so it never sits in an address or an access log
    return client.post("/api/github/repos", json={"username": username})


def test_listing_repositories(client, gh):
    gh(repos=(REPO, OTHER | {"fork": True}))
    body = repos_of(client).json()
    assert body == {"username": "zzqx-sample", "repos": [{"name": "delay-report", "description": "Weekly delivery delays report", "language": "Python",
                                                         "stars": 3, "pushed_on": "2026-08-21", "url": "https://github.com/zzqx-sample/delay-report",
                                                         "imported": False}]}


@pytest.mark.parametrize("reply, status, message", [
    (httpx.Response(404, json={"message": "Not Found"}), 404, "No GitHub user with that name"),
    (httpx.Response(403, headers={"x-ratelimit-remaining": "0"}, json={}), 429, "GitHub is busy. Try again in a few minutes."),
    (httpx.Response(500, text="oops"), 502, "We could not reach GitHub. Try again shortly."),
])
def test_github_failures_have_plain_messages(client, gh, stub, reply, status, message):
    gh(fail=lambda request: reply)
    calls = stub("github_achievements", {1: PROJECT})
    r = repos_of(client)
    assert r.status_code == status and r.json()["detail"] == message
    r = client.post("/api/ai/achievements/github", json={"username": "zzqx-sample", "repos": ["delay-report"]})
    assert r.status_code == status and r.json()["detail"] == message
    assert calls == [] and used(client) == 0


@pytest.mark.parametrize("username", ["-leading", "two words", "x" * 40, "a_b"])
def test_a_username_github_would_never_allow_is_refused(client, gh, username):
    seen = gh()
    assert repos_of(client, username).status_code == 422
    assert client.post("/api/ai/achievements/github", json={"username": username, "repos": ["delay-report"]}).status_code == 422
    assert seen == []


def test_importing_repositories_saves_project_achievements(client, gh, stub):
    seen = gh()
    calls = stub("github_achievements", {1: PROJECT, 2: PROJECT | {"title": "Mess feedback", "raw": ""}})
    r = client.post("/api/ai/achievements/github", json={"username": "zzqx-sample", "repos": ["delay-report", "mess-feedback"]})
    assert r.status_code == 200
    items = r.json()["items"]
    assert [(i["title"], i["source"], i["source_url"]) for i in items] == [
        ("Delay report", "github", "https://github.com/zzqx-sample/delay-report"),
        ("Mess feedback", "github", "https://github.com/zzqx-sample/mess-feedback")]
    sent = calls[0][0]
    assert [(x["n"], x["name"], x["readme"]) for x in sent] == [(1, "delay-report", README), (2, "mess-feedback", README)]
    assert seen.count("/repos/zzqx-sample/delay-report/readme") == 1 and seen.count("/users/zzqx-sample/repos") == 1
    s = state(client)
    assert s["profile"]["github_username"] == "zzqx-sample" and s["usage"]["ai"]["used"] == 1
    entry = s["journal"][0]
    assert (entry["type"], entry["title"]) == ("import", "GitHub projects")
    assert "Builds a weekly delays report in SQL." in client.get(f"/api/journal/{entry['id']}/transcript").json()["transcript"]


@pytest.mark.parametrize("repos", [[], ["a", "b", "c", "d", "e", "f"], ["bad name"], "delay-report"])
def test_import_takes_one_to_five_repository_names(client, gh, stub, repos):
    gh()
    calls = stub("github_achievements", {1: PROJECT})
    assert client.post("/api/ai/achievements/github", json={"username": "zzqx-sample", "repos": repos}).status_code == 422
    assert calls == []


def test_a_repository_that_is_not_in_the_users_list_is_refused(client, gh, stub):
    gh(repos=(REPO, OTHER | {"name": "a-fork", "fork": True}))
    calls = stub("github_achievements", {1: PROJECT})
    for name in ("someone-elses", "a-fork"):
        r = client.post("/api/ai/achievements/github", json={"username": "zzqx-sample", "repos": ["delay-report", name]})
        assert r.status_code == 422 and r.json()["detail"] == "Pick repositories from the list."
    assert calls == [] and used(client) == 0 and state(client)["profile"]["github_username"] is None


def test_a_repository_already_imported_is_skipped(client, gh, stub):
    gh()
    stub("github_achievements", {1: PROJECT})
    client.post("/api/ai/achievements/github", json={"username": "zzqx-sample", "repos": ["delay-report"]})
    assert [r["imported"] for r in repos_of(client).json()["repos"]] == [True, False]

    calls = stub("github_achievements", {1: PROJECT | {"title": "Mess feedback"}})
    client.post("/api/ai/achievements/github", json={"username": "zzqx-sample", "repos": ["delay-report", "mess-feedback"]})
    assert [x["name"] for x in calls[0][0]] == ["mess-feedback"]

    r = client.post("/api/ai/achievements/github", json={"username": "zzqx-sample", "repos": ["delay-report", "mess-feedback"]})
    assert r.status_code == 422 and r.json()["detail"] == "Those repositories are already in your profile."
    assert len(state(client)["achievements"]) == 2 and used(client) == 2


def test_a_repository_with_nothing_to_read_is_not_sent_to_the_ai(client, gh, stub):
    gh(repos=(OTHER,), readme="")
    calls = stub("github_achievements", {1: PROJECT})
    r = client.post("/api/ai/achievements/github", json={"username": "zzqx-sample", "repos": ["mess-feedback"]})
    assert r.status_code == 422 and r.json()["detail"] == "Those repositories have no README or description to read."
    assert calls == [] and used(client) == 0


def test_a_repository_the_ai_could_not_describe_is_reported(client, gh, stub):
    gh()
    stub("github_achievements", {2: PROJECT})
    body = client.post("/api/ai/achievements/github", json={"username": "zzqx-sample", "repos": ["delay-report", "mess-feedback"]}).json()
    assert [i["source_url"] for i in body["items"]] == ["https://github.com/zzqx-sample/mess-feedback"]
    assert body["notice"] == "1 repository said too little to describe."


def test_github_import_saves_nothing_when_the_ai_fails(client, gh, stub):
    gh()
    stub("github_achievements", ai.AIError("github"))
    r = client.post("/api/ai/achievements/github", json={"username": "zzqx-sample", "repos": ["delay-report"]})
    assert r.status_code == 502 and r.json()["detail"] == AI_FAILED
    s = state(client)
    assert s["achievements"] == [] and s["journal"] == [] and s["profile"]["github_username"] is None


def test_github_import_at_the_daily_limit(client, gh, stub, monkeypatch):
    monkeypatch.setenv("DAILY_AI_LIMIT", "0")
    gh()
    calls = stub("github_achievements", {1: PROJECT})
    r = client.post("/api/ai/achievements/github", json={"username": "zzqx-sample", "repos": ["delay-report"]})
    assert r.status_code == 429 and calls == []


def test_the_github_token_is_in_no_response(client, gh, monkeypatch):
    gh(fail=lambda request: httpx.Response(500, text=f"echo {request.headers.get('authorization')}"))
    monkeypatch.setenv("GITHUB_TOKEN", TOKEN)
    for r in (repos_of(client),
              client.post("/api/ai/achievements/github", json={"username": "zzqx-sample", "repos": ["delay-report"]})):
        assert r.status_code == 502 and TOKEN not in r.text


def test_the_username_a_user_types_is_not_written_to_the_server_log(client, gh, stub, caplog):
    import logging
    gh()
    stub("github_achievements", {1: PROJECT})
    with caplog.at_level(logging.INFO):
        repos_of(client)
        client.post("/api/ai/achievements/github", json={"username": "zzqx-sample", "repos": ["delay-report"]})
    assert "zzqx-sample" not in caplog.text


def test_github_projects_are_private_to_their_owner(client, gh, stub, user_b, as_user):
    gh()
    stub("github_achievements", {1: PROJECT})
    client.post("/api/ai/achievements/github", json={"username": "zzqx-sample", "repos": ["delay-report"]})
    as_user(user_b)
    assert state(client)["achievements"] == [] and state(client)["profile"]["github_username"] is None
    assert [r["imported"] for r in repos_of(client).json()["repos"]] == [False, False]


# ---------- improve with AI ----------

def weak(conn, user):
    return repo.add_achievements(conn, user, [ITEMS[1]], "cv")[0]


def test_improve_rewrites_and_saves_the_bullet_and_says_what_it_was(client, stub, conn, user_a):
    a = weak(conn, user_a)
    calls = stub("improve", {"uk_version": "Wrote a Python script saving 5 hours a week", "outcome": "5 hours a week saved", "scale": "one team"})
    r = client.post(f"/api/ai/achievements/{a['id']}/improve", json={"note": "it saved five hours a week"})
    assert r.status_code == 200
    body = r.json()
    assert body["achievement"]["uk_version"] == "Wrote a Python script saving 5 hours a week" and body["achievement"]["needs_number"] is False
    assert body["achievement"]["raw"] == a["raw"] and body["achievement"]["title"] == a["title"]
    assert body["previous"] == {"uk_version": a["uk_version"], "outcome": a["outcome"], "scale": a["scale"]}
    assert calls[0][0]["id"] == a["id"] and calls[0][1] == "it saved five hours a week"
    assert state(client)["achievements"][0]["outcome"] == "5 hours a week saved" and used(client) == 1


def test_improve_leaves_the_bullet_alone_when_the_ai_fails(client, stub, conn, user_a):
    a = weak(conn, user_a)
    stub("improve", ai.AIError("improve"))
    r = client.post(f"/api/ai/achievements/{a['id']}/improve", json={"note": "five hours"})
    assert r.status_code == 502 and r.json()["detail"] == AI_FAILED
    assert repo.get_achievement(conn, user_a, a["id"]) == a


def test_improve_without_a_note_is_allowed(client, stub, conn, user_a):
    a = weak(conn, user_a)
    calls = stub("improve", {"uk_version": "Wrote a Python script that merged three spreadsheets", "outcome": "", "scale": ""})
    assert client.post(f"/api/ai/achievements/{a['id']}/improve", json={}).status_code == 200 and calls[0][1] == ""


def test_improve_bad_unknown_foreign_and_limited(client, stub, conn, user_a, user_b, as_user, monkeypatch):
    a = weak(conn, user_a)
    calls = stub("improve", {"uk_version": "x", "outcome": "", "scale": ""})
    assert client.post("/api/ai/achievements/not-a-uuid/improve", json={"note": "x"}).status_code == 422
    assert client.post(f"/api/ai/achievements/{uuid.uuid4()}/improve", json={"note": "x"}).status_code == 404
    assert client.post(f"/api/ai/achievements/{a['id']}/improve", json={"note": "x" * 301}).status_code == 422
    as_user(user_b)
    assert client.post(f"/api/ai/achievements/{a['id']}/improve", json={"note": "x"}).status_code == 404
    as_user(user_a, "Test Person")
    monkeypatch.setenv("DAILY_AI_LIMIT", "0")
    assert client.post(f"/api/ai/achievements/{a['id']}/improve", json={"note": "x"}).status_code == 429
    assert calls == [] and repo.get_achievement(conn, user_a, a["id"]) == a


# ---------- the story bank ----------

def achievements(conn, user, count):
    made = [ITEMS[0] | {"title": f"Thing {n}", "uk_version": f"Built thing {n} for 15 users"} for n in range(count)]
    return repo.add_achievements(conn, user, made, "cv")


@pytest.fixture
def bank(monkeypatch):
    """The model writes a story for every achievement it is sent, unless told to fail for a batch size."""
    def install(fail_sizes=()):
        asked = []

        def fake(batch, taken=()):
            asked.append([a["id"] for a in batch])
            if len(batch) in fail_sizes:
                raise ai.AIError("story bank")
            return {a["n"]: STORY | {"title": f"Story of {a['title']}"} for a in batch}
        monkeypatch.setattr(ai, "story_bank", fake)
        return asked
    return install


def test_the_story_bank_writes_a_story_for_each_achievement_without_one(client, bank, conn, user_a):
    made = achievements(conn, user_a, 3)
    repo.add_story(conn, user_a, made[0]["id"], STORY)
    asked = bank()
    r = client.post("/api/ai/stories/bank")
    assert r.status_code == 200 and r.json()["notice"] is None
    assert {s["achievement_id"] for s in r.json()["stories"]} == {made[1]["id"], made[2]["id"]}
    assert sorted(x for batch in asked for x in batch) == sorted([made[1]["id"], made[2]["id"]])
    assert len(state(client)["stories"]) == 3 and used(client) == 1


def test_the_story_bank_never_takes_the_total_past_eight(client, bank, conn, user_a):
    made = achievements(conn, user_a, 11)
    for a in made[:6]:
        repo.add_story(conn, user_a, a["id"], STORY)
    bank()
    assert len(client.post("/api/ai/stories/bank").json()["stories"]) == 2
    assert len(state(client)["stories"]) == 8
    r = client.post("/api/ai/stories/bank")
    assert r.status_code == 400 and r.json()["detail"] == "You already have 8 stories."
    assert len(state(client)["stories"]) == 8 and used(client) == 1


def test_the_story_bank_needs_something_to_write_about(client, bank, conn, user_a):
    asked = bank()
    r = client.post("/api/ai/stories/bank")
    assert r.status_code == 400 and r.json()["detail"] == "Build your profile first."
    made = achievements(conn, user_a, 1)
    repo.add_story(conn, user_a, made[0]["id"], STORY)
    r = client.post("/api/ai/stories/bank")
    assert r.status_code == 400 and r.json()["detail"] == "Every achievement already has a story."
    assert asked == [] and used(client) == 0


def test_one_failed_batch_keeps_the_other_and_says_so(client, bank, conn, user_a):
    achievements(conn, user_a, 7)
    bank(fail_sizes={3})
    body = client.post("/api/ai/stories/bank").json()
    assert len(body["stories"]) == 4 and body["notice"] == "Some stories could not be written. Try again to write the rest."
    assert len(state(client)["stories"]) == 4


def test_the_story_bank_saves_nothing_when_every_batch_fails(client, bank, conn, user_a):
    achievements(conn, user_a, 7)
    bank(fail_sizes={3, 4})
    r = client.post("/api/ai/stories/bank")
    assert r.status_code == 502 and r.json()["detail"] == AI_FAILED and state(client)["stories"] == []


def test_the_story_bank_at_the_daily_limit(client, bank, conn, user_a, monkeypatch):
    achievements(conn, user_a, 2)
    monkeypatch.setenv("DAILY_AI_LIMIT", "0")
    asked = bank()
    assert client.post("/api/ai/stories/bank").status_code == 429 and asked == []


def test_the_story_bank_is_private(client, bank, conn, user_a, user_b, as_user):
    achievements(conn, user_a, 2)
    bank()
    client.post("/api/ai/stories/bank")
    as_user(user_b)
    assert state(client)["stories"] == []
    assert client.post("/api/ai/stories/bank").json()["detail"] == "Build your profile first."
