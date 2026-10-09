from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class PromptTemplate:
    id: UUID
    key: str
    name: str
    purpose: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class PromptTemplateVersion:
    id: UUID
    prompt_template_id: UUID
    version: int
    body: str
    status: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ResolvedPrompt:
    key: str
    version: int
    body: str
    template_id: UUID | None = None
    version_id: UUID | None = None
