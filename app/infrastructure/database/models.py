from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    knowledge_units: Mapped[list["KnowledgeUnitModel"]] = relationship(back_populates="source", cascade="all, delete-orphan")
    topics: Mapped[list["TopicModel"]] = relationship(back_populates="source", cascade="all, delete-orphan")
    discovery_jobs: Mapped[list["DiscoveryJobModel"]] = relationship(back_populates="source", cascade="all, delete-orphan")

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
    discovery_status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING")
    discovery_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[SourceModel] = relationship(back_populates="topics")
    knowledge_units: Mapped[list["KnowledgeUnitModel"]] = relationship(back_populates="topic")


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    source: Mapped[SourceModel] = relationship(back_populates="knowledge_units")
    topic: Mapped[TopicModel | None] = relationship(back_populates="knowledge_units")
    publications: Mapped[list["PublicationModel"]] = relationship(back_populates="knowledge_unit", cascade="save-update, merge")


class PublicationModel(Base):
    __tablename__ = "publications"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    knowledge_unit_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("knowledge_units.id", ondelete="RESTRICT"), nullable=False)
    platform: Mapped[str] = mapped_column(String(50), nullable=False, default="telegram")
    destination: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="DRAFT")
    external_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    knowledge_unit: Mapped[KnowledgeUnitModel] = relationship(back_populates="publications")


class DiscoveryJobModel(Base):
    __tablename__ = "discovery_jobs"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    stage: Mapped[str] = mapped_column(String(50), nullable=False)
    topics_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    topics_completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    materials_discovered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_topic_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("topics.id", ondelete="SET NULL"), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retryable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[SourceModel] = relationship(back_populates="discovery_jobs")
