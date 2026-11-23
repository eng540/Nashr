"""Create reviewable text and native quiz drafts without generation or sends."""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.artifacts import persist_generic_artifact
from app.application.media_bank import _media_bank_contract
from app.domain.artifacts import Artifact, ArtifactKind
from app.domain.quizzes import QuizPayload
from app.infrastructure.database.models import SourceModel, KnowledgeUnitModel


async def create_manual_artifact(session: AsyncSession, *, kind: str, title: str, content: str, quiz: dict | None = None, native: dict | None = None, album_metadata: dict | None = None):
    if kind not in {"TEXT", "QUIZ"}:
        raise ValueError("Only TEXT or QUIZ drafts can be created here.")
    if not title.strip() or len(title) > 500 or not content.strip() or len(content) > 100000:
        raise ValueError("A title and non-empty content are required within their limits.")
    metadata = {"source_type": "MANUAL_DRAFT", "title": title.strip()}
    if kind == "QUIZ":
        parsed = QuizPayload.from_dict(quiz)
        if content != parsed.question:
            raise ValueError("Quiz content must match its question.")
        metadata["quiz"] = quiz
    if native is not None:
        if kind != "TEXT":
            raise ValueError("Native content must use TEXT wrapper.")
        from app.domain.telegram_payloads import native_payload
        native_payload(native)
        metadata["telegram_native"] = native
    if album_metadata is not None:
        if kind != "TEXT" or native is not None:
            raise ValueError("Albums require a dedicated TEXT wrapper.")
        metadata.update(album_metadata)
    source_id, unit_id, artifact_id = uuid4(), uuid4(), uuid4()
    session.add(SourceModel(id=source_id, filename=title[:500], mime_type="text/plain", storage_path="manual-draft", size_bytes=len(content.encode()), status="STORED"))
    session.add(KnowledgeUnitModel(id=unit_id, source_id=source_id, position=1, title=title[:500], kind="MANUAL_DRAFT", content=content, original_text=content))
    mime = "text/plain" if kind == "TEXT" else "application/json"
    context = _media_bank_contract(kind, mime)
    context["output_contract"]["key"] = "MANUAL_DRAFT"
    context["output_contract"]["definition"]["content_mode"] = "INLINE"
    now = datetime.now(timezone.utc)
    artifact = Artifact(id=artifact_id, source_knowledge_unit_id=unit_id, kind=ArtifactKind(kind), content=content, status="AVAILABLE", created_at=now, updated_at=now, mime_type=mime, metadata=metadata)
    saved = await persist_generic_artifact(session, artifact, resolved_context=context)
    await session.commit()
    return saved
