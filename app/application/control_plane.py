from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.control_plane import PromptTemplate
from app.domain.production_context import PinnedIdentity, PinnedOutputContract
from app.domain.identities import EditorialIdentityDefinition
from app.infrastructure.database.identities import EditorialIdentityRepository
from app.infrastructure.database.control_plane import PromptTemplateRepository
from app.infrastructure.database.recipes import ProductionRecipeRepository
from app.infrastructure.database.output_contracts import OutputContractRepository
from app.domain.output_contracts import OutputContractDefinition


EDITORIAL_PROMPT_KEY = "editorial.drafter"


class ControlPlaneResolver:
    async def resolve_prompt(self, session: AsyncSession, key: str):
        return await PromptTemplateRepository(session).resolve_active(key)

    async def resolve_recipe(self, session: AsyncSession, key: str):
        return await ProductionRecipeRepository(session).resolve_active(key)

    async def resolve_output_contract(self, session: AsyncSession, key: str) -> PinnedOutputContract:
        contract, version = await OutputContractRepository(session).resolve_active(key)
        return PinnedOutputContract(
            contract_id=str(contract.id),
            version_id=str(version.id),
            key=contract.key,
            version=version.version,
            definition=OutputContractDefinition.from_dict(version.definition).to_dict(),
        )

    async def resolve_identity(self, session: AsyncSession, key: str) -> PinnedIdentity:
        identity, version = await EditorialIdentityRepository(session).resolve_active(key)
        return PinnedIdentity(
            identity_id=str(identity.id),
            version_id=str(version.id),
            key=identity.key,
            version=version.version,
            definition=EditorialIdentityDefinition.from_dict(version.definition).to_dict(),
        )


class PromptTemplateService:
    def __init__(self, session: AsyncSession) -> None:
        self.repository = PromptTemplateRepository(session)

    async def list_templates(self):
        return await self.repository.list_templates()

    async def get_template(self, key: str):
        row = await self.repository.get_template(key)
        if row is None:
            raise LookupError("Prompt template not found.")
        template = PromptTemplate(
            id=row.id,
            key=row.key,
            name=row.name,
            purpose=row.purpose,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        return template, await self.repository.get_versions(key)

    async def create_template(self, key: str, name: str, purpose: str, body: str):
        if not body.strip():
            raise ValueError("Prompt body cannot be empty.")
        if await self.repository.get_template(key):
            raise ValueError("Prompt template key already exists.")
        template = await self.repository.create_template(key.strip(), name.strip(), purpose.strip())
        model = await self.repository.get_template(key.strip())
        version = await self.repository.create_version(model, body)
        await self.repository.session.commit()
        return template, version

    async def create_draft(self, key: str, body: str):
        if not body.strip():
            raise ValueError("Prompt body cannot be empty.")
        template = await self.repository.get_template(key)
        if template is None:
            raise LookupError("Prompt template not found.")
        result = await self.repository.create_version(template, body)
        await self.repository.session.commit()
        return result

    async def update_draft(self, key: str, version: int, body: str):
        if not body.strip():
            raise ValueError("Prompt body cannot be empty.")
        result = await self.repository.update_draft(key, version, body)
        await self.repository.session.commit()
        return result

    async def publish(self, key: str, version: int):
        result = await self.repository.publish(key, version)
        await self.repository.session.commit()
        return result

    async def archive(self, key: str, version: int):
        result = await self.repository.archive(key, version)
        await self.repository.session.commit()
        return result
