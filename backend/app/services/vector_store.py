import hashlib
import re
from uuid import UUID

from qdrant_client import AsyncQdrantClient, models

from app.core.config import get_settings

settings = get_settings()


def sparse_vector(text: str) -> models.SparseVector:
    counts: dict[int, float] = {}
    for token in re.findall(r"[a-z0-9]{2,}", text.lower()):
        index = int.from_bytes(hashlib.blake2b(token.encode(), digest_size=4).digest(), "big")
        counts[index] = counts.get(index, 0) + 1.0
    ordered = sorted(counts.items())
    return models.SparseVector(
        indices=[item[0] for item in ordered], values=[item[1] for item in ordered]
    )


async def index_evidence(evidence_id: UUID, run_id: UUID, source_id: UUID, passage: str) -> None:
    client = AsyncQdrantClient(url=settings.qdrant_url, timeout=10)
    try:
        if not await client.collection_exists(settings.qdrant_collection):
            await client.create_collection(
                collection_name=settings.qdrant_collection,
                sparse_vectors_config={"text": models.SparseVectorParams()},
            )
        await client.upsert(
            collection_name=settings.qdrant_collection,
            points=[
                models.PointStruct(
                    id=str(evidence_id),
                    vector={"text": sparse_vector(passage)},
                    payload={"run_id": str(run_id), "source_id": str(source_id)},
                )
            ],
        )
    finally:
        await client.close()
