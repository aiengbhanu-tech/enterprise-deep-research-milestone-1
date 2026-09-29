import hashlib
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.core.config import get_settings
from app.core.url_safety import validate_public_url

settings = get_settings()


@dataclass(frozen=True)
class FetchedDocument:
    url: str
    title: str
    text: str
    content_type: str
    content_hash: str


def extract_html(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    for element in soup(["script", "style", "noscript", "svg", "nav", "footer"]):
        element.decompose()
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    blocks = [
        element.get_text(" ", strip=True)
        for element in soup.select("article p, main p, h1, h2, h3, body p")
    ]
    text = "\n\n".join(dict.fromkeys(block for block in blocks if len(block) >= 40))
    return title, text


async def fetch_document(url: str, max_redirects: int = 5) -> FetchedDocument:
    current_url = await validate_public_url(url)
    headers = {"User-Agent": "EnterpriseDeepResearchBot/0.2 (+research; contact=local)"}
    async with httpx.AsyncClient(
        timeout=settings.fetch_timeout_seconds, follow_redirects=False, headers=headers
    ) as client:
        for _ in range(max_redirects + 1):
            async with client.stream("GET", current_url) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise httpx.HTTPError("Redirect missing Location header")
                    current_url = await validate_public_url(urljoin(current_url, location))
                    continue
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").split(";")[0].lower()
                if content_type not in {"text/html", "text/plain"}:
                    raise ValueError(f"Unsupported content type: {content_type or 'unknown'}")
                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > settings.max_source_bytes:
                        raise ValueError("Source exceeds MAX_SOURCE_BYTES")
                    chunks.append(chunk)
                raw = b"".join(chunks)
                decoded = raw.decode(response.encoding or "utf-8", errors="replace")
                title, text = (
                    extract_html(decoded) if content_type == "text/html" else ("", decoded)
                )
                return FetchedDocument(
                    url=current_url,
                    title=title,
                    text=text,
                    content_type=content_type,
                    content_hash=hashlib.sha256(raw).hexdigest(),
                )
    raise httpx.TooManyRedirects("Too many redirects")
