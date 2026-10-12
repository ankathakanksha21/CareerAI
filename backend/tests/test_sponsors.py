from datetime import date

import httpx
import pytest

import repo
import sponsors

HEADER = "Organisation Name,Town/City,County,Type & Rating,Route\n"
# Names that cannot occur in the real register, which is present in the database these tests use
CSV = (HEADER
       + ' Zzqx Holdings Ltd ,Zzqx Town,,Worker (A rating),Skilled Worker\n'
       + '"ZZQX FOODS LTD T/A Qqzz Kitchen",Zzqx Town,Zzqxshire,Worker (A rating),Skilled Worker\n'
       + 'Zzqx Theatre,Zzqx Town,,Temporary Worker (A rating),Creative Worker\n')
API = {"public_updated_at": "2026-10-12T10:08:49+01:00",
       "details": {"attachments": [{"content_type": "text/csv", "url": "https://assets.publishing.service.gov.uk/media/abc/register.csv"}]}}


def _row(name, route="Skilled Worker"):
    return {"name": name, "town": "Zzqx Town", "county": "", "route": route, "rating": "Worker (A rating)"}


def _register(conn, *names, route="Skilled Worker"):
    """Add entries to the register inside the test's transaction, beside whatever is really there."""
    for r in sponsors.with_keys([_row(n, route) for n in names]):
        conn.execute("insert into sponsors (name, name_key, town, county, route, rating) values (%s, %s, %s, %s, %s, %s)",
                     (r["name"], r["name_key"], r["town"], r["county"], r["route"], r["rating"]))


def _fake_get(replies):
    """httpx.get replaced by canned replies, keyed by the start of the address."""
    def get(url, **kwargs):
        for prefix, reply in replies.items():
            if url.startswith(prefix):
                if isinstance(reply, Exception):
                    raise reply
                body = {"json": reply} if isinstance(reply, dict) else {"content": reply.encode("utf-8")}
                return httpx.Response(200, request=httpx.Request("GET", url), **body)
        raise AssertionError(f"unexpected request to {url}")
    return get


# ---------- names ----------

@pytest.mark.parametrize("name", ["Zzqx Ltd", "ZZQX LIMITED", "Zzqx", " The Zzqx Group (UK) Ltd. ", "Zzqx PLC", "zzqx  llp"])
def test_normalise_company_forms(name):
    assert sponsors.normalise(name) == "zzqx"


def test_normalise_keeps_distinguishing_words():
    assert sponsors.normalise("Zzqx Recruitment") == "zzqx recruitment"
    assert sponsors.normalise("Zzqx Recruitment") != sponsors.normalise("Zzqx")


def test_normalise_ampersand_punctuation_and_apostrophes():
    assert sponsors.normalise("Zzqx & Sons, Ltd") == sponsors.normalise("Zzqx and Sons Limited") == "zzqx and sons"
    assert sponsors.normalise("Zzqx's Bakery") == "zzqxs bakery"


def test_normalise_never_empties_a_name_made_of_common_words():
    assert sponsors.normalise("The Company Ltd") == "the company ltd"
    assert sponsors.normalise("  ") == ""


def test_keys_for_trading_as():
    assert sponsors.keys("ZZQX FOODS LTD T/A Qqzz Kitchen") == ["zzqx foods", "qqzz kitchen"]
    assert sponsors.keys("Zzqx Foods Limited trading as Qqzz Kitchen") == ["zzqx foods", "qqzz kitchen"]
    assert sponsors.keys("Zzqx Ltd") == ["zzqx"]
    assert sponsors.keys("Zzqx Ltd t/a Zzqx") == ["zzqx"]  # the same name twice is one key


def test_with_keys_gives_one_row_per_name():
    rows = sponsors.with_keys([_row("ZZQX FOODS LTD T/A Qqzz Kitchen"), _row("Zzqx Ltd")])
    assert [(r["name"], r["name_key"]) for r in rows] == [
        ("ZZQX FOODS LTD T/A Qqzz Kitchen", "zzqx foods"), ("ZZQX FOODS LTD T/A Qqzz Kitchen", "qqzz kitchen"), ("Zzqx Ltd", "zzqx")]


# ---------- reading the file ----------

def test_parse_keeps_skilled_worker_only_and_trims(monkeypatch):
    monkeypatch.setattr(sponsors, "MIN_ROWS", 1)
    rows = sponsors.parse(CSV)
    assert [r["name"] for r in rows] == ["Zzqx Holdings Ltd", "ZZQX FOODS LTD T/A Qqzz Kitchen"]
    assert rows[1] == {"name": "ZZQX FOODS LTD T/A Qqzz Kitchen", "town": "Zzqx Town", "county": "Zzqxshire",
                       "rating": "Worker (A rating)", "route": "Skilled Worker"}


@pytest.mark.parametrize("text", ["", "\n", HEADER, "Name,Town,Route\nZzqx Ltd,Zzqx Town,Skilled Worker\n", "<html>Not found</html>"])
def test_parse_rejects_empty_or_changed_files(monkeypatch, text):
    monkeypatch.setattr(sponsors, "MIN_ROWS", 1)
    with pytest.raises(sponsors.RegisterError):
        sponsors.parse(text)


def test_parse_rejects_a_file_with_too_few_rows():
    with pytest.raises(sponsors.RegisterError):  # three rows against the real minimum
        sponsors.parse(CSV)


def test_latest_reads_the_attachment_and_date(monkeypatch):
    monkeypatch.setattr(sponsors.httpx, "get", _fake_get({sponsors.REGISTER_API: API}))
    assert sponsors.latest() == {"url": "https://assets.publishing.service.gov.uk/media/abc/register.csv", "published_on": date(2026, 10, 12)}


@pytest.mark.parametrize("reply", [
    {"public_updated_at": "2026-10-12T10:08:49+01:00", "details": {"attachments": []}},
    {"details": {}},
    {"public_updated_at": "2026-10-12T10:08:49+01:00",
     "details": {"attachments": [{"content_type": "text/csv", "url": "https://elsewhere.example.test/register.csv"}]}},
    httpx.ConnectError("down"),
])
def test_latest_fails_clearly(monkeypatch, reply):
    monkeypatch.setattr(sponsors.httpx, "get", _fake_get({sponsors.REGISTER_API: reply}))
    with pytest.raises(sponsors.RegisterError):
        sponsors.latest()


# ---------- matching an employer ----------

@pytest.mark.db
@pytest.mark.parametrize("employer", ["Zzqx Holdings Ltd", "ZZQX HOLDINGS LIMITED", "Zzqx", "The Zzqx Group"])
def test_exact_match_after_normalising(conn, employer):
    _register(conn, "Zzqx Holdings Ltd")
    assert sponsors.status(conn, employer) == {"status": "listed", "name": "Zzqx Holdings Ltd"}


@pytest.mark.db
def test_possible_match_when_registered_name_is_longer(conn):
    _register(conn, "Zzqx Stores Limited", "Zzqx Stores Distribution Limited")
    assert sponsors.status(conn, "Zzqx") == {"status": "possible", "name": "Zzqx Stores Limited"}


@pytest.mark.db
def test_longer_advert_name_does_not_match(conn):
    _register(conn, "Zzqx")
    assert sponsors.status(conn, "Zzqx Recruitment") == {"status": "not_found", "name": None}


@pytest.mark.db
def test_a_name_that_only_starts_the_same_does_not_match(conn):
    _register(conn, "Zzqxon Limited")
    assert sponsors.status(conn, "Zzqx")["status"] == "not_found"


@pytest.mark.db
def test_only_skilled_worker_entries_count(conn):
    _register(conn, "Zzqx Theatre", route="Creative Worker")
    assert sponsors.status(conn, "Zzqx Theatre")["status"] == "not_found"


@pytest.mark.db
def test_trading_name_matches(conn):
    _register(conn, "ZZQX FOODS LTD T/A Qqzz Kitchen")
    assert sponsors.status(conn, "Qqzz Kitchen") == {"status": "listed", "name": "ZZQX FOODS LTD T/A Qqzz Kitchen"}
    assert sponsors.status(conn, "Zzqx Foods")["status"] == "listed"


@pytest.mark.db
def test_short_names_match_exactly_only(conn):
    _register(conn, "Zqx Stores Ltd", "Zqy Ltd")
    assert sponsors.status(conn, "Zqx")["status"] == "not_found"  # too short to guess from
    assert sponsors.status(conn, "Zqy")["status"] == "listed"


@pytest.mark.db
@pytest.mark.parametrize("employer", ["", "   ", "Ltd"])
def test_blank_or_meaningless_employer_is_not_found(conn, employer):
    assert sponsors.status(conn, employer)["status"] == "not_found"


@pytest.mark.db
def test_agency_advert_is_never_looked_up(conn):
    _register(conn, "Zzqx Recruitment Ltd")
    assert sponsors.status(conn, "Zzqx Recruitment Ltd", posted_by="agency") == {"status": "agency", "name": None}


# ---------- loading ----------

@pytest.mark.db
def test_replace_swaps_the_register_and_records_when(conn):
    _register(conn, "Zzqx Old Name Ltd")
    rows = sponsors.with_keys([_row("Zzqx Holdings Ltd"), _row("ZZQX FOODS LTD T/A Qqzz Kitchen")])
    repo.replace_sponsors(conn, rows, published_on=date(2026, 10, 12), source_url="https://assets.publishing.service.gov.uk/x.csv", row_count=2)
    assert conn.execute("select count(*) as n from sponsors").fetchone()["n"] == 3  # one of them has two names
    assert sponsors.status(conn, "Zzqx Old Name")["status"] == "not_found"
    meta = repo.register_meta(conn)
    assert meta["published_on"] == date(2026, 10, 12) and meta["row_count"] == 2 and meta["loaded_at"] is not None


@pytest.mark.db
def test_refresh_loads_the_register(conn, own_transaction, monkeypatch):
    monkeypatch.setattr(sponsors, "MIN_ROWS", 1)
    monkeypatch.setattr(sponsors.httpx, "get", _fake_get({sponsors.REGISTER_API: API, "https://assets.publishing.service.gov.uk/": CSV}))
    assert sponsors.refresh() == {"rows": 2, "published_on": date(2026, 10, 12)}
    assert sponsors.status(conn, "Qqzz Kitchen")["status"] == "listed"
    assert sponsors.status(conn, "Zzqx Theatre")["status"] == "not_found"  # not a Skilled Worker entry


@pytest.mark.db
@pytest.mark.parametrize("body", ["", HEADER, "<html>Service unavailable</html>", httpx.ReadTimeout("slow")])
def test_refresh_failure_leaves_the_register_in_place(conn, own_transaction, monkeypatch, body):
    _register(conn, "Zzqx Holdings Ltd")
    monkeypatch.setattr(sponsors.httpx, "get", _fake_get({sponsors.REGISTER_API: API, "https://assets.publishing.service.gov.uk/": body}))
    with pytest.raises(sponsors.RegisterError):
        sponsors.refresh()
    assert sponsors.status(conn, "Zzqx Holdings")["status"] == "listed"


@pytest.mark.db
def test_refresh_rechecks_stored_listings(conn, own_transaction, monkeypatch):
    listing = conn.execute(
        "insert into job_listings (source, source_id, title, employer, employer_key, posted_by, url, posted_on) "
        "values ('test', 't-1', 'Role A', 'Zzqx Holdings', 'zzqx', 'employer', 'https://example.test/1', current_date) returning id").fetchone()["id"]
    agency = conn.execute(
        "insert into job_listings (source, source_id, title, employer, employer_key, posted_by, url, posted_on, sponsor_status) "
        "values ('test', 't-2', 'Role A', 'Zzqx Holdings', 'zzqx', 'agency', 'https://example.test/2', current_date, 'agency') returning id").fetchone()["id"]
    monkeypatch.setattr(sponsors, "MIN_ROWS", 1)
    monkeypatch.setattr(sponsors.httpx, "get", _fake_get({sponsors.REGISTER_API: API, "https://assets.publishing.service.gov.uk/": CSV}))
    sponsors.refresh()
    status = "select sponsor_status, sponsor_name from job_listings where id = %s"
    assert conn.execute(status, (listing,)).fetchone() == {"sponsor_status": "listed", "sponsor_name": "Zzqx Holdings Ltd"}
    assert conn.execute(status, (agency,)).fetchone() == {"sponsor_status": "agency", "sponsor_name": None}  # an agency advert stays one


def test_employer_key_is_empty_for_a_name_that_identifies_nobody():
    assert sponsors.employer_key("Zzqx Holdings Ltd") == "zzqx"
    assert sponsors.employer_key("The Company Ltd") == "" and sponsors.employer_key("") == ""
