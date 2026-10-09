from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.control_plane import PromptTemplate, PromptTemplateVersion, ResolvedPrompt
from app.infrastructure.database.models import PromptTemplateModel, PromptTemplateVersionModel


def _template(row: PromptTemplateModel) -> PromptTemplate:
    return PromptTemplate(id=row.id, key=row.key, name=row.name, purpose=row.purpose, created_at=row.created_at, updated_at=row.updated_at)


def _version(row: PromptTemplateVersionModel) -> PromptTemplateVersion:
    return PromptTemplateVersion(id=row.id, prompt_template_id=row.prompt_template_id, version=row.version, body=row.body, status=row.status, created_at=row.created_at, updated_at=row.updated_at)


class PromptTemplateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_templates(self) -> list[PromptTemplate]:
        result = await self.session.execute(select(PromptTemplateModel).order_by(PromptTemplateModel.key.asc()))
        return [_template(row) for row in result.scalars().all()]

    async def get_template(self, key: str) -> PromptTemplateModel | None:
        result = await self.session.execute(select(PromptTemplateModel).where(PromptTemplateModel.key == key))
        return result.scalar_one_or_none()

    async def get_versions(self, key: str) -> list[PromptTemplateVersion]:
        result = await self.session.execute(
            select(PromptTemplateVersionModel)
            .join(PromptTemplateModel)
            .where(PromptTemplateModel.key == key)
            .order_by(PromptTemplateVersionModel.version.desc())
        )
        return [_version(row) for row in result.scalars().all()]

    async def create_template(self, key: str, name: str, purpose: str) -> PromptTemplate:
        row = PromptTemplateModel(id=uuid4(), key=key, name=name, purpose=purpose)
        self.session.add(row)
        await self.session.flush()
        return _template(row)

    async def create_version(self, template: PromptTemplateModel, body: str) -> PromptTemplateVersion:
        latest = (
            await self.session.execute(
                select(PromptTemplateVersionModel.version)
                .where(PromptTemplateVersionModel.prompt_template_id == template.id)
                .order_by(PromptTemplateVersionModel.version.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        row = PromptTemplateVersionModel(
            id=uuid4(),
            prompt_template_id=template.id,
            version=(latest or 0) + 1,
            body=body,
            status="DRAFT",
        )
        self.session.add(row)
        await self.session.flush()
        return _version(row)

    async def update_draft(self, key: str, version: int, body: str) -> PromptTemplateVersion:
        row = await self._get_version_row(key, version)
        if row is None:
            raise LookupError("Prompt version not found.")
        if row.status != "DRAFT":
            raise ValueError("Only DRAFT prompt versions can be edited.")
        row.body = body
        await self.session.flush()
        return _version(row)

    async def publish(self, key: str, version: int) -> PromptTemplateVersion:
        target = await self._get_version_row(key, version)
        if target is None:
            raise LookupError("Prompt version not found.")
        if target.status != "DRAFT":
            raise ValueError("Only DRAFT prompt versions can be published.")
        template = await self.get_template(key)
        if template is None:
            raise LookupError("Prompt template not found.")
        target_id = target.id
        template_id = target.prompt_template_id
        target_version = target.version
        target_body = target.body
        target_created_at = target.created_at
        target_updated_at = target.updated_at
        await self.session.execute(
            update(PromptTemplateVersionModel)
            .where(
                PromptTemplateVersionModel.prompt_template_id == template.id,
                PromptTemplateVersionModel.status == "PUBLISHED",
            )
            .values(status="ARCHIVED")
        )
        target.status = "PUBLISHED"
        await self.session.flush()
        return PromptTemplateVersion(
            id=target_id,
            prompt_template_id=template_id,
            version=target_version,
            body=target_body,
            status="PUBLISHED",
            created_at=target_created_at,
            updated_at=target_updated_at,
        )

    async def archive(self, key: str, version: int) -> PromptTemplateVersion:
        row = await self._get_version_row(key, version)
        if row is None:
            raise LookupError("Prompt version not found.")
        if row.status == "PUBLISHED":
            raise ValueError("The active PUBLISHED version cannot be archived directly.")
        row.status = "ARCHIVED"
        await self.session.flush()
        return _version(row)

    async def resolve_active(self, key: str) -> ResolvedPrompt:
        result = await self.session.execute(
            select(
                PromptTemplateModel.id.label("template_id"),
                PromptTemplateModel.key,
                PromptTemplateVersionModel.id.label("version_id"),
                PromptTemplateVersionModel.version,
                PromptTemplateVersionModel.body,
            )
            .join(
                PromptTemplateVersionModel,
                PromptTemplateVersionModel.prompt_template_id == PromptTemplateModel.id,
            )
            .where(
                PromptTemplateModel.key == key,
                PromptTemplateVersionModel.status == "PUBLISHED",
            )
        )
        rows = result.all()
        if len(rows) != 1:
            raise LookupError(f"No unique active published prompt exists for key '{key}'.")
        row = rows[0]
        return ResolvedPrompt(
            key=row.key,
            version=row.version,
            body=row.body,
            template_id=row.template_id,
            version_id=row.version_id,
        )

    async def _get_version_row(self, key: str, version: int) -> PromptTemplateVersionModel | None:
        result = await self.session.execute(
            select(PromptTemplateVersionModel)
            .join(PromptTemplateModel)
            .where(
                PromptTemplateModel.key == key,
                PromptTemplateVersionModel.version == version,
            )
        )
        return result.scalar_one_or_none()
