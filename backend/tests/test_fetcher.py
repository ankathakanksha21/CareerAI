import gzip
import time

import httpx
import pytest

import fetcher

PUBLIC = "93.184.216.34"  # a public address (documentation sites use it); nothing here really connects
OTHER = "93.184.216.35"
HOME = "https://zzqx.test/"
HTML = {"Content-Type": "text/html; charset=utf-8"}


def page(body: str, title: str = "Zzqx", links: list[tuple[str, str]] = ()) -> str:
    anchors = "".join(f'<a href="{href}">{text}</a>' for href, text in links)
    return f"<html><head><title>{title}</title></head><body><nav>Menu</nav><p>{body}</p>{anchors}<footer>Cookies</footer></body></html>"


@pytest.fixture
def web(monkeypatch):
    """The internet replaced: `names` maps host names to addresses, `routes` maps "host/path" to a
    response (or a callable taking the request). robots.txt is missing (404) unless routed.
    Returns the requests made."""
    seen = []

    def install(routes: dict, names: dict | None = None):
        names = names or {}

        def resolve(host, port):
            if host in names:
                return names[host]
            if host.endswith(".test"):
                return [PUBLIC]
            raise OSError("no such host")

        def handler(request):
            seen.append(request)
            key = request.headers["host"] + request.url.path
            answer = routes.get(key)
            if answer is None:
                return httpx.Response(404)
            return answer(request) if callable(answer) else answer
        monkeypatch.setattr(fetcher, "_resolve", resolve)
        monkeypatch.setattr(fetcher, "_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
        return seen
    return install


def ok(body: str, headers=HTML) -> httpx.Response:
    return httpx.Response(200, headers=headers, text=body)


# ---------- what the user types ----------

@pytest.mark.parametrize("typed, expected", [
    ("zzqx.test", "https://zzqx.test/"), ("http://zzqx.test/about", "https://zzqx.test/"), ("  WWW.Zzqx.test  ", "https://www.zzqx.test/"),
    ("https://zzqx.test:443/", "https://zzqx.test/"), ("zzqx.test.", "https://zzqx.test/")])
def test_website_normalises(typed, expected):
    assert fetcher.website(typed) == expected


@pytest.mark.parametrize("typed", ["localhost", "10.0.0.1", "http://10.0.0.1", "[::1]", "http://[::1]/", "file:///etc/passwd",
                                   "zzqx.test:8080", "https://x@zzqx.test", "https://x:y@zzqx.test", "", "   ", "ftp://zzqx.test",
                                   "https://zz qx.test", "javascript:alert(1)", "https://127.0.0.1.nip.io@zzqx.test"])
def test_website_refuses(typed):
    assert fetcher.website(typed) is None


# ---------- where a request may go ----------

def test_private_resolution_is_refused(web):
    seen = web({"zzqx.test/": ok(page("Hello"))}, names={"zzqx.test": ["10.0.0.5"]})
    with pytest.raises(fetcher.Refused) as e:
        fetcher.fetch(HOME, {})
    assert e.value.reason == "address" and seen == []


@pytest.mark.parametrize("addresses", [[PUBLIC, "10.0.0.5"], ["127.0.0.1"], ["169.254.169.254"], ["::1"], ["fe80::1"],
                                       ["::ffff:127.0.0.1"], ["100.64.0.1"], ["0.0.0.0"]])
def test_any_non_public_resolution_is_refused(web, addresses):
    web({"zzqx.test/": ok(page("Hello"))}, names={"zzqx.test": addresses})
    with pytest.raises(fetcher.Refused) as e:
        fetcher.fetch(HOME, {})
    assert e.value.reason == "address"


def test_redirect_to_metadata_address_is_refused(web):
    seen = web({"zzqx.test/": httpx.Response(302, headers={"Location": "http://169.254.169.254/latest/meta-data/"})})
    with pytest.raises(fetcher.Refused) as e:
        fetcher.fetch(HOME, {})
    assert e.value.reason == "address"
    assert all(r.url.host == PUBLIC for r in seen)  # nothing was sent to the private address


def test_redirect_to_a_name_that_resolves_privately_is_refused(web):
    web({"zzqx.test/": httpx.Response(301, headers={"Location": "https://inside.test/"})},
        names={"zzqx.test": [PUBLIC], "inside.test": ["192.168.1.10"]})
    with pytest.raises(fetcher.Refused) as e:
        fetcher.fetch(HOME, {})
    assert e.value.reason == "address"


def test_redirect_to_another_scheme_is_refused(web):
    web({"zzqx.test/": httpx.Response(302, headers={"Location": "file:///etc/passwd"})})
    with pytest.raises(fetcher.Refused) as e:
        fetcher.fetch(HOME, {})
    assert e.value.reason == "address"


def test_connects_to_the_checked_address_with_the_host_name(web):
    seen = web({"zzqx.test/": ok(page("Hello"))})
    fetcher.fetch(HOME, {})
    request = seen[-1]
    assert request.url.host == PUBLIC and request.url.scheme == "https"
    assert request.headers["host"] == "zzqx.test" and request.extensions["sni_hostname"] == "zzqx.test"
    assert request.headers["user-agent"] == fetcher.USER_AGENT


def test_follows_a_redirect_and_reports_where_it_ended(web):
    web({"zzqx.test/": httpx.Response(301, headers={"Location": "https://www.zzqx.test/"}),
         "www.zzqx.test/": ok(page("Welcome to Zzqx"))})
    got = fetcher.fetch(HOME, {})
    assert got["url"] == "https://www.zzqx.test/" and "Welcome to Zzqx" in got["text"]


def test_too_many_redirects(web):
    web({f"zzqx.test/{i}": httpx.Response(302, headers={"Location": f"/{i + 1}"}) for i in range(6)})
    with pytest.raises(fetcher.Refused) as e:
        fetcher.fetch("https://zzqx.test/0", {})
    assert e.value.reason == "redirects"


# ---------- what is read ----------

def test_size_limit_stops_reading(web):
    web({"zzqx.test/": ok("<p>" + "a" * 5_000_000 + "</p>")})
    got = fetcher.fetch(HOME, {})
    assert 0 < len(got["text"]) <= fetcher.MAX_BYTES


def test_compressed_page_is_limited_after_decoding(web):
    body = gzip.compress(("<p>" + "b" * 3_000_000 + "</p>").encode())
    web({"zzqx.test/": httpx.Response(200, headers=HTML | {"Content-Encoding": "gzip"}, content=body)})
    got = fetcher.fetch(HOME, {})
    assert 0 < len(got["text"]) <= fetcher.MAX_BYTES


def test_timeout(web):
    def slow(request):
        raise httpx.ReadTimeout("slow", request=request)
    web({"zzqx.test/": slow})
    with pytest.raises(fetcher.Refused) as e:
        fetcher.fetch(HOME, {})
    assert e.value.reason == "timeout"


def test_unknown_host_is_unreachable(web):
    web({}, names={})
    with pytest.raises(fetcher.Refused) as e:
        fetcher.fetch("https://nowhere.example/", {})
    assert e.value.reason == "unreachable"


@pytest.mark.parametrize("content_type", ["application/pdf", "image/png", "application/json"])
def test_not_html_is_refused(web, content_type):
    web({"zzqx.test/": ok("%PDF-1.4", headers={"Content-Type": content_type})})
    with pytest.raises(fetcher.Refused) as e:
        fetcher.fetch(HOME, {})
    assert e.value.reason == "not_html"


def test_error_status_is_refused(web):
    web({"zzqx.test/": httpx.Response(500)})
    with pytest.raises(fetcher.Refused) as e:
        fetcher.fetch(HOME, {})
    assert e.value.reason == "status"


def test_text_drops_scripts_navigation_and_footers(web):
    web({"zzqx.test/": ok("<html><head><title>Zzqx | Home</title><script>var x = 1;</script></head><body><header>Menu</header>"
                          "<nav>Products</nav><main><h1>We build bridges</h1><p>Founded by engineers.</p></main>"
                          "<form><input name=e><button>Sign up</button></form><footer>Cookie policy</footer></body></html>")})
    got = fetcher.fetch(HOME, {})
    assert got["title"] == "Zzqx | Home"
    assert got["text"] == "We build bridges\nFounded by engineers."


def test_latin1_page_reads(web):
    web({"zzqx.test/": httpx.Response(200, headers={"Content-Type": "text/html; charset=iso-8859-1"},
                                      content="<p>Café crème since 1990</p>".encode("latin-1"))})
    assert fetcher.fetch(HOME, {})["text"] == "Café crème since 1990"


def test_meta_charset_is_used_when_the_header_has_none(web):
    web({"zzqx.test/": httpx.Response(200, headers={"Content-Type": "text/html"},
                                      content='<meta charset="windows-1252"><p>“Quality”</p>'.encode("cp1252"))})
    assert fetcher.fetch(HOME, {})["text"] == "“Quality”"


# ---------- robots.txt ----------

def test_robots_disallow_is_respected(web):
    seen = web({"zzqx.test/robots.txt": ok("User-agent: *\nDisallow: /\n", headers={"Content-Type": "text/plain"}),
                "zzqx.test/": ok(page("Hello"))})
    with pytest.raises(fetcher.Refused) as e:
        fetcher.fetch(HOME, {})
    assert e.value.reason == "robots"
    assert [r.url.path for r in seen] == ["/robots.txt"]


def test_robots_rule_for_this_agent_is_respected(web):
    web({"zzqx.test/robots.txt": ok("User-agent: UKCareerNavigator\nDisallow: /private\n\nUser-agent: *\nDisallow: /\n",
                                    headers={"Content-Type": "text/plain"}),
         "zzqx.test/": ok(page("Hello")), "zzqx.test/private": ok(page("Secret"))})
    assert fetcher.fetch(HOME, {})["text"].startswith("Hello")
    with pytest.raises(fetcher.Refused):
        fetcher.fetch("https://zzqx.test/private", {})


def test_robots_missing_allows(web):
    web({"zzqx.test/": ok(page("Hello"))})  # robots.txt answers 404
    assert "Hello" in fetcher.fetch(HOME, {})["text"]


@pytest.mark.parametrize("robots", [httpx.Response(500), httpx.Response(503)])
def test_robots_unreachable_forbids(web, robots):
    web({"zzqx.test/robots.txt": robots, "zzqx.test/": ok(page("Hello"))})
    with pytest.raises(fetcher.Refused) as e:
        fetcher.fetch(HOME, {})
    assert e.value.reason == "robots"


def test_robots_timeout_forbids(web):
    def slow(request):
        raise httpx.ConnectTimeout("slow", request=request)
    web({"zzqx.test/robots.txt": slow, "zzqx.test/": ok(page("Hello"))})
    with pytest.raises(fetcher.Refused) as e:
        fetcher.fetch(HOME, {})
    assert e.value.reason == "robots"


def test_robots_read_once_per_host(web):
    seen = web({"zzqx.test/": ok(page("Hello")), "zzqx.test/about": ok(page("About"))})
    robots = {}
    fetcher.fetch(HOME, robots)
    fetcher.fetch("https://zzqx.test/about", robots)
    assert [r.url.path for r in seen].count("/robots.txt") == 1


# ---------- a whole site ----------

def test_site_picks_useful_same_site_links(web):
    links = [("/about-us", "About"), ("/careers", "Join us"), ("/basket", "Basket"), ("https://other.test/about", "Partner"),
             ("/values", "Our values"), ("mailto:hi@zzqx.test", "Email"), ("/news/report.pdf", "Annual report"),
             ("/about-us#team", "Team"), ("https://www.zzqx.test/what-we-do", "Services"), ("/x", "Who we are")]
    seen = web({"zzqx.test/": ok(page("Home page", links=links)), "zzqx.test/about-us": ok(page("About text")),
                "zzqx.test/careers": ok(page("Careers text")), "zzqx.test/values": ok(page("Values text")),
                "www.zzqx.test/what-we-do": ok(page("Services text")), "zzqx.test/x": ok(page("Who text"))})
    pages, problems = fetcher.site(HOME)
    assert [p["url"] for p in pages] == ["https://zzqx.test/", "https://zzqx.test/about-us", "https://zzqx.test/careers",
                                         "https://zzqx.test/values", "https://www.zzqx.test/what-we-do", "https://zzqx.test/x"]
    assert problems == []
    assert not any(r.headers["host"] == "other.test" for r in seen)


def test_site_reads_at_most_five_more_pages(web):
    links = [(f"/about-{i}", "About") for i in range(9)]
    routes = {"zzqx.test/": ok(page("Home", links=links))} | {f"zzqx.test/about-{i}": ok(page(f"About {i}")) for i in range(9)}
    web(routes)
    pages, _ = fetcher.site(HOME)
    assert len(pages) == 1 + fetcher.MAX_EXTRA_PAGES


def test_site_collects_reasons_and_never_raises(web):
    links = [("/about", "About"), ("/careers", "Careers")]
    web({"zzqx.test/": ok(page("Home", links=links)), "zzqx.test/careers": ok("%PDF", headers={"Content-Type": "application/pdf"})})
    pages, problems = fetcher.site(HOME)
    assert [p["url"] for p in pages] == ["https://zzqx.test/"]
    assert sorted(problems) == ["not_html", "status"]


def test_site_when_the_home_page_fails(web):
    web({}, names={"zzqx.test": ["10.0.0.5"]})
    assert fetcher.site(HOME) == ([], ["address"])


def test_title_is_the_pages_own_not_an_icons(web):
    web({"zzqx.test/": ok('<html><head><title>Zzqx | Home</title></head><body><svg><title>Logo</title></svg><p>Hi</p></body></html>')})
    assert fetcher.fetch(HOME, {})["title"] == "Zzqx | Home"


# ---------- what the final review found ----------

def test_a_slow_page_is_given_up_after_the_time_limit(web, monkeypatch):
    monkeypatch.setattr(fetcher, "TIMEOUT_S", 0.5)

    def drip():
        for _ in range(40):
            time.sleep(0.1)
            yield b"<p>slow</p>"
    web({"zzqx.test/": lambda request: httpx.Response(200, headers=HTML, content=drip())})
    started = time.monotonic()
    with pytest.raises(fetcher.Refused) as e:
        fetcher.fetch(HOME, {})
    assert e.value.reason == "timeout" and time.monotonic() - started < 1.5


def test_a_page_wrapped_in_one_form_is_read(web):
    web({"zzqx.test/": ok('<html><body><form id="aspnetForm"><input name="q"><p>We are an NHS trust in Leeds.</p>'
                          '<button>Search</button><select><option>Menu</option></select><textarea>x</textarea></form></body></html>')})
    assert fetcher.fetch(HOME, {})["text"] == "We are an NHS trust in Leeds."


def test_site_with_an_empty_home_page_says_it_could_not_be_read(web):
    web({"zzqx.test/": ok("<html><body><script>app()</script></body></html>")})
    assert fetcher.site(HOME) == ([], ["empty"])


def test_site_leaves_out_an_empty_extra_page(web):
    web({"zzqx.test/": ok(page("Home", links=[("/about", "About"), ("/careers", "Careers")])),
         "zzqx.test/about": ok("<html><body><div id=root></div></body></html>"), "zzqx.test/careers": ok(page("Careers text"))})
    pages, problems = fetcher.site(HOME)
    assert [p["url"] for p in pages] == ["https://zzqx.test/", "https://zzqx.test/careers"] and problems == ["empty"]


def test_asks_for_an_uncompressed_page(web):
    seen = web({"zzqx.test/": ok(page("Hello"))})
    fetcher.fetch(HOME, {})
    assert seen[-1].headers["accept-encoding"] == "identity"


def test_a_utf8_page_cut_through_a_character_is_not_garbled(web, monkeypatch):
    monkeypatch.setattr(fetcher, "MAX_BYTES", 11)  # cuts the curly apostrophe in half
    web({"zzqx.test/": httpx.Response(200, headers={"Content-Type": "text/html"}, content="<p>Caf\u00e9 \u2019s</p>".encode("utf-8"))})
    text = fetcher.fetch(HOME, {})["text"]
    assert text.startswith("Caf\u00e9") and "\u00c3" not in text


def test_a_long_utf8_page_with_one_stray_byte_is_not_garbled(web):
    body = ("<p>" + "Caf\u00e9 cr\u00e8me. " * 200 + "</p>").encode("utf-8") + b"\xff" + "<p>The end\u2019s here.</p>".encode("utf-8")
    web({"zzqx.test/": httpx.Response(200, headers={"Content-Type": "text/html"}, content=body)})
    text = fetcher.fetch(HOME, {})["text"]
    assert "\u00c3" not in text and "The end\u2019s here." in text


def test_a_latin1_page_with_no_charset_still_reads(web):
    web({"zzqx.test/": httpx.Response(200, headers={"Content-Type": "text/html"}, content="<p>Caf\u00e9 cr\u00e8me</p>".encode("latin-1"))})
    assert fetcher.fetch(HOME, {})["text"] == "Caf\u00e9 cr\u00e8me"


@pytest.mark.parametrize("addresses", [["64:ff9b::a00:1"], ["::a00:1"], ["::ffff:0:a00:1"], ["2002:a00:1::1"]])
def test_ipv6_forms_of_a_private_ipv4_address_are_refused(web, addresses):
    web({"zzqx.test/": ok(page("Hello"))}, names={"zzqx.test": addresses})
    with pytest.raises(fetcher.Refused) as e:
        fetcher.fetch(HOME, {})
    assert e.value.reason == "address"


def test_a_malformed_redirect_is_refused_not_raised(web):
    web({"zzqx.test/": httpx.Response(302, headers={"Location": "http://[zz/"})})
    with pytest.raises(fetcher.Refused):
        fetcher.fetch(HOME, {})
    assert fetcher.site(HOME) == ([], ["address"])


def test_a_malformed_link_is_skipped(web):
    web({"zzqx.test/": ok(page("Home", links=[("http://[zz/about", "About us"), ("/careers", "Careers")])),
         "zzqx.test/careers": ok(page("Careers text"))})
    assert [p["url"] for p in fetcher.site(HOME)[0]] == ["https://zzqx.test/", "https://zzqx.test/careers"]
