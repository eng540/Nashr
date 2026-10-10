from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.artifacts import Artifact, ArtifactKind, ArtifactStatus
from app.domain.posts import Post
from app.domain.output_contracts import OutputContractDefinition
from app.domain.policies import ProductionPolicyDefinition
from app.infrastructure.database.models import ArtifactModel, PostModel


def post_to_artifact(
    post: Post,
    *,
    production_job_id: UUID | None = None,
    resolved_context: dict | None = None,
) -> Artifact:
    """Expose a Post through the generic Artifact boundary without owning editorial state."""
    return Artifact(
        id=post.id,
        source_knowledge_unit_id=post.knowledge_unit_id,
        kind=ArtifactKind.POST,
        content=post.content,
        status=ArtifactStatus.AVAILABLE.value,
        created_at=post.created_at,
        updated_at=post.updated_at,
        post_id=post.id,
        editorial_status=post.status.value,
        production_job_id=production_job_id,
        resolved_context=resolved_context,
    )


async def ensure_post_artifact(
    session: AsyncSession,
    post: Post,
    *,
    production_job_id: UUID | None,
    resolved_context: dict | None,
) -> Artifact:
    """Validate against the pinned contract before persisting durable Artifact provenance."""
    contract_key = None
    contract_version = None
    contract_mime_type = None
    if resolved_context is not None and "output_contract" in resolved_context:
        from app.domain.production_context import PinnedOutputContract
        pinned = PinnedOutputContract.from_dict(resolved_context["output_contract"])
        definition = OutputContractDefinition.from_dict(pinned.definition)
        if definition.artifact_kind != ArtifactKind.POST.value:
            raise ValueError("Generated Artifact kind does not match the pinned output contract.")
        if definition.content_mode != "INLINE" or not post.content:
            raise ValueError("Generated Post content does not satisfy the pinned inline output contract.")
        if definition.max_content_chars is not None and len(post.content) > definition.max_content_chars:
            raise ValueError("Generated Post exceeds the pinned output contract content limit.")
        metadata = {}
        missing = [field for field in definition.required_metadata_fields if field not in metadata]
        if missing:
            raise ValueError("Generated Artifact is missing required metadata fields: " + ", ".join(missing))
        contract_key = pinned.key
        contract_version = pinned.version
        contract_mime_type = definition.mime_type
    if resolved_context is not None and "policy" in resolved_context:
        from app.domain.production_context import PinnedPolicy
        pinned_policy = PinnedPolicy.from_dict(resolved_context["policy"])
        policy = ProductionPolicyDefinition.from_dict(pinned_policy.definition)
        policy_errors = policy.validate_content(post.content)
        if policy_errors:
            raise ValueError("Generated Post violates pinned production policy: " + " ".join(policy_errors))
    existing = (
        await session.execute(select(ArtifactModel).where(ArtifactModel.id == post.id))
    ).scalar_one_or_none()
    if existing is None:
        await session.execute(
            insert(ArtifactModel)
            .values(
                id=post.id,
                source_knowledge_unit_id=post.knowledge_unit_id,
                kind=ArtifactKind.POST.value,
                status=ArtifactStatus.AVAILABLE.value,
                post_id=post.id,
                production_job_id=production_job_id,
                resolved_context=resolved_context,
                output_contract_key=contract_key,
                output_contract_version=contract_version,
                mime_type=contract_mime_type,
                content=post.content,
                created_at=post.created_at,
                updated_at=post.updated_at,
                artifact_metadata={},
            )
            .on_conflict_do_nothing(index_elements=[ArtifactModel.id])
        )
        await session.commit()
    artifact = await load_artifact(session, post.id)
    if artifact is None:
        raise RuntimeError("Artifact persistence did not produce a readable record.")
    return artifact


async def persist_generic_artifact(
    session: AsyncSession,
    artifact: Artifact,
    *,
    resolved_context: dict,
) -> Artifact:
    """Validate and persist a non-Post Artifact against its pinned output contract."""
    if artifact.kind == ArtifactKind.POST:
        raise ValueError("POST artifacts must use ensure_post_artifact so editorial state remains canonical.")
    try:
        kind = ArtifactKind(artifact.kind)
        status = ArtifactStatus(artifact.status)
    except ValueError as exc:
        raise ValueError("Generic Artifact kind or status is unsupported.") from exc

    from app.domain.production_context import PinnedOutputContract
    if not isinstance(resolved_context, dict) or "output_contract" not in resolved_context:
        raise ValueError("Generic Artifact persistence requires a pinned output contract.")
    pinned_contract = PinnedOutputContract.from_dict(resolved_context["output_contract"])
    definition = OutputContractDefinition.from_dict(pinned_contract.definition)
    if definition.artifact_kind != kind.value:
        raise ValueError("Generated Artifact kind does not match the pinned output contract.")
    if artifact.mime_type is not None and artifact.mime_type != definition.mime_type:
        raise ValueError("Generated Artifact MIME type does not match the pinned output contract.")
    metadata = dict(artifact.metadata or {})
    missing = [field for field in definition.required_metadata_fields if field not in metadata]
    if missing:
        raise ValueError("Generated Artifact is missing required metadata fields: " + ", ".join(missing))
    if definition.content_mode == "INLINE":
        if not isinstance(artifact.content, str) or not artifact.content.strip() or artifact.storage_uri is not None:
            raise ValueError("Inline Artifact requires non-empty content and no storage URI.")
        if definition.max_content_chars is not None and len(artifact.content) > definition.max_content_chars:
            raise ValueError("Generated Artifact exceeds the pinned output contract content limit.")
    else:
        if artifact.content is not None or not isinstance(artifact.storage_uri, str) or not artifact.storage_uri.strip():
            raise ValueError("Storage-backed Artifact requires a storage URI and no inline content.")
        if len(artifact.storage_uri) > 2000:
            raise ValueError("Artifact storage URI exceeds the supported length.")
    if "policy" in resolved_context and artifact.content is not None:
        from app.domain.production_context import PinnedPolicy
        pinned_policy = PinnedPolicy.from_dict(resolved_context["policy"])
        policy = ProductionPolicyDefinition.from_dict(pinned_policy.definition)
        policy_errors = policy.validate_content(artifact.content)
        if policy_errors:
            raise ValueError("Generated Artifact violates pinned production policy: " + " ".join(policy_errors))

    if artifact.production_job_id is not None:
        existing = (
            await session.execute(
                select(ArtifactModel).where(
                    ArtifactModel.production_job_id == artifact.production_job_id,
                    ArtifactModel.source_knowledge_unit_id == artifact.source_knowledge_unit_id,
                    ArtifactModel.kind == kind.value,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            loaded = await load_artifact(session, existing.id)
            if loaded is not None:
                return loaded

    await session.execute(
        insert(ArtifactModel)
        .values(
            id=artifact.id,
            source_knowledge_unit_id=artifact.source_knowledge_unit_id,
            kind=kind.value,
            status=status.value,
            post_id=None,
            production_job_id=artifact.production_job_id,
            resolved_context=resolved_context,
            output_contract_key=pinned_contract.key,
            output_contract_version=pinned_contract.version,
            mime_type=definition.mime_type,
            content=artifact.content,
            storage_uri=artifact.storage_uri,
            artifact_metadata=metadata,
            created_at=artifact.created_at,
            updated_at=artifact.updated_at,
        )
        .on_conflict_do_nothing(
            index_elements=[
                ArtifactModel.production_job_id,
                ArtifactModel.source_knowledge_unit_id,
                ArtifactModel.kind,
            ],
            index_where=ArtifactModel.production_job_id.is_not(None),
        )
    )
    await session.commit()
    loaded = await load_artifact(session, artifact.id)
    if loaded is None and artifact.production_job_id is not None:
        existing = (
            await session.execute(
                select(ArtifactModel).where(
                    ArtifactModel.production_job_id == artifact.production_job_id,
                    ArtifactModel.source_knowledge_unit_id == artifact.source_knowledge_unit_id,
                    ArtifactModel.kind == kind.value,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            loaded = await load_artifact(session, existing.id)
    if loaded is None:
        raise RuntimeError("Generic Artifact persistence did not produce a readable record.")
    return loaded


async def persist_generic_artifact(session: AsyncSession, artifact: Artifact, *, resolved_context: dict) -> Artifact:
    """Persist a non-Post Artifact after enforcing its pinned output contract."""
    if artifact.kind == ArtifactKind.POST:
        raise ValueError("POST artifacts must use ensure_post_artifact.")
    kind = ArtifactKind(artifact.kind)
    status = ArtifactStatus(artifact.status)
    from app.domain.production_context import PinnedOutputContract
    if not isinstance(resolved_context, dict) or "output_contract" not in resolved_context:
        raise ValueError("Generic Artifact persistence requires a pinned output contract.")
    pinned = PinnedOutputContract.from_dict(resolved_context["output_contract"])
    definition = OutputContractDefinition.from_dict(pinned.definition)
    if definition.artifact_kind != kind.value:
        raise ValueError("Generated Artifact kind does not match the pinned output contract.")
    if artifact.mime_type is not None and artifact.mime_type != definition.mime_type:
        raise ValueError("Generated Artifact MIME type does not match the pinned output contract.")
    metadata = dict(artifact.metadata or {})
    missing = [field for field in definition.required_metadata_fields if field not in metadata]
    if missing:
        raise ValueError("Generated Artifact is missing required metadata fields: " + ", ".join(missing))
    if definition.content_mode == "INLINE":
        if not isinstance(artifact.content, str) or not artifact.content.strip() or artifact.storage_uri is not None:
            raise ValueError("Inline Artifact requires non-empty content and no storage URI.")
        if definition.max_content_chars is not None and len(artifact.content) > definition.max_content_chars:
            raise ValueError("Generated Artifact exceeds the pinned output contract content limit.")
    else:
        if artifact.content is not None or not isinstance(artifact.storage_uri, str) or not artifact.storage_uri.strip():
            raise ValueError("Storage-backed Artifact requires a storage URI and no inline content.")
        if len(artifact.storage_uri) > 2000:
            raise ValueError("Artifact storage URI exceeds the supported length.")
    if "policy" in resolved_context and artifact.content is not None:
        from app.domain.production_context import PinnedPolicy
        policy = ProductionPolicyDefinition.from_dict(PinnedPolicy.from_dict(resolved_context["policy"]).definition)
        errors = policy.validate_content(artifact.content)
        if errors:
            raise ValueError("Generated Artifact violates pinned production policy: " + " ".join(errors))

    if artifact.production_job_id is not None:
        row = (await session.execute(select(ArtifactModel).where(
            ArtifactModel.production_job_id == artifact.production_job_id,
            ArtifactModel.source_knowledge_unit_id == artifact.source_knowledge_unit_id,
            ArtifactModel.kind == kind.value,
        ))).scalar_one_or_none()
        if row is not None:
            existing = await load_artifact(session, row.id)
            if existing is not None:
                return existing

    await session.execute(
        insert(ArtifactModel).values(
            id=artifact.id,
            source_knowledge_unit_id=artifact.source_knowledge_unit_id,
            kind=kind.value,
            status=status.value,
            post_id=None,
            production_job_id=artifact.production_job_id,
            resolved_context=resolved_context,
            output_contract_key=pinned.key,
            output_contract_version=pinned.version,
            mime_type=definition.mime_type,
            content=artifact.content,
            storage_uri=artifact.storage_uri,
            artifact_metadata=metadata,
            created_at=artifact.created_at,
            updated_at=artifact.updated_at,
        ).on_conflict_do_nothing(
            index_elements=[ArtifactModel.production_job_id, ArtifactModel.source_knowledge_unit_id, ArtifactModel.kind],
            index_where=ArtifactModel.production_job_id.is_not(None),
        )
    )
    await session.commit()
    existing = await load_artifact(session, artifact.id)
    if existing is None and artifact.production_job_id is not None:
        row = (await session.execute(select(ArtifactModel).where(
            ArtifactModel.production_job_id == artifact.production_job_id,
            ArtifactModel.source_knowledge_unit_id == artifact.source_knowledge_unit_id,
            ArtifactModel.kind == kind.value,
        ))).scalar_one_or_none()
        if row is not None:
            existing = await load_artifact(session, row.id)
    if existing is None:
        raise RuntimeError("Generic Artifact persistence did not produce a readable record.")
    return existing


async def load_artifact(session: AsyncSession, artifact_id: UUID) -> Artifact | None:
    result = await session.execute(
        select(ArtifactModel).where(ArtifactModel.id == artifact_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None

    post: PostModel | None = None
    if row.kind == ArtifactKind.POST.value and row.post_id is not None:
        post = (
            await session.execute(select(PostModel).where(PostModel.id == row.post_id))
        ).scalar_one_or_none()

    return Artifact(
        id=row.id,
        source_knowledge_unit_id=row.source_knowledge_unit_id,
        kind=ArtifactKind(row.kind),
        content=post.content if post is not None else row.content,
        status=row.status,
        created_at=post.created_at if post is not None else row.created_at,
        updated_at=post.updated_at if post is not None else row.updated_at,
        storage_uri=row.storage_uri,
        mime_type=row.mime_type,
        post_id=row.post_id,
        editorial_status=post.status if post is not None else None,
        production_job_id=row.production_job_id,
        output_contract_key=row.output_contract_key,
        output_contract_version=row.output_contract_version,
        resolved_context=row.resolved_context,
        metadata=row.artifact_metadata,
    )


async def load_post_model_to_artifact(session: AsyncSession, post_id: UUID) -> Artifact:
    """Compatibility helper: expose a persisted Post row through the Artifact boundary."""
    result = await session.execute(select(PostModel).where(PostModel.id == post_id))
    post = result.scalar_one_or_none()
    if post is None:
        raise ValueError("Post not found for Artifact conversion.")
    return post_model_to_artifact(post)


def post_model_to_artifact(post: PostModel) -> Artifact:
    """Expose a persisted Post while keeping its editorial state distinct from Artifact state."""
    return Artifact(
        id=post.id,
        source_knowledge_unit_id=post.knowledge_unit_id,
        kind=ArtifactKind.POST,
        content=post.content,
        status=ArtifactStatus.AVAILABLE.value,
        created_at=post.created_at,
        updated_at=post.updated_at,
        post_id=post.id,
        editorial_status=post.status,
    )
