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
WEBSITE_HIDDEN = ("head", "nav", "header", "footer", "form", "noscript", "template", "svg")
HTML_TYPES = ("text/html", "application/xhtml+xml")
META_CHARSET = re.compile(rb"""<meta[^>]+charset\s*=\s*["']?([A-Za-z0-9_\-]+)""", re.I)
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
    if address.version == 6 and address.ipv4_mapped:
        address = address.ipv4_mapped
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


def _send(client: httpx.Client, url: str) -> httpx.Response:
    """One GET to the checked address of the URL's host, as a stream. No redirects followed."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username is not None:
        raise Refused("address")
    try:
        port = parts.port
    except ValueError:
        raise Refused("address") from None
    if port not in (None, 80, 443):
        raise Refused("address")
    host = parts.hostname
    address = _address(host, port or (443 if parts.scheme == "https" else 80))
    netloc = f"[{address}]" if ":" in address else address
    target = urlunsplit((parts.scheme, netloc + (f":{port}" if port else ""), parts.path or "/", parts.query, ""))
    request = client.build_request("GET", target, headers={"Host": host, "User-Agent": USER_AGENT,
                                                            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1"},
                                   extensions={"sni_hostname": host})
    try:
        return client.send(request, stream=True)
    except httpx.TimeoutException:
        raise Refused("timeout") from None
    except httpx.HTTPError:
        raise Refused("unreachable") from None


def _open(client: httpx.Client, url: str, robots: dict | None) -> tuple[httpx.Response, str]:
    """Follow up to MAX_REDIRECTS redirects, checking every hop. Returns the final response and address."""
    for _ in range(MAX_REDIRECTS + 1):
        if robots is not None and not _allowed(url, robots):
            raise Refused("robots")
        response = _send(client, url)
        if not response.is_redirect:
            return response, url
        response.close()
        url = urljoin(url, response.headers.get("location", ""))
    raise Refused("redirects")


def _read(response: httpx.Response, limit: int, started: float) -> bytes:
    """The decoded body, at most `limit` bytes; a page still arriving after TIMEOUT_S is given up."""
    body = bytearray()
    try:
        for chunk in response.iter_bytes(chunk_size=65_536):
            body += chunk
            if len(body) >= limit:
                break
            if time.monotonic() - started > TIMEOUT_S:
                raise Refused("timeout")
    except httpx.TimeoutException:
        raise Refused("timeout") from None
    except httpx.HTTPError:
        raise Refused("unreachable") from None
    finally:
        response.close()
    return bytes(body[:limit])


def _decode(response: httpx.Response, body: bytes) -> str:
    charset = response.charset_encoding
    if not charset:
        found = META_CHARSET.search(body[:4096])
        charset = found.group(1).decode() if found else None
    for encoding in (charset, "utf-8", "cp1252"):
        if not encoding:
            continue
        try:
            return body.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return body.decode("utf-8", errors="replace")


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
    started = time.monotonic()
    try:
        with _client() as client:
            response, _ = _open(client, origin + "/robots.txt", None)
            if 400 <= response.status_code < 500:
                response.close()
                return True   # no robots.txt: everything is allowed
            if response.status_code != 200:
                response.close()
                return False  # the server could not say: read nothing
            text = _decode(response, _read(response, ROBOTS_BYTES, started))
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
    started = time.monotonic()
    with _client() as client:
        response, final = _open(client, url, robots)
        if response.status_code != 200:
            response.close()
            raise Refused("status")
        kind = response.headers.get("content-type", "").split(";")[0].strip().lower()
        if kind not in HTML_TYPES:
            response.close()
            raise Refused("not_html")
        html = _decode(response, _read(response, MAX_BYTES, started))
    found = _Page()
    found.feed(html)
    found.close()
    return {"url": final, "title": " ".join(found.title.split()), "text": textify.text(html, WEBSITE_HIDDEN)[:MAX_BYTES],
            "links": found.links}


def _site_host(host: str) -> str:
    return host.lower().removeprefix("www.")


def site(home: str) -> tuple[list[dict], list[str]]:
    """The home page and up to MAX_EXTRA_PAGES pages of the same site whose link looks like about,
    careers, values, news and the like, as [{url, title, text}], with the reason each page that
    could not be read was refused. Never raises."""
    robots = {}
    try:
        first = fetch(home, robots)
    except Refused as e:
        return [], [e.reason]
    host = _site_host(urlsplit(first["url"]).hostname or "")
    wanted, seen = [], {first["url"].rstrip("/")}
    for href, label in first["links"]:
        parts = urlsplit(urljoin(first["url"], href))
        if parts.scheme not in ("http", "https") or _site_host(parts.hostname or "") != host or NOT_PAGES.search(parts.path):
            continue
        address = urlunsplit((parts.scheme, parts.netloc, parts.path or "/", "", ""))
        if address.rstrip("/") in seen or not (USEFUL.search(parts.path) or USEFUL.search(label)):
            continue
        seen.add(address.rstrip("/"))
        wanted.append(address)
        if len(wanted) == MAX_EXTRA_PAGES:
            break

    def attempt(address):
        try:
            return fetch(address, robots)
        except Refused as e:
            return e.reason
    results = together(attempt, wanted)
    pages = [{k: p[k] for k in ("url", "title", "text")} for p in [first, *results] if isinstance(p, dict)]
    return pages, [r for r in results if isinstance(r, str)]
