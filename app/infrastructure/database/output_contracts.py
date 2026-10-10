from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.output_contracts import OutputContractDefinition
from app.infrastructure.database.models import OutputContractModel, OutputContractVersionModel


class OutputContractRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_contracts(self) -> list[OutputContractModel]:
        result = await self.session.execute(select(OutputContractModel).order_by(OutputContractModel.key.asc()))
        return list(result.scalars().all())

    async def get_contract(self, key: str, *, for_update: bool = False) -> OutputContractModel | None:
        statement = select(OutputContractModel).where(OutputContractModel.key == key)
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_versions(self, key: str) -> list[OutputContractVersionModel]:
        result = await self.session.execute(
            select(OutputContractVersionModel)
            .join(OutputContractModel)
            .where(OutputContractModel.key == key)
            .order_by(OutputContractVersionModel.version.desc())
        )
        return list(result.scalars().all())

    async def create_contract(self, key: str, name: str, purpose: str, definition: dict[str, object]):
        contract = OutputContractModel(id=uuid4(), key=key, name=name, purpose=purpose)
        self.session.add(contract)
        await self.session.flush()
        version = OutputContractVersionModel(
            id=uuid4(), contract_id=contract.id, version=1,
            definition=definition, status="DRAFT",
        )
        self.session.add(version)
        await self.session.flush()
        return contract, version

    async def create_draft(self, key: str, definition: dict[str, object]) -> OutputContractVersionModel:
        contract = await self.get_contract(key, for_update=True)
        if contract is None:
            raise LookupError("Output contract not found.")
        latest = (
            await self.session.execute(
                select(func.max(OutputContractVersionModel.version)).where(
                    OutputContractVersionModel.contract_id == contract.id
                )
            )
        ).scalar_one()
        row = OutputContractVersionModel(
            id=uuid4(), contract_id=contract.id, version=(latest or 0) + 1,
            definition=definition, status="DRAFT",
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def update_draft(self, key: str, version: int, definition: dict[str, object]) -> OutputContractVersionModel:
        contract = await self.get_contract(key, for_update=True)
        if contract is None:
            raise LookupError("Output contract not found.")
        row = await self._get_version_row(key, version)
        if row is None:
            raise LookupError("Output contract version not found.")
        if row.status != "DRAFT":
            raise ValueError("Only DRAFT output contract versions can be edited.")
        row.definition = definition
        await self.session.flush()
        return row

    async def publish(self, key: str, version: int) -> OutputContractVersionModel:
        contract = await self.get_contract(key, for_update=True)
        if contract is None:
            raise LookupError("Output contract not found.")
        target = await self._get_version_row(key, version)
        if target is None:
            raise LookupError("Output contract version not found.")
        if target.status != "DRAFT":
            raise ValueError("Only DRAFT output contract versions can be published.")
        await self.session.execute(
            update(OutputContractVersionModel)
            .where(
                OutputContractVersionModel.contract_id == contract.id,
                OutputContractVersionModel.status == "PUBLISHED",
            )
            .values(status="ARCHIVED")
        )
        target.status = "PUBLISHED"
        await self.session.flush()
        return target

    async def archive(self, key: str, version: int) -> OutputContractVersionModel:
        contract = await self.get_contract(key, for_update=True)
        if contract is None:
            raise LookupError("Output contract not found.")
        row = await self._get_version_row(key, version)
        if row is None:
            raise LookupError("Output contract version not found.")
        if row.status == "PUBLISHED":
            raise ValueError("The active PUBLISHED output contract cannot be archived directly.")
        if row.status == "ARCHIVED":
            return row
        row.status = "ARCHIVED"
        await self.session.flush()
        return row

    async def resolve_active(self, key: str) -> tuple[OutputContractModel, OutputContractVersionModel]:
        result = await self.session.execute(
            select(OutputContractModel, OutputContractVersionModel)
            .join(OutputContractVersionModel, OutputContractVersionModel.contract_id == OutputContractModel.id)
            .where(OutputContractModel.key == key, OutputContractVersionModel.status == "PUBLISHED")
        )
        row = result.one_or_none()
        if row is None:
            raise LookupError(f"No active published output contract exists for key '{key}'.")
        OutputContractDefinition.from_dict(row[1].definition)
        return row[0], row[1]

    async def _get_version_row(self, key: str, version: int) -> OutputContractVersionModel | None:
        result = await self.session.execute(
            select(OutputContractVersionModel)
            .join(OutputContractModel)
            .where(OutputContractModel.key == key, OutputContractVersionModel.version == version)
        )
        return result.scalar_one_or_none()
