"""Reading an employer's public website, safely.

The server fetches addresses that come from users and from redirects, so every request:
- goes only to http or https, on the standard ports;
- resolves the host itself and refuses unless every address it resolves to is public, then
  connects to the address it checked (the host name is kept for the certificate), so neither a
  redirect nor a name that resolves differently the second time can reach a private network;
- asks robots.txt first (RFC 9309: missing means allowed, unreachable means not allowed);
- stops at a size limit, a time limit and a page limit, and reads HTML only;
- says who it is in its user agent."""
import ipaddress
import re
import socket
import time
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx

import textify
from parallel import together

USER_AGENT = "UKCareerNavigator/1.0 (interview preparation; reads public pages only)"
ROBOTS_AGENT = "UKCareerNavigator"
MAX_BYTES = 1_000_000      # decoded text read from one page; the rest is not read
ROBOTS_BYTES = 200_000
TIMEOUT_S = 8              # for one page, from the first request to the last byte
MAX_REDIRECTS = 3
MAX_EXTRA_PAGES = 5        # pages read besides the home page
USEFUL = re.compile(r"about|careers?|jobs|values|culture|mission|who[- ]we[- ]are|what[- ]we[- ]do|our[- ]story|news|press", re.I)
NOT_PAGES = re.compile(r"\.(pdf|docx?|xlsx?|pptx?|zip|jpe?g|png|gif|svg|webp|mp4|mp3)$", re.I)
# Form controls are hidden, not forms: older sites (ASP.NET) wrap the whole page in one form
WEBSITE_HIDDEN = ("head", "nav", "header", "footer", "noscript", "template", "svg", "button", "select", "textarea")
HTML_TYPES = ("text/html", "application/xhtml+xml")
META_CHARSET = re.compile(rb"""<meta[^>]+charset\s*=\s*["']?([A-Za-z0-9_\-]+)""", re.I)
# IPv6 ranges that carry an IPv4 address inside them (NAT64, IPv4-compatible, IPv4-translated):
# refused outright rather than trusting what they lead to
EMBEDS_IPV4 = tuple(ipaddress.ip_network(n) for n in ("64:ff9b::/96", "64:ff9b:1::/48", "::/96", "::ffff:0:0:0/96"))
MOJIBAKE_SHARE = 0.01  # a page that is mostly UTF-8 with a stray bad byte is still read as UTF-8
HOST = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$")


class Refused(Exception):
    """A page that was not read, and why: address, robots, redirects, not_html, timeout, unreachable or status."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT_S, follow_redirects=False, trust_env=False)


def _resolve(host: str, port: int) -> list[str]:
    return [info[4][0] for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)]


def _literal(host: str):
    try:
        return ipaddress.ip_address(host.split("%")[0])
    except ValueError:
        return None


def _public(address) -> bool:
    if address.version == 6:
        if address.ipv4_mapped:
            address = address.ipv4_mapped
        elif any(address in network for network in EMBEDS_IPV4):
            return False
        else:
            inner = address.sixtofour or (address.teredo[1] if address.teredo else None)
            if inner and not inner.is_global:
                return False
    return address.is_global and not address.is_multicast


# ---------- what the user types ----------

def website(raw: str) -> str | None:
    """A typed address as the site's home page, https://host/, or None when it is not a plain
    public host name: no user name, no port but the standard ones, no IP address."""
    typed = (raw or "").strip()
    if not typed or any(c.isspace() for c in typed):
        return None
    if "://" not in typed:
        typed = "https://" + typed
    try:
        url = urlsplit(typed)
        port = url.port
    except ValueError:
        return None
    host = (url.hostname or "").rstrip(".")
    if url.scheme not in ("http", "https") or url.username is not None or url.password is not None or port not in (None, 80, 443):
        return None
    if _literal(host) or not HOST.match(host):
        return None
    return f"https://{host}/"


# ---------- one request ----------

def _address(host: str, port: int) -> str:
    """The checked address to connect to, or Refused."""
    literal = _literal(host)
    if literal:
        if not _public(literal):
            raise Refused("address")
        return str(literal)
    try:
        found = _resolve(host, port)
    except OSError:
        raise Refused("unreachable") from None
    addresses = [_literal(a) for a in found]
    if not addresses or any(a is None or not _public(a) for a in addresses):
        raise Refused("address" if addresses else "unreachable")
    return str(addresses[0])


def _send(client: httpx.Client, url: str, deadline: float) -> httpx.Response:
    """One GET to the checked address of the URL's host, as a stream. No redirects followed."""
    if time.monotonic() > deadline:
        raise Refused("timeout")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise Refused("address") from None
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username is not None:
        raise Refused("address")
    if port not in (None, 80, 443):
        raise Refused("address")
    host = parts.hostname
    address = _address(host, port or (443 if parts.scheme == "https" else 80))
    netloc = f"[{address}]" if ":" in address else address
    target = urlunsplit((parts.scheme, netloc + (f":{port}" if port else ""), parts.path or "/", parts.query, ""))
    # uncompressed, so the size limit applies to what arrives rather than to what it expands into
    request = client.build_request("GET", target, headers={"Host": host, "User-Agent": USER_AGENT, "Accept-Encoding": "identity",
                                                            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1"},
                                   extensions={"sni_hostname": host})
    try:
        return client.send(request, stream=True)
    except httpx.TimeoutException:
        raise Refused("timeout") from None
    except (httpx.HTTPError, ValueError):
        raise Refused("unreachable") from None


def _open(client: httpx.Client, url: str, robots: dict | None, deadline: float) -> tuple[httpx.Response, str]:
    """Follow up to MAX_REDIRECTS redirects, checking every hop. Returns the final response and address."""
    for _ in range(MAX_REDIRECTS + 1):
        if robots is not None and not _allowed(url, robots):
            raise Refused("robots")
        response = _send(client, url, deadline)
        if not response.is_redirect:
            return response, url
        response.close()
        try:
            url = urljoin(url, response.headers.get("location", ""))
        except ValueError:  # a malformed address is a refusal, never a crash
            raise Refused("address") from None
    raise Refused("redirects")


def _read(response: httpx.Response, limit: int, deadline: float) -> bytes:
    """The body, at most `limit` bytes; a page still arriving at the deadline is given up. The clock
    is read after every piece that arrives, so a page sent a little at a time cannot run on."""
    body = bytearray()
    try:
        for chunk in response.iter_bytes():
            body += chunk
            if len(body) >= limit:
                break
            if time.monotonic() > deadline:
                raise Refused("timeout")
    except httpx.TimeoutException:
        raise Refused("timeout") from None
    except httpx.HTTPError:
        raise Refused("unreachable") from None
    finally:
        response.close()
    return bytes(body[:limit])


def _decode(response: httpx.Response, body: bytes) -> str:
    """The page's text in the encoding it declares; with none, UTF-8 unless the bytes plainly are not
    (then Windows-1252). A character cut at the size limit, or one stray byte, never turns the whole
    page into mojibake."""
    charset = response.charset_encoding
    if not charset:
        found = META_CHARSET.search(body[:4096])
        charset = found.group(1).decode() if found else None
    if charset:
        try:
            return body.decode(charset, errors="replace")
        except LookupError:
            pass
    text = body.decode("utf-8", errors="replace")
    if text.count("\ufffd") <= max(1, len(text) * MOJIBAKE_SHARE):
        return text
    return body.decode("cp1252", errors="replace")


# ---------- robots.txt ----------

def _allowed(url: str, robots: dict) -> bool:
    """Whether robots.txt lets this app read the URL. Read once per host and kept in `robots`."""
    parts = urlsplit(url)
    origin = f"{parts.scheme}://{parts.netloc}"
    if origin not in robots:
        robots[origin] = _robots(origin)
    rules = robots[origin]
    return rules if isinstance(rules, bool) else rules.can_fetch(ROBOTS_AGENT, url)


def _robots(origin: str) -> RobotFileParser | bool:
    deadline = time.monotonic() + TIMEOUT_S
    try:
        with _client() as client:
            response, _ = _open(client, origin + "/robots.txt", None, deadline)
            if 400 <= response.status_code < 500:
                response.close()
                return True   # no robots.txt: everything is allowed
            if response.status_code != 200:
                response.close()
                return False  # the server could not say: read nothing
            text = _decode(response, _read(response, ROBOTS_BYTES, deadline))
    except Refused as e:
        if e.reason in ("address", "unreachable"):
            raise  # the host itself cannot or may not be reached
        return False
    rules = RobotFileParser()
    rules.parse(text.splitlines())
    return rules


# ---------- a page ----------

class _Page(HTMLParser):
    """The page's title and its links, with the text of each."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title, self.links, self.in_title, self.link, self.titled = "", [], False, None, False

    def handle_starttag(self, tag, attrs):
        if tag == "title" and not self.titled:  # the first title is the page's; later ones belong to icons
            self.in_title = True
        elif tag == "a":
            href = dict(attrs).get("href")
            self.link = [href, ""] if href else None

    def handle_endtag(self, tag):
        if tag == "title" and self.in_title:
            self.in_title, self.titled = False, True
        elif tag == "a" and self.link:
            self.links.append((self.link[0], " ".join(self.link[1].split())))
            self.link = None

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        if self.link:
            self.link[1] += data


def fetch(url: str, robots: dict) -> dict:
    """One page as {url (after redirects), title, text, links: [(href, link text)]}, or Refused."""
    deadline = time.monotonic() + TIMEOUT_S
    with _client() as client:
        response, final = _open(client, url, robots, deadline)
        if response.status_code != 200:
            response.close()
            raise Refused("status")
        kind = response.headers.get("content-type", "").split(";")[0].strip().lower()
        if kind not in HTML_TYPES:
            response.close()
            raise Refused("not_html")
        html = _decode(response, _read(response, MAX_BYTES, deadline))
    found = _Page()
    found.feed(html)
    found.close()
    return {"url": final, "title": " ".join(found.title.split()), "text": textify.text(html, WEBSITE_HIDDEN)[:MAX_BYTES],
            "links": found.links}


def _attempt(address: str, robots: dict) -> dict | str:
    """A page with some text, or the reason it was not read ("empty" for a page with no text)."""
    try:
        page = fetch(address, robots)
    except Refused as e:
        return e.reason
    except (ValueError, httpx.InvalidURL):
        return "address"
    return page if page["text"].strip() else "empty"


def _site_host(host: str) -> str:
    return host.lower().removeprefix("www.")


def site(home: str) -> tuple[list[dict], list[str]]:
    """The home page and up to MAX_EXTRA_PAGES pages of the same site whose link looks like about,
    careers, values, news and the like, as [{url, title, text}], with the reason each page that
    could not be read was refused. Never raises."""
    robots = {}
    first = _attempt(home, robots)
    if isinstance(first, str):
        return [], [first]
    host = _site_host(urlsplit(first["url"]).hostname or "")
    wanted, seen = [], {first["url"].rstrip("/")}
    for href, label in first["links"]:
        try:
            parts = urlsplit(urljoin(first["url"], href))
            parts.port  # a malformed address raises here rather than later
        except ValueError:
            continue
        if parts.scheme not in ("http", "https") or _site_host(parts.hostname or "") != host or NOT_PAGES.search(parts.path):
            continue
        address = urlunsplit((parts.scheme, parts.netloc, parts.path or "/", "", ""))
        if address.rstrip("/") in seen or not (USEFUL.search(parts.path) or USEFUL.search(label)):
            continue
        seen.add(address.rstrip("/"))
        wanted.append(address)
        if len(wanted) == MAX_EXTRA_PAGES:
            break

    results = together(lambda address: _attempt(address, robots), wanted)
    pages = [{k: p[k] for k in ("url", "title", "text")} for p in [first, *results] if isinstance(p, dict)]
    return pages, [r for r in results if isinstance(r, str)]
