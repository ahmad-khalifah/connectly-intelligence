"""Fetch a public web page or PDF that a researcher submitted, safely.

* Only http(s) URLs on public addresses. Every redirect hop is re-checked, so the server
  cannot be pointed at itself, the database or a private network.
* Google grounding redirect links are refused: the researcher must open the source and
  submit the page's own address (Google's terms forbid storing those links).
* Size and time are capped. Only HTML, plain text and PDF are read.
"""

from __future__ import annotations

import hashlib
import io
import ipaddress
import json
import re
import socket
from dataclasses import dataclass
from datetime import UTC, date, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx

MAX_BYTES = 8 * 1024 * 1024
MAX_REDIRECTS = 5
TIMEOUT = 30.0
USER_AGENT = "ConnectlyIntelligence/1.0 (research source retrieval)"
READABLE = ("text/html", "application/xhtml+xml", "text/plain", "application/pdf")
GROUNDING_REDIRECT_HOSTS = ("vertexaisearch.cloud.google.com",)


class FetchError(ValueError):
    pass


@dataclass
class FetchedDoc:
    url: str
    final_url: str
    content_type: str
    title: str | None
    publisher: str | None
    published_on: date | None
    published_basis: str | None
    text: str
    sha256: str
    retrieved_at: datetime


def check_url(url: str, resolve: bool = True) -> str:
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise FetchError("Only http and https web addresses can be analysed.")
    if parts.username or parts.password:
        raise FetchError("Addresses with a user name or password are not accepted.")
    host = parts.hostname.lower()
    if host.endswith(GROUNDING_REDIRECT_HOSTS):
        raise FetchError(
            "This is a Google Search redirect link. Open the source, then submit the page's "
            "own address from your browser's address bar."
        )
    if host in ("localhost",) or host.endswith((".local", ".internal", ".localhost")):
        raise FetchError("Local and internal addresses cannot be fetched.")
    try:
        literal = [ipaddress.ip_address(host.strip("[]"))]
    except ValueError:
        literal = None
    if literal is not None:
        addresses = literal
    elif resolve:
        try:
            infos = socket.getaddrinfo(host, parts.port or (443 if parts.scheme == "https" else 80))
        except OSError:
            raise FetchError(f"The address {host} could not be found.") from None
        addresses = [ipaddress.ip_address(info[4][0]) for info in infos]
    else:
        addresses = []
    for ip in addresses:
        if not ip.is_global or ip.is_multicast:
            raise FetchError("This address points to a private or reserved network.")
    return url.strip()


def fetch(
    url: str, transport: httpx.BaseTransport | None = None, resolve: bool = True
) -> FetchedDoc:
    current = check_url(url, resolve)
    with httpx.Client(
        transport=transport,
        timeout=TIMEOUT,
        follow_redirects=False,
        headers={"User-Agent": USER_AGENT, "Accept": ", ".join(READABLE)},
    ) as client:
        for _ in range(MAX_REDIRECTS + 1):
            try:
                with client.stream("GET", current) as r:
                    if r.status_code in (301, 302, 303, 307, 308):
                        current = check_url(
                            urljoin(current, r.headers.get("location", "")), resolve
                        )
                        continue
                    if r.status_code != 200:
                        raise FetchError(f"The page returned HTTP {r.status_code}.")
                    ctype = r.headers.get("content-type", "").split(";")[0].strip().lower()
                    if ctype not in READABLE:
                        raise FetchError(
                            f"Content of type {ctype or 'unknown'} cannot be analysed."
                        )
                    body = bytearray()
                    for chunk in r.iter_bytes():
                        body.extend(chunk)
                        if len(body) > MAX_BYTES:
                            raise FetchError("The document is larger than 8 MB.")
                    charset = r.charset_encoding or "utf-8"
                    break
            except httpx.HTTPError as e:
                raise FetchError(f"The page could not be retrieved ({type(e).__name__}).") from None
        else:
            raise FetchError("Too many redirects.")
    raw = bytes(body)
    retrieved = datetime.now(tz=UTC)
    host = urlsplit(current).hostname
    if ctype == "application/pdf":
        title, published, basis, text_ = _pdf(raw)
        publisher = host
    elif ctype == "text/plain":
        title, publisher, published, basis = None, host, None, None
        text_ = raw.decode(charset, errors="replace")
    else:
        page = _Page()
        page.feed(raw.decode(charset, errors="replace"))
        text_ = page.text()
        title = page.meta.get("og:title") or page.title
        publisher = page.meta.get("og:site_name") or host
        published, basis = page.published()
    text_ = re.sub(r"[ \t\r\f\v]+", " ", text_)
    text_ = re.sub(r"\n\s*\n+", "\n\n", text_).strip()
    if len(text_) < 200:
        raise FetchError("Too little readable text was found on this page.")
    return FetchedDoc(
        url=url.strip(),
        final_url=current,
        content_type=ctype,
        title=(title or "").strip()[:500] or None,
        publisher=(publisher or "")[:255] or None,
        published_on=published,
        published_basis=basis,
        text=text_,
        sha256=hashlib.sha256(text_.encode()).hexdigest(),
        retrieved_at=retrieved,
    )


DATE_META = (
    "article:published_time",
    "datepublished",
    "citation_publication_date",
    "citation_date",
    "dc.date",
    "dc.date.issued",
    "dcterms.issued",
    "date",
    "pubdate",
)


def _parse_date(value: str) -> date | None:
    value = value.strip()
    for pattern, fmt in (
        (r"^\d{4}-\d{2}-\d{2}", "%Y-%m-%d"),
        (r"^\d{4}/\d{2}/\d{2}", "%Y/%m/%d"),
    ):
        m = re.match(pattern, value)
        if m:
            try:
                return datetime.strptime(m.group(0), fmt).date()
            except ValueError:
                return None
    return None


class _Page(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "template", "iframe"}
    BLOCK = {
        "p",
        "div",
        "li",
        "br",
        "tr",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "section",
        "article",
        "table",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.meta: dict[str, str] = {}
        self.title: str | None = None
        self.times: list[str] = []
        self.ld_json: list[str] = []
        self._skip = 0
        self._in_title = False
        self._in_ld = False

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            key = (a.get("property") or a.get("name") or a.get("itemprop") or "").lower()
            if key and a.get("content"):
                self.meta.setdefault(key, a["content"])
        elif tag == "time" and a.get("datetime"):
            self.times.append(a["datetime"])
        elif tag == "title":
            self._in_title = True
        elif tag == "script" and a.get("type", "").lower() == "application/ld+json":
            self._in_ld = True
        if tag in self.SKIP:
            self._skip += 1
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        if tag == "title":
            self._in_title = False
        if tag == "script":
            self._in_ld = False
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title = (self.title or "") + data
        elif self._in_ld:
            self.ld_json.append(data)
        elif not self._skip:
            self.parts.append(data)

    def text(self) -> str:
        return "".join(self.parts)

    def published(self) -> tuple[date | None, str | None]:
        for key in DATE_META:
            if key in self.meta and (d := _parse_date(self.meta[key])):
                return d, f"page metadata ({key})"
        for blob in self.ld_json:
            try:
                data = json.loads(blob)
            except ValueError:
                continue
            for obj in data if isinstance(data, list) else [data]:
                if isinstance(obj, dict) and (d := _parse_date(str(obj.get("datePublished", "")))):
                    return d, "page structured data (datePublished)"
        if len(self.times) == 1 and (d := _parse_date(self.times[0])):
            return d, "page <time> element"
        return None, None


def _pdf(raw: bytes) -> tuple[str | None, date | None, str | None, str]:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(raw))
        pages = [p.extract_text() or "" for p in reader.pages[:200]]
    except Exception:  # noqa: BLE001 - any parser failure means the PDF is unreadable
        raise FetchError("The PDF could not be read.") from None
    info = reader.metadata or {}
    title = str(info.get("/Title") or "") or None
    created = str(info.get("/CreationDate") or "")
    published = None
    m = re.match(r"D:(\d{4})(\d{2})(\d{2})", created)
    if m:
        try:
            published = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            published = None
    basis = "PDF creation date (may differ from publication)" if published else None
    return title, published, basis, "\n\n".join(pages)
