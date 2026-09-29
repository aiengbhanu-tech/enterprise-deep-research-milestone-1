import asyncio
import ipaddress
import socket
from urllib.parse import SplitResult, urlsplit, urlunsplit


class UnsafeURLError(ValueError):
    pass


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    hostname = (parts.hostname or "").lower()
    netloc = hostname
    if parts.port and not (
        (parts.scheme == "http" and parts.port == 80)
        or (parts.scheme == "https" and parts.port == 443)
    ):
        netloc = f"{hostname}:{parts.port}"
    path = parts.path or "/"
    return urlunsplit(SplitResult(parts.scheme.lower(), netloc, path, parts.query, ""))


def _is_forbidden_ip(value: str) -> bool:
    ip = ipaddress.ip_address(value)
    return not ip.is_global


async def validate_public_url(url: str) -> str:
    original_parts = urlsplit(url.strip())
    if original_parts.username or original_parts.password:
        raise UnsafeURLError("URLs containing credentials are blocked")
    normalized = normalize_url(url)
    parts = urlsplit(normalized)
    if parts.scheme not in {"http", "https"}:
        raise UnsafeURLError("Only HTTP and HTTPS URLs are allowed")
    if not parts.hostname or parts.username or parts.password:
        raise UnsafeURLError("URL must contain a public hostname and no credentials")
    if parts.hostname == "localhost" or parts.hostname.endswith(".local"):
        raise UnsafeURLError("Local hostnames are blocked")

    try:
        if _is_forbidden_ip(parts.hostname):
            raise UnsafeURLError("Private, reserved, and link-local addresses are blocked")
        return normalized
    except ValueError:
        pass

    loop = asyncio.get_running_loop()
    try:
        addresses = await loop.run_in_executor(
            None,
            lambda: socket.getaddrinfo(parts.hostname, parts.port or 443, type=socket.SOCK_STREAM),
        )
    except socket.gaierror as exc:
        raise UnsafeURLError("Hostname could not be resolved") from exc
    if not addresses or any(_is_forbidden_ip(item[4][0]) for item in addresses):
        raise UnsafeURLError("Hostname resolves to a non-public address")
    return normalized
