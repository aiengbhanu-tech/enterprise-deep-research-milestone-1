import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.url_safety import normalize_url
from app.db.session import SessionLocal
from app.models.evidence import (
    EvidenceItem,
    Source,
    ToolExecution,
)
from app.providers.search import (
    SearchResult,
    get_search_provider,
)
from app.services.execution_control import (
    RunCancelled,
    RunTimedOut,
    check_run_control,
    run_controlled,
)
from app.services.fetcher import (
    FetchedDocument,
    fetch_document,
)
from app.services.quality import score_source
from app.services.vector_store import index_evidence

settings = get_settings()


@dataclass(frozen=True)
class DiscoveredResult:
    query: str
    result: SearchResult


def build_queries(
    plan: list[dict[str, str]],
    user_query: str,
) -> list[tuple[str, str]]:
    return [
        (
            item["question"],
            (
                f"{user_query} {item['question']} "
                "recent authoritative sources"
            ),
        )
        for item in plan
    ]


async def _record_tool(
    run_id: UUID,
    tool_name: str,
    provider: str,
    status: str,
    started: float,
    input_metadata: dict,
    output_metadata: dict | None = None,
    error: str | None = None,
) -> None:
    async with SessionLocal() as session:
        session.add(
            ToolExecution(
                run_id=run_id,
                tool_name=tool_name,
                provider=provider,
                status=status,
                latency_ms=int(
                    (time.perf_counter() - started) * 1000
                ),
                attempt=1,
                estimated_cost_usd=Decimal("0"),
                input_metadata=input_metadata,
                output_metadata=output_metadata or {},
                error=error,
                created_at=datetime.now(UTC),
            )
        )

        await session.commit()


async def discover_sources(
    run_id: UUID,
    query_pairs: list[tuple[str, str]],
) -> list[DiscoveredResult]:
    provider = get_search_provider()
    semaphore = asyncio.Semaphore(
        settings.max_search_concurrency
    )

    async with SessionLocal() as session:
        searches_used = await session.scalar(
            select(func.count())
            .select_from(ToolExecution)
            .where(
                ToolExecution.run_id == run_id,
                ToolExecution.tool_name == "web_search",
            )
        )

    remaining_searches = max(
        settings.research_max_searches
        - (searches_used or 0),
        0,
    )
    query_pairs = query_pairs[:remaining_searches]

    async def search_one(
        question: str,
        query: str,
    ) -> list[DiscoveredResult]:
        started = time.perf_counter()

        try:
            async with semaphore:
                results = await run_controlled(
                    run_id,
                    provider.search(query, 5),
                    settings.search_timeout_seconds,
                )

            await _record_tool(
                run_id,
                "web_search",
                provider.name,
                "succeeded",
                started,
                {"query": query},
                {"result_count": len(results)},
            )

            return [
                DiscoveredResult(question, item)
                for item in results
            ]

        except (RunCancelled, RunTimedOut) as exc:
            await _record_tool(
                run_id,
                "web_search",
                provider.name,
                exc.terminal_status.value,
                started,
                {"query": query},
                error=str(exc)[:1000],
            )
            raise

        except asyncio.TimeoutError:
            await _record_tool(
                run_id,
                "web_search",
                provider.name,
                "timed_out",
                started,
                {"query": query},
                error="Search provider timeout",
            )
            return []

        except Exception as exc:
            await _record_tool(
                run_id,
                "web_search",
                provider.name,
                "failed",
                started,
                {"query": query},
                error=str(exc)[:1000],
            )
            return []

    tasks = [
        asyncio.create_task(search_one(*pair))
        for pair in query_pairs
    ]

    try:
        batches = await asyncio.gather(*tasks)
    except (RunCancelled, RunTimedOut):
        for task in tasks:
            task.cancel()

        await asyncio.gather(
            *tasks,
            return_exceptions=True,
        )
        raise

    deduplicated: dict[str, DiscoveredResult] = {}

    for item in (
        item
        for batch in batches
        for item in batch
    ):
        deduplicated.setdefault(
            normalize_url(item.result.url),
            item,
        )

    return list(deduplicated.values())


def extract_passages(
    text: str,
    maximum: int = 3,
) -> list[tuple[int, str]]:
    paragraphs = [
        part.strip()
        for part in text.split("\n\n")
        if len(part.strip()) >= 100
    ]

    return [
        (index, passage[:2_500])
        for index, passage in enumerate(
            paragraphs[:maximum]
        )
    ]


async def collect_evidence(
    run_id: UUID,
    discoveries: list[DiscoveredResult],
) -> list[dict]:
    semaphore = asyncio.Semaphore(
        settings.max_fetch_concurrency
    )

    async with SessionLocal() as session:
        sources_used = await session.scalar(
            select(func.count())
            .select_from(Source)
            .where(Source.run_id == run_id)
        )

    remaining_sources = max(
        settings.research_max_sources
        - (sources_used or 0),
        0,
    )

    async def fetch_one(
        item: DiscoveredResult,
    ) -> tuple[
        DiscoveredResult,
        FetchedDocument,
    ] | None:
        started = time.perf_counter()

        try:
            async with semaphore:
                document = await run_controlled(
                    run_id,
                    fetch_document(item.result.url),
                    settings.fetch_timeout_seconds,
                )

            await _record_tool(
                run_id,
                "web_fetch",
                "httpx",
                "succeeded",
                started,
                {"url": item.result.url},
                {
                    "bytes_of_text": len(document.text),
                },
            )

            return item, document

        except (RunCancelled, RunTimedOut) as exc:
            await _record_tool(
                run_id,
                "web_fetch",
                "httpx",
                exc.terminal_status.value,
                started,
                {"url": item.result.url},
                error=str(exc)[:1000],
            )
            raise

        except asyncio.TimeoutError:
            await _record_tool(
                run_id,
                "web_fetch",
                "httpx",
                "timed_out",
                started,
                {"url": item.result.url},
                error="Fetch timeout",
            )
            return None

        except Exception as exc:
            await _record_tool(
                run_id,
                "web_fetch",
                "httpx",
                "failed",
                started,
                {"url": item.result.url},
                error=str(exc)[:1000],
            )
            return None

    tasks = [
        asyncio.create_task(fetch_one(item))
        for item in discoveries[:remaining_sources]
    ]

    try:
        fetched = await asyncio.gather(*tasks)
    except (RunCancelled, RunTimedOut):
        for task in tasks:
            task.cancel()

        await asyncio.gather(
            *tasks,
            return_exceptions=True,
        )
        raise

    await check_run_control(run_id)

    evidence_payloads: list[dict] = []
    to_index: list[tuple[UUID, UUID, str]] = []

    async with SessionLocal() as session:
        for pair in (
            item
            for item in fetched
            if item is not None
        ):
            discovery, document = pair
            normalized = normalize_url(document.url)

            existing = await session.scalar(
                select(Source).where(
                    Source.run_id == run_id,
                    Source.normalized_url == normalized,
                )
            )

            if existing:
                continue

            quality = score_source(
                document.url,
                document.text,
            )

            source = Source(
                run_id=run_id,
                url=document.url,
                normalized_url=normalized,
                title=(
                    document.title
                    or discovery.result.title
                ),
                publisher=None,
                retrieved_at=datetime.now(UTC),
                content_type=document.content_type,
                content_hash=document.content_hash,
                raw_text=document.text,
                quality_score=quality.score,
                quality_details=quality.details,
                search_query=discovery.question,
            )

            session.add(source)
            await session.flush()

            for position, passage in extract_passages(
                document.text
            ):
                evidence = EvidenceItem(
                    run_id=run_id,
                    source_id=source.id,
                    question=discovery.question,
                    passage=passage,
                    locator={
                        "type": "paragraph",
                        "position": position,
                    },
                    relevance_score=max(
                        discovery.result.score,
                        0.5,
                    ),
                )

                session.add(evidence)
                await session.flush()

                to_index.append(
                    (
                        evidence.id,
                        source.id,
                        passage,
                    )
                )

                evidence_payloads.append(
                    {
                        "id": str(evidence.id),
                        "source_id": str(source.id),
                        "question": discovery.question,
                        "content": passage,
                        "source": document.url,
                        "source_quality": quality.score,
                    }
                )

        await session.commit()

    await asyncio.gather(
        *(
            index_evidence(
                evidence_id,
                run_id,
                source_id,
                passage,
            )
            for (
                evidence_id,
                source_id,
                passage,
            ) in to_index
        ),
        return_exceptions=True,
    )

    await check_run_control(run_id)

    return evidence_payloads


async def run_live_research(
    run_id: str,
    user_query: str,
    plan: list[dict[str, str]],
) -> list[dict]:
    run_uuid = UUID(run_id)

    await check_run_control(run_uuid)

    query_pairs = build_queries(
        plan,
        user_query,
    )

    discoveries = await discover_sources(
        run_uuid,
        query_pairs,
    )

    return await collect_evidence(
        run_uuid,
        discoveries,
    )