import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.application.artifacts import persist_generic_artifact
from app.application.generic_artifact_review import GenericArtifactReviewService
from app.application.recipe_engine import ProductionExecutionContext, RenderApprovedTextCardCapability
from app.domain.artifacts import Artifact, ArtifactKind, ArtifactStatus
from app.infrastructure.database.models import ArtifactModel, KnowledgeUnitModel, SourceModel
from app.infrastructure.database.session import SessionFactory


class MemoryCardStorage:
    def __init__(self):
        self.objects = {}

    async def ensure_available(self):
        return None

    async def put(self, *, key: str, content: bytes, content_type: str):
        assert content_type == "image/png"
        assert content.startswith(bytes.fromhex("89504e470d0a1a0a"))
        uri = f"s3://test/{key}"
        self.objects[uri] = content
        return uri

    async def delete(self, uri: str):
        self.objects.pop(uri, None)


def _pinned_contract(key: str, kind: str, mime_type: str, mode: str, required_fields: list[str]):
    return {
        "contract_id": str(uuid4()),
        "version_id": str(uuid4()),
        "key": key,
        "version": 1,
        "definition": {
            "artifact_kind": kind,
            "mime_type": mime_type,
            "content_mode": mode,
            "required_metadata_fields": required_fields,
            "max_content_chars": 10000 if mode == "INLINE" else None,
        },
    }


@pytest.mark.asyncio
async def test_approved_text_to_card_capability_persists_png_with_provenance(monkeypatch):
    font_candidates = [
        os.environ.get("NASHR_CARD_FONT_PATH"),
        "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]
    font_path = next((path for path in font_candidates if path and Path(path).is_file()), None)
    if font_path is None:
        pytest.skip("No Arabic-capable system font is installed in this test environment.")
    monkeypatch.setenv("NASHR_CARD_FONT_PATH", font_path)

    storage = MemoryCardStorage()
    source_id, unit_id, run_id = uuid4(), uuid4(), uuid4()
    text_contract = _pinned_contract("CARD_SOURCE_TEXT", "TEXT", "text/plain", "INLINE", ["language"])
    text_context = {"output_contract": text_contract}
    approved_text = "إِنَّ حفظَ النصِّ المعتمدِ أصلٌ لا يُعادُ توليدُه."

    async with SessionFactory() as session:
        session.add(SourceModel(
            id=source_id,
            filename="arabic-book.pdf",
            mime_type="application/pdf",
            storage_path=f"./storage/test/{source_id}.pdf",
            size_bytes=10,
            status="STORED",
            book_title="كتاب الأمثلة",
        ))
        session.add(KnowledgeUnitModel(
            id=unit_id,
            source_id=source_id,
            position=1,
            title="حفظ النص",
            content="مادة المصدر",
            source_reference="ص. 11",
        ))
        await session.commit()

        now = datetime.now(timezone.utc)
        text_artifact = Artifact(
            id=uuid4(),
            source_knowledge_unit_id=unit_id,
            kind=ArtifactKind.TEXT,
            content=approved_text,
            status=ArtifactStatus.AVAILABLE.value,
            created_at=now,
            updated_at=now,
            mime_type="text/plain",
            output_contract_key="CARD_SOURCE_TEXT",
            output_contract_version=1,
            resolved_context=text_context,
            metadata={"title": "النص المعتمد", "language": "ar"},
        )
        saved_text = await persist_generic_artifact(session, text_artifact, resolved_context=text_context)
        await GenericArtifactReviewService(session).approve(saved_text.id, "Human-approved for card rendering")

        image_contract = _pinned_contract("CARD_IMAGE_PNG", "IMAGE", "image/png", "STORAGE_URI", ["source_artifact_id"])
        context = ProductionExecutionContext(
            session=session,
            inputs={"knowledge_unit_id": unit_id, "source_artifact_id": saved_text.id},
            configuration={},
            run_id=run_id,
            resolved_context={"output_contract": image_contract},
            stage_configuration={
                "width": 640,
                "height": 800,
                "padding": 40,
                "font_size": 30,
                "line_spacing": 10,
                "max_lines": 20,
                "show_title": True,
                "show_source_attribution": True,
            },
        )
        image_artifact = await RenderApprovedTextCardCapability(
            storage_factory=lambda: storage
        ).execute(context)

        assert image_artifact.kind == ArtifactKind.IMAGE
        assert image_artifact.mime_type == "image/png"
        assert image_artifact.storage_uri in storage.objects
        assert image_artifact.metadata["source_artifact_id"] == str(saved_text.id)
        assert image_artifact.metadata["source_text_sha256"] == hashlib.sha256(approved_text.encode("utf-8")).hexdigest()
        assert image_artifact.metadata["source_attribution"] == "المصدر: كتاب الأمثلة — حفظ النص (ص. 11)"
        assert image_artifact.metadata["card_title"] == "النص المعتمد"

        persisted = (await session.execute(
            select(ArtifactModel).where(ArtifactModel.id == image_artifact.id)
        )).scalar_one()
        assert persisted.review_status == "DRAFT"
        assert persisted.artifact_metadata["source_artifact_id"] == str(saved_text.id)
        assert persisted.mime_type == "image/png"
