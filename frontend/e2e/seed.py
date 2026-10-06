from pathlib import Path
from uuid import uuid4

import asyncio
import json

from app.infrastructure.database.models import KnowledgeUnitModel, PostModel, SourceModel, TopicModel
from app.infrastructure.database.session import SessionFactory

SEED_FILE = Path(__file__).resolve().parent / ".seed.json"


async def main() -> None:
    source_id, topic_id, unit_id, post_id = uuid4(), uuid4(), uuid4(), uuid4()
    async with SessionFactory() as session:
        session.add_all([
            SourceModel(
                id=source_id,
                filename="e2e-book.pdf",
                mime_type="application/pdf",
                storage_path="./storage/test/e2e-book.pdf",
                size_bytes=10,
                status="STORED",
                book_title="E2E Book",
            ),
            TopicModel(id=topic_id, source_id=source_id, position=1, title="E2E Topic", description="E2E"),
            KnowledgeUnitModel(
                id=unit_id,
                source_id=source_id,
                topic_id=topic_id,
                position=1,
                title="E2E Approved Post",
                kind="حكمة",
                content="E2E content",
            ),
            PostModel(
                id=post_id,
                knowledge_unit_id=unit_id,
                content="E2E approved content",
                status="APPROVED",
                review_note="E2E seed",
            ),
        ])
        await session.commit()

    SEED_FILE.write_text(json.dumps({"post_id": str(post_id)}), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
