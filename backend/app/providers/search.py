from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import get_settings


@dataclass(frozen=True)
class SearchResult:
    url: str
    title: str
    snippet: str = ""
    score: float = 0.0


class SearchProvider(Protocol):
    name: str

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]: ...


class MockSearchProvider:
    name = "mock"

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        return []


class TavilySearchProvider:
    name = "tavily"

    def __init__(self, api_key: str, timeout_seconds: float = 20) -> None:
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": self.api_key,
                    "query": query,
                    "search_depth": "advanced",
                    "max_results": max_results,
                    "include_raw_content": False,
                },
            )
            response.raise_for_status()
        return [
            SearchResult(
                url=item["url"],
                title=item.get("title", ""),
                snippet=item.get("content", ""),
                score=float(item.get("score", 0)),
            )
            for item in response.json().get("results", [])
            if item.get("url")
        ]


def get_search_provider() -> SearchProvider:
    settings = get_settings()
    if settings.search_provider == "tavily":
        if not settings.tavily_api_key:
            raise RuntimeError("TAVILY_API_KEY is required when SEARCH_PROVIDER=tavily")
        return TavilySearchProvider(settings.tavily_api_key, settings.fetch_timeout_seconds)
    return MockSearchProvider()
