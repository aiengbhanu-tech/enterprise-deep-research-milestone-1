import pytest
from app.core.url_safety import UnsafeURLError, normalize_url, validate_public_url


def test_normalize_url_removes_fragment_and_default_port() -> None:
    assert normalize_url("HTTPS://Example.COM:443/path?q=1#section") == (
        "https://example.com/path?q=1"
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://169.254.169.254/latest/meta-data",
        "http://10.0.0.1/private",
        "file:///etc/passwd",
        "http://localhost:8000",
        "http://user:password@example.com",
    ],
)
async def test_validate_public_url_blocks_ssrf_targets(url: str) -> None:
    with pytest.raises(UnsafeURLError):
        await validate_public_url(url)
