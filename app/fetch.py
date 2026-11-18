"""Download a past-paper PDF from a link, safely (no internal addresses, size-capped)."""
import ipaddress
import socket
from collections.abc import Callable
from pathlib import PurePosixPath
from urllib.parse import unquote, urljoin, urlparse

import httpx

MAX_BYTES = 50 * 1024 * 1024
MAX_REDIRECTS = 5


class FetchError(Exception):
    """A friendly message for the parent."""


def _system_resolve(host: str) -> list[str]:
    return [info[4][0] for info in socket.getaddrinfo(host, None)]


def _check_url(url: str, resolve: Callable[[str], list[str]]) -> None:
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise FetchError("That doesn't look like a web link. It should start with http:// or https://")
    try:
        addrs = resolve(p.hostname)
    except OSError:
        raise FetchError(f"Couldn't find the website {p.hostname}.")
    for a in addrs:
        ip = ipaddress.ip_address(a.split("%")[0])
        if not ip.is_global:
            raise FetchError("That link points to a private or internal address, which isn't allowed.")


def _filename(url: str) -> str:
    name = PurePosixPath(unquote(urlparse(url).path)).name
    return name if name else "paper.pdf"


def fetch_pdf(url: str, transport: httpx.BaseTransport | None = None,
              resolve: Callable[[str], list[str]] | None = None, max_bytes: int = MAX_BYTES) -> tuple[str, bytes]:
    resolve = resolve or _system_resolve
    url = url.strip()
    with httpx.Client(transport=transport, follow_redirects=False, timeout=30,
                      headers={"User-Agent": "olympiad-practice/1.0"}) as client:
        for _ in range(MAX_REDIRECTS + 1):
            _check_url(url, resolve)
            try:
                with client.stream("GET", url) as resp:
                    if resp.is_redirect:
                        url = urljoin(url, resp.headers.get("location", ""))
                        continue
                    if resp.status_code != 200:
                        raise FetchError(f"The website answered with error {resp.status_code}.")
                    data = bytearray()
                    for chunk in resp.iter_bytes():
                        data.extend(chunk)
                        if len(data) > max_bytes:
                            raise FetchError("That file is too big (over 50 MB).")
            except httpx.HTTPError as e:
                raise FetchError(f"Couldn't download the file ({type(e).__name__}).") from e
            if not bytes(data[:1024]).lstrip().startswith(b"%PDF"):
                raise FetchError("That link isn't a PDF. Open it in your browser and copy the link to the PDF itself.")
            return _filename(url), bytes(data)
    raise FetchError("That link redirects too many times.")
