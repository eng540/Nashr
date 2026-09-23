from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.domain.sources import Source


class Base(DeclarativeBase):
    """Provide the SQLAlchemy declarative base."""


class SourceModel(Base):
    """Persist a source file and its storage metadata."""
    __tablename__ = "sources"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="STORED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    knowledge_units: Mapped[list["KnowledgeUnitModel"]] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
    )

    def to_domain(self) -> Source:
        """Convert the persistence model into the domain source."""
        from app.domain.sources import SourceStatus
        return Source(
            id=self.id,
            filename=self.filename,
            mime_type=self.mime_type,
            storage_path=self.storage_path,
            size_bytes=self.size_bytes,
            status=SourceStatus(self.status),
            created_at=self.created_at,
        )


class KnowledgeUnitModel(Base):
    """Persist one extracted knowledge unit."""
    __tablename__ = "knowledge_units"
    __table_args__ = (UniqueConstraint("source_id", "position", name="uq_knowledge_units_source_position"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    source: Mapped[SourceModel] = relationship(back_populates="knowledge_units")
