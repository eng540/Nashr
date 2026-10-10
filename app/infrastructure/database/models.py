from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, LargeBinary, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.domain.sources import Source


class Base(DeclarativeBase):
    pass


class SourceModel(Base):
    __tablename__ = "sources"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="STORED")
    book_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    book_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    gemini_file_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    gemini_file_uri: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    gemini_file_mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    gemini_file_source_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # file_payload is loaded by default for safety. Read-only list
    # views that never need the binary payload should apply
    # .options(defer(SourceModel.file_payload)) explicitly.
    file_payload: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    knowledge_units: Mapped[list["KnowledgeUnitModel"]] = relationship(back_populates="source", cascade="all, delete-orphan")
    topics: Mapped[list["TopicModel"]] = relationship(back_populates="source", cascade="all, delete-orphan")
    discovery_jobs: Mapped[list["DiscoveryJobModel"]] = relationship(back_populates="source", cascade="all, delete-orphan")
    book_map_sections: Mapped[list["BookMapSectionModel"]] = relationship(back_populates="source", cascade="all, delete-orphan")
    production_jobs: Mapped[list["ProductionJobModel"]] = relationship(back_populates="source", cascade="all, delete-orphan")

    def ensure_file_on_disk(self) -> Path:
        """Guarantee that the source PDF exists on ephemeral local storage."""
        path = Path(self.storage_path)
        if not path.is_file():
            if self.file_payload is None:
                raise FileNotFoundError(
                    f"Source file is missing from disk and has no database backup: {self.storage_path}"
                )
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(self.file_payload)
        return path

    def to_domain(self) -> Source:
        from app.domain.sources import SourceStatus
        return Source(
            id=self.id,
            filename=self.filename,
            mime_type=self.mime_type,
            storage_path=self.storage_path,
            size_bytes=self.size_bytes,
            status=SourceStatus(self.status),
            created_at=self.created_at,
            content_sha256=self.content_sha256,
            gemini_file_name=self.gemini_file_name,
            gemini_file_uri=self.gemini_file_uri,
            gemini_file_mime_type=self.gemini_file_mime_type,
            gemini_file_source_sha256=self.gemini_file_source_sha256,
        )


class TopicModel(Base):
    __tablename__ = "topics"
    __table_args__ = (UniqueConstraint("source_id", "position", name="uq_topics_source_position"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    source_reference: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    discovery_status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING")
    discovery_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[SourceModel] = relationship(back_populates="topics")
    knowledge_units: Mapped[list["KnowledgeUnitModel"]] = relationship(back_populates="topic")
    chunks: Mapped[list["DiscoveryChunkModel"]] = relationship(back_populates="topic", cascade="all, delete-orphan")


class KnowledgeUnitModel(Base):
    __tablename__ = "knowledge_units"
    __table_args__ = (UniqueConstraint("source_id", "position", name="uq_knowledge_units_source_position"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    topic_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("topics.id", ondelete="SET NULL"), nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    kind: Mapped[str | None] = mapped_column(String(200), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    original_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    discovery_page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    discovery_page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    discovery_chunk_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    source: Mapped[SourceModel] = relationship(back_populates="knowledge_units")
    topic: Mapped[TopicModel | None] = relationship(back_populates="knowledge_units")
    posts: Mapped[list["PostModel"]] = relationship(back_populates="knowledge_unit", cascade="all, delete-orphan")
    publications: Mapped[list["PublicationModel"]] = relationship(back_populates="knowledge_unit", cascade="save-update, merge")


class PostModel(Base):
    __tablename__ = "posts"
    __table_args__ = (UniqueConstraint("knowledge_unit_id", name="uq_posts_knowledge_unit"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    knowledge_unit_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("knowledge_units.id", ondelete="RESTRICT"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="DRAFT")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    knowledge_unit: Mapped[KnowledgeUnitModel] = relationship(back_populates="posts")
    publications: Mapped[list["PublicationModel"]] = relationship(back_populates="post", cascade="save-update, merge")


class ProductionJobModel(Base):
    __tablename__ = "production_jobs"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    scope: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="QUEUED")
    total_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_item_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    editorial_prompt_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    editorial_prompt_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    editorial_prompt_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_context: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    source: Mapped[SourceModel] = relationship(back_populates="production_jobs")
    items: Mapped[list["ProductionJobItemModel"]] = relationship(back_populates="job", cascade="all, delete-orphan")


class ProductionJobItemModel(Base):
    __tablename__ = "production_job_items"
    __table_args__ = (
        UniqueConstraint("job_id", "knowledge_unit_id", name="uq_production_job_items_job_knowledge_unit"),
        UniqueConstraint("job_id", "position", name="uq_production_job_items_job_position"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("production_jobs.id", ondelete="CASCADE"), nullable=False)
    knowledge_unit_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("knowledge_units.id", ondelete="RESTRICT"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    post_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("posts.id", ondelete="RESTRICT"), nullable=True)
    artifact_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("artifacts.id", ondelete="RESTRICT"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    job: Mapped[ProductionJobModel] = relationship(back_populates="items")
    knowledge_unit: Mapped[KnowledgeUnitModel] = relationship()
    post: Mapped[PostModel | None] = relationship()


class ArtifactModel(Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        UniqueConstraint("post_id", name="uq_artifacts_post_id"),
        CheckConstraint(
            "kind IN ('POST', 'TEXT', 'IMAGE', 'VIDEO', 'AUDIO')",
            name="ck_artifacts_kind",
        ),
        CheckConstraint(
            "status IN ('AVAILABLE', 'FAILED', 'ARCHIVED')",
            name="ck_artifacts_status",
        ),
        CheckConstraint(
            "kind <> 'POST' OR post_id IS NOT NULL",
            name="ck_artifacts_post_reference",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    source_knowledge_unit_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("knowledge_units.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="AVAILABLE")
    post_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("posts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage_uri: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(200), nullable=True)
    output_contract_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    output_contract_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    production_job_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("production_jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    resolved_context: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    artifact_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class PublicationModel(Base):
    __tablename__ = "publications"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    knowledge_unit_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("knowledge_units.id", ondelete="RESTRICT"), nullable=False)
    post_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("posts.id", ondelete="SET NULL"), nullable=True)
    platform: Mapped[str] = mapped_column(String(50), nullable=False, default="telegram")
    destination: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="DRAFT")
    external_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    knowledge_unit: Mapped[KnowledgeUnitModel] = relationship(back_populates="publications")
    post: Mapped[PostModel | None] = relationship(back_populates="publications")


class ScheduleModel(Base):
    __tablename__ = "schedules"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="DRAFT")
    timezone: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    items: Mapped[list["ScheduleItemModel"]] = relationship(back_populates="schedule", cascade="all, delete-orphan")


class ScheduleItemModel(Base):
    __tablename__ = "schedule_items"
    __table_args__ = (
        UniqueConstraint("schedule_id", "position", name="uq_schedule_items_schedule_position"),
        UniqueConstraint("schedule_id", "post_id", name="uq_schedule_items_schedule_post"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    schedule_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("schedules.id", ondelete="CASCADE"), nullable=False)
    post_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("posts.id", ondelete="RESTRICT"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING")
    publication_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("publications.id", ondelete="SET NULL"), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    schedule: Mapped["ScheduleModel"] = relationship(back_populates="items")
    post: Mapped[PostModel] = relationship()
    publication: Mapped["PublicationModel | None"] = relationship()


class BookMapSectionModel(Base):
    __tablename__ = "book_map_sections"
    __table_args__ = (UniqueConstraint("source_id", "section_index", name="uq_book_map_sections_source_index"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    section_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_start: Mapped[int] = mapped_column(Integer, nullable=False)
    page_end: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING")
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    source: Mapped[SourceModel] = relationship(back_populates="book_map_sections")


class DiscoveryChunkModel(Base):
    __tablename__ = "discovery_chunks"
    __table_args__ = (UniqueConstraint("topic_id", "chunk_index", name="uq_discovery_chunks_topic_index"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    topic_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_start: Mapped[int] = mapped_column(Integer, nullable=False)
    page_end: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING")
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    topic: Mapped[TopicModel] = relationship(back_populates="chunks")


class DiscoveryJobModel(Base):
    __tablename__ = "discovery_jobs"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    stage: Mapped[str] = mapped_column(String(50), nullable=False)
    topics_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    topics_completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunks_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunks_completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    materials_discovered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_topic_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("topics.id", ondelete="SET NULL"), nullable=True)
    current_chunk_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("discovery_chunks.id", ondelete="SET NULL"), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retryable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[SourceModel] = relationship(back_populates="discovery_jobs")
class PromptTemplateModel(Base):
    __tablename__ = "prompt_templates"
    __table_args__ = (UniqueConstraint("key", name="uq_prompt_templates_key"),)
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    key: Mapped[str] = mapped_column(String(200), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    versions: Mapped[list["PromptTemplateVersionModel"]] = relationship(back_populates="template", cascade="all, delete-orphan", order_by="PromptTemplateVersionModel.version")


class PromptTemplateVersionModel(Base):
    __tablename__ = "prompt_template_versions"
    __table_args__ = (UniqueConstraint("prompt_template_id", "version", name="uq_prompt_template_versions_template_version"),)
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    prompt_template_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("prompt_templates.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="DRAFT")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    template: Mapped[PromptTemplateModel] = relationship(back_populates="versions")

class ProductionRecipeModel(Base):
    __tablename__ = "production_recipes"
    __table_args__ = (UniqueConstraint("key", name="uq_production_recipes_key"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    key: Mapped[str] = mapped_column(String(200), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class ProductionRecipeVersionModel(Base):
    __tablename__ = "production_recipe_versions"
    __table_args__ = (
        UniqueConstraint("recipe_id", "version", name="uq_production_recipe_versions_recipe_version"),
        CheckConstraint("version > 0", name="ck_production_recipe_versions_positive_version"),
        CheckConstraint("status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')", name="ck_production_recipe_versions_status"),
        Index(
            "uq_production_recipe_versions_published",
            "recipe_id",
            unique=True,
            postgresql_where=text("status = 'PUBLISHED'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    recipe_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("production_recipes.id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="DRAFT")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class EditorialIdentityModel(Base):
    __tablename__ = "editorial_identities"
    __table_args__ = (UniqueConstraint("key", name="uq_editorial_identities_key"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    key: Mapped[str] = mapped_column(String(200), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class EditorialIdentityVersionModel(Base):
    __tablename__ = "editorial_identity_versions"
    __table_args__ = (
        UniqueConstraint("identity_id", "version", name="uq_editorial_identity_versions_identity_version"),
        CheckConstraint("version > 0", name="ck_editorial_identity_versions_positive_version"),
        CheckConstraint("status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')", name="ck_editorial_identity_versions_status"),
        Index(
            "uq_editorial_identity_versions_published",
            "identity_id",
            unique=True,
            postgresql_where=text("status = 'PUBLISHED'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    identity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("editorial_identities.id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="DRAFT")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class ProductionPolicyModel(Base):
    __tablename__ = "production_policies"
    __table_args__ = (UniqueConstraint("key", name="uq_production_policies_key"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    key: Mapped[str] = mapped_column(String(200), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class ProductionPolicyVersionModel(Base):
    __tablename__ = "production_policy_versions"
    __table_args__ = (
        UniqueConstraint("policy_id", "version", name="uq_production_policy_versions_policy_version"),
        CheckConstraint("version > 0", name="ck_production_policy_versions_positive_version"),
        CheckConstraint("status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')", name="ck_production_policy_versions_status"),
        Index("uq_production_policy_versions_published", "policy_id", unique=True, postgresql_where=text("status = 'PUBLISHED'")),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    policy_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("production_policies.id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="DRAFT")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class ProductionProductModel(Base):
    __tablename__ = "production_products"
    __table_args__ = (UniqueConstraint("key", name="uq_production_products_key"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    key: Mapped[str] = mapped_column(String(200), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class ProductionProductVersionModel(Base):
    __tablename__ = "production_product_versions"
    __table_args__ = (
        UniqueConstraint("product_id", "version", name="uq_production_product_versions_product_version"),
        CheckConstraint("version > 0", name="ck_production_product_versions_positive_version"),
        CheckConstraint("status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')", name="ck_production_product_versions_status"),
        Index("uq_production_product_versions_published", "product_id", unique=True, postgresql_where=text("status = 'PUBLISHED'")),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    product_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("production_products.id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="DRAFT")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class OutputContractModel(Base):
    __tablename__ = "output_contracts"
    __table_args__ = (UniqueConstraint("key", name="uq_output_contracts_key"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    key: Mapped[str] = mapped_column(String(200), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class OutputContractVersionModel(Base):
    __tablename__ = "output_contract_versions"
    __table_args__ = (
        UniqueConstraint("contract_id", "version", name="uq_output_contract_versions_contract_version"),
        CheckConstraint("version > 0", name="ck_output_contract_versions_positive_version"),
        CheckConstraint("status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')", name="ck_output_contract_versions_status"),
        Index(
            "uq_output_contract_versions_published",
            "contract_id",
            unique=True,
            postgresql_where=text("status = 'PUBLISHED'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    contract_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("output_contracts.id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="DRAFT")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
