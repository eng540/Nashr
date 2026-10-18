import hashlib
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.adapters.drafting.gemini import GeminiEditorialDrafter
from app.application.control_plane import ControlPlaneResolver, EDITORIAL_PROMPT_KEY
from app.application.identity_context import compose_editorial_prompt
from app.domain.production_jobs import (
    ProductionJobItemStatus,
    ProductionJobStatus,
    ProductionScope,
)
from app.domain.production_context import ResolvedProductionContext
from app.domain.products import ProductionProductDefinition
from app.domain.artifacts import Artifact, ArtifactKind, ArtifactStatus, validate_production_artifact
from app.domain.output_contracts import OutputContractDefinition
from app.domain.recipes import BOOK_TO_TELEGRAM_POST
from app.application.recipe_engine import (
    ProductionExecutionContext,
    build_production_recipe_engine,
)
from app.infrastructure.database.models import (
    ArtifactModel,
    KnowledgeUnitModel,
    PostModel,
    ProductionClaimModel,
    ProductionJobItemModel,
    ProductionJobModel,
    SourceModel,
    TopicModel,
)
from app.infrastructure.database.session import SessionFactory

logger = logging.getLogger(__name__)


def _stale_seconds() -> int:
    return int(os.getenv("NASHR_PRODUCTION_STALE_SECONDS", "900"))


async def _resolve_units(
    session: AsyncSession,
    source_id: UUID,
    scope: ProductionScope,
    topic_id: UUID | None,
    knowledge_unit_ids: list[UUID],
) -> list[KnowledgeUnitModel]:
    source = (
        await session.execute(select(SourceModel).where(SourceModel.id == source_id))
    ).scalar_one_or_none()
    if source is None:
        raise ValueError("Source not found.")

    if scope == ProductionScope.SOURCE:
        if topic_id is not None or knowledge_unit_ids:
            raise ValueError("SOURCE scope accepts only source_id.")
        query = (
            select(KnowledgeUnitModel)
            .where(KnowledgeUnitModel.source_id == source_id)
            .order_by(KnowledgeUnitModel.position, KnowledgeUnitModel.id)
        )
    elif scope == ProductionScope.TOPIC:
        if topic_id is None or knowledge_unit_ids:
            raise ValueError("TOPIC scope requires topic_id and no explicit selection.")
        topic = (
            await session.execute(
                select(TopicModel).where(
                    TopicModel.id == topic_id,
                    TopicModel.source_id == source_id,
                )
            )
        ).scalar_one_or_none()
        if topic is None:
            raise ValueError("Topic not found for source.")
        query = (
            select(KnowledgeUnitModel)
            .where(
                KnowledgeUnitModel.source_id == source_id,
                KnowledgeUnitModel.topic_id == topic_id,
            )
            .order_by(KnowledgeUnitModel.position, KnowledgeUnitModel.id)
        )
    else:
        if topic_id is not None:
            raise ValueError("SELECTION scope does not accept topic_id.")
        if not knowledge_unit_ids:
            raise ValueError("SELECTION scope requires knowledge_unit_ids.")
        if len(set(knowledge_unit_ids)) != len(knowledge_unit_ids):
            raise ValueError("knowledge_unit_ids must not contain duplicates.")
        query = (
            select(KnowledgeUnitModel)
            .where(
                KnowledgeUnitModel.source_id == source_id,
                KnowledgeUnitModel.id.in_(knowledge_unit_ids),
            )
            .order_by(KnowledgeUnitModel.position, KnowledgeUnitModel.id)
        )

    units = (await session.execute(query)).scalars().all()
    if scope == ProductionScope.SELECTION and len(units) != len(knowledge_unit_ids):
        raise ValueError("One or more selected knowledge units do not belong to source.")
    if not units:
        raise ValueError("Production scope contains no knowledge units.")
    return list(units)


async def create_production_job(
    session: AsyncSession,
    source_id: UUID,
    scope: ProductionScope,
    topic_id: UUID | None = None,
    knowledge_unit_ids: list[UUID] | None = None,
    recipe_key: str = BOOK_TO_TELEGRAM_POST.key,
    identity_key: str | None = None,
    product_key: str | None = None,
    idempotency_key: str | None = None,
    request_fingerprint: str | None = None,
    request_payload: dict | None = None,
    thematic_theme: str | None = None,
    custom_instructions: str | None = None,
    source_artifact_id: UUID | None = None,
    source_post_id: UUID | None = None,
) -> ProductionJobModel:
    # A claim is durable user intent; the job is a separate execution record.
    # A missing key means an explicit fresh claim, never a settings-based dedupe.
    ordered_units = [str(unit_id) for unit_id in (knowledge_unit_ids or [])]
    normalized_units = sorted(ordered_units)
    # Thematic composition treats the user's selection order as editorial input.
    # Keep that order in the durable request payload and fingerprint; ordinary
    # production selections retain their historical order-independent dedupe.
    request_units = ordered_units if thematic_theme is not None else normalized_units
    canonical_request_payload = {
        "source_id": str(source_id),
        "scope": scope.value,
        "topic_id": str(topic_id) if topic_id is not None else None,
        "knowledge_unit_ids": request_units,
        "recipe_key": recipe_key,
        "identity_key": identity_key,
        "product_key": product_key,
        "thematic_theme": thematic_theme.strip() if isinstance(thematic_theme, str) else None,
        "custom_instructions": custom_instructions.strip() if isinstance(custom_instructions, str) and custom_instructions.strip() else None,
        "source_artifact_id": str(source_artifact_id) if source_artifact_id is not None else None,
        "source_post_id": str(source_post_id) if source_post_id is not None else None,
    }
    if request_fingerprint is None:
        request_fingerprint = hashlib.sha256(
            json.dumps(canonical_request_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ).hexdigest()
    persisted_request_payload = request_payload if request_payload is not None else canonical_request_payload

    if idempotency_key is not None:
        existing_claim = (await session.execute(
            select(ProductionClaimModel).where(ProductionClaimModel.idempotency_key == idempotency_key)
        )).scalar_one_or_none()
        if existing_claim is not None:
            if existing_claim.request_fingerprint != request_fingerprint:
                raise ValueError("Idempotency key was already used for a different production request.")
            existing_job = (await session.execute(
                select(ProductionJobModel).where(ProductionJobModel.claim_id == existing_claim.id)
            )).scalar_one_or_none()
            if existing_job is None:
                raise RuntimeError("Production claim exists without its execution job.")
            return existing_job

    # Resolve a published product's immutable manifest once at job creation.
    # Legacy products without a manifest may still appear in history, but must not
    # start new work by silently adopting today's active component versions.
    resolver = ControlPlaneResolver()
    resolved_product = await resolver.resolve_product(session, product_key) if product_key is not None else None
    if resolved_product is not None:
        product_definition = ProductionProductDefinition.from_dict(resolved_product.definition)
        if not product_definition.has_immutable_manifest:
            raise ValueError(
                "This legacy product version has no pinned component manifest and cannot start a new job safely. "
                "In /control, create a new product version, explicitly select published prompt and editorial identity "
                "(and verify its recipe, policy, and output contract), publish that version, then retry. "
                "Historical jobs remain resumable from their saved context."
            )
        if identity_key is not None and identity_key != product_definition.identity_key:
            raise ValueError(
                "The runtime identity cannot override the editorial identity selected by the published product."
            )
        refs = product_definition.component_versions
        assert refs is not None
        resolved_prompt = await resolver.resolve_prompt_version(session, refs["prompt"])
        resolved_recipe = await resolver.resolve_recipe_version(session, refs["recipe"])
        resolved_identity = await resolver.resolve_identity_version(session, refs["identity"])
        resolved_output_contract = await resolver.resolve_output_contract_version(session, refs["output_contract"])
        resolved_policy = await resolver.resolve_policy_version(session, refs["policy"])
        recipe_key = resolved_recipe.key
        output_contract_key = resolved_output_contract.key
        policy_key = resolved_policy.key
    else:
        resolved_prompt = await resolver.resolve_prompt(session, EDITORIAL_PROMPT_KEY)
        if not resolved_prompt.body.strip():
            raise LookupError(f"Published editorial prompt '{EDITORIAL_PROMPT_KEY}' is empty.")
        output_contract_key = "TELEGRAM_POST"
        policy_key = "EDITORIAL_DEFAULT"
        resolved_recipe = await resolver.resolve_recipe(session, recipe_key)
        if any(stage.capability_key in {"produce_text_artifact", "compose_thematic_artifact", "render_approved_text_card"} for stage in resolved_recipe.stages):
            raise ValueError("Non-Post artifact recipes must be selected through a Product so the correct Output Contract is pinned.")
        resolved_identity = await resolver.resolve_identity(session, identity_key) if identity_key is not None else None
        resolved_output_contract = await resolver.resolve_output_contract(session, output_contract_key)
        resolved_policy = await resolver.resolve_policy(session, policy_key)

    has_card_stage = any(stage.capability_key == "render_approved_text_card" for stage in resolved_recipe.stages)
    if has_card_stage and len(resolved_recipe.stages) != 1:
        raise ValueError("A design-card recipe must contain only render_approved_text_card; it cannot trigger unrelated production stages.")
    has_card_source = source_artifact_id is not None or source_post_id is not None
    if source_artifact_id is not None and source_post_id is not None:
        raise ValueError("Choose either an approved TEXT Artifact or an approved Post as the design source, not both.")
    if has_card_stage != has_card_source:
        raise ValueError("Design-card recipes require an explicit approved source_artifact_id or source_post_id, and other recipes cannot accept either.")
    if has_card_source:
        if scope != ProductionScope.SELECTION or topic_id is not None or len(knowledge_unit_ids or []) != 1:
            raise ValueError("Design-card production requires selection scope with exactly one lineage anchor.")
        if source_artifact_id is not None:
            source_artifact = (await session.execute(
                select(ArtifactModel).where(ArtifactModel.id == source_artifact_id)
            )).scalar_one_or_none()
            if source_artifact is None:
                raise ValueError("The selected source Artifact does not exist.")
            if source_artifact.kind != ArtifactKind.TEXT.value or source_artifact.review_status != "APPROVED":
                raise ValueError("Design cards can only be produced from a human-approved TEXT Artifact.")
            if source_artifact.source_knowledge_unit_id != knowledge_unit_ids[0]:
                raise ValueError("The selected approved text Artifact must match the selected lineage anchor.")
        if source_post_id is not None:
            source_post = (await session.execute(
                select(PostModel).where(PostModel.id == source_post_id)
            )).scalar_one_or_none()
            if source_post is None:
                raise ValueError("The selected source Post does not exist.")
            if source_post.status != "APPROVED" or not source_post.content.strip():
                raise ValueError("Design cards can only be produced from a human-approved Post with non-empty text.")
            if source_post.knowledge_unit_id != knowledge_unit_ids[0]:
                raise ValueError("The selected approved Post must match the selected lineage anchor.")
        card_contract = OutputContractDefinition.from_dict(resolved_output_contract.definition)
        if card_contract.artifact_kind != ArtifactKind.IMAGE or card_contract.mime_type != "image/png" or card_contract.content_mode != "STORAGE_URI":
            raise ValueError("Design-card product must pin a storage-backed image/png output contract.")

    if thematic_theme is not None:
        thematic_theme = thematic_theme.strip()
        selected_ids = list(knowledge_unit_ids or [])
        if not thematic_theme:
            raise ValueError("Thematic composition requires a non-empty theme.")
        if scope != ProductionScope.SELECTION or topic_id is not None:
            raise ValueError("Thematic composition requires SELECTION scope without a topic.")
        if len(selected_ids) < 2:
            raise ValueError("Thematic composition requires at least two selected knowledge units.")
        if len(set(selected_ids)) != len(selected_ids):
            raise ValueError("Thematic source selection must not contain duplicate knowledge units.")
        if not any(stage.capability_key == "compose_thematic_artifact" for stage in resolved_recipe.stages):
            raise ValueError("The selected product recipe does not include compose_thematic_artifact.")
        selected_result = await session.execute(
            select(KnowledgeUnitModel)
            .options(selectinload(KnowledgeUnitModel.source))
            .where(KnowledgeUnitModel.id.in_(selected_ids))
        )
        selected_by_id = {unit.id: unit for unit in selected_result.scalars().all()}
        missing = [str(unit_id) for unit_id in selected_ids if unit_id not in selected_by_id]
        if missing:
            raise ValueError("One or more thematic source units were not found: " + ", ".join(missing))
        if selected_by_id[selected_ids[0]].source_id != source_id:
            raise ValueError("source_id must match the first selected unit, used only as the legacy lineage anchor.")
        # One thematic request produces one composite Artifact, not one duplicate per source.
        units = [selected_by_id[selected_ids[0]]]
    else:
        if any(stage.capability_key == "compose_thematic_artifact" for stage in resolved_recipe.stages):
            raise ValueError("Thematic product recipe requires thematic_theme and explicit source selection.")
        units = await _resolve_units(
            session,
            source_id,
            scope,
            topic_id,
            knowledge_unit_ids or [],
        )
    claim = ProductionClaimModel(
        id=uuid4(),
        source_id=source_id,
        scope=scope.value,
        idempotency_key=idempotency_key,
        request_fingerprint=request_fingerprint,
        request_payload=persisted_request_payload,
    )
    job = ProductionJobModel(
        id=uuid4(),
        claim_id=claim.id,
        source_id=source_id,
        scope=scope.value,
        status=ProductionJobStatus.QUEUED.value,
        total_items=len(units),
        editorial_prompt_key=resolved_prompt.key,
        editorial_prompt_version=resolved_prompt.version,
        editorial_prompt_body=resolved_prompt.body,
        resolved_context=ResolvedProductionContext.capture(
            resolved_prompt, recipe=resolved_recipe, identity=resolved_identity,
            output_contract=resolved_output_contract, policy=resolved_policy,
            product=resolved_product,
        ).to_dict(),
    )
    session.add(claim)
    session.add(job)
    for position, unit in enumerate(units, start=1):
        session.add(
            ProductionJobItemModel(
                id=uuid4(),
                job_id=job.id,
                knowledge_unit_id=unit.id,
                position=position,
                status=ProductionJobItemStatus.PENDING.value,
            )
        )
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        if idempotency_key is not None:
            existing_claim = (await session.execute(
                select(ProductionClaimModel).where(ProductionClaimModel.idempotency_key == idempotency_key)
            )).scalar_one_or_none()
            if existing_claim is not None:
                if existing_claim.request_fingerprint != request_fingerprint:
                    raise ValueError("Idempotency key was already used for a different production request.")
                existing_job = (await session.execute(
                    select(ProductionJobModel).where(ProductionJobModel.claim_id == existing_claim.id)
                )).scalar_one_or_none()
                if existing_job is not None:
                    return existing_job
        raise
    await session.refresh(job)
    logger.info(
        "event=PRODUCTION_JOB_CREATED job_id=%s source_id=%s scope=%s total=%s",
        job.id,
        source_id,
        scope.value,
        len(units),
    )
    return job


async def _claim_job(job_id: UUID) -> bool:
    async with SessionFactory() as session:
        result = await session.execute(
            update(ProductionJobModel)
            .where(
                ProductionJobModel.id == job_id,
                ProductionJobModel.status == ProductionJobStatus.QUEUED.value,
            )
            .values(
                status=ProductionJobStatus.RUNNING.value,
                attempts=ProductionJobModel.attempts + 1,
                started_at=func.coalesce(ProductionJobModel.started_at, func.now()),
                updated_at=func.now(),
                error_code=None,
                error_message=None,
            )
        )
        await session.commit()
        return result.rowcount == 1


async def _claim_next_item(job_id: UUID) -> UUID | None:
    async with SessionFactory() as session:
        item = (
            await session.execute(
                select(ProductionJobItemModel)
                .where(
                    ProductionJobItemModel.job_id == job_id,
                    ProductionJobItemModel.status == ProductionJobItemStatus.PENDING.value,
                )
                .order_by(ProductionJobItemModel.position)
                .limit(1)
            )
        ).scalar_one_or_none()
        if item is None:
            return None

        result = await session.execute(
            update(ProductionJobItemModel)
            .where(
                ProductionJobItemModel.id == item.id,
                ProductionJobItemModel.status == ProductionJobItemStatus.PENDING.value,
            )
            .values(
                status=ProductionJobItemStatus.RUNNING.value,
                attempts=ProductionJobItemModel.attempts + 1,
                updated_at=func.now(),
                error_code=None,
                error_message=None,
            )
        )
        await session.commit()
        if result.rowcount != 1:
            return None
        return item.id


async def _reconcile_stale_item(session: AsyncSession, job_id: UUID, item: ProductionJobItemModel) -> str:
    """Reconcile durable output/provider state before deciding whether a stale item can rerun."""
    artifact_row = None
    if item.artifact_id is not None:
        artifact_row = (
            await session.execute(
                select(ArtifactModel).where(ArtifactModel.id == item.artifact_id)
            )
        ).scalar_one_or_none()
    if artifact_row is None:
        artifact_row = (
            await session.execute(
                select(ArtifactModel)
                .where(
                    ArtifactModel.production_job_id == job_id,
                    ArtifactModel.source_knowledge_unit_id == item.knowledge_unit_id,
                    ArtifactModel.status == ArtifactStatus.AVAILABLE.value,
                )
                .order_by(ArtifactModel.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if artifact_row is not None:
        kind = str(artifact_row.kind)
        if kind in {ArtifactKind.POST.value, ArtifactKind.TEXT.value}:
            valid_output = isinstance(artifact_row.content, str) and bool(artifact_row.content.strip())
        else:
            mime_prefix = {
                ArtifactKind.IMAGE.value: "image/",
                ArtifactKind.VIDEO.value: "video/",
                ArtifactKind.AUDIO.value: "audio/",
            }.get(kind)
            valid_output = (
                mime_prefix is not None
                and isinstance(artifact_row.storage_uri, str)
                and bool(artifact_row.storage_uri.strip())
                and isinstance(artifact_row.mime_type, str)
                and artifact_row.mime_type.startswith(mime_prefix)
            )
        if artifact_row.status == ArtifactStatus.AVAILABLE.value and valid_output:
            item.status = ProductionJobItemStatus.COMPLETED.value
            item.artifact_id = artifact_row.id
            item.post_id = artifact_row.post_id if kind == ArtifactKind.POST.value else None
            item.error_code = None
            item.error_message = None
            item.completed_at = now
            item.updated_at = now
            return "COMPLETED"
        item.status = ProductionJobItemStatus.FAILED.value
        item.error_code = "PRODUCTION_OUTPUT_RECONCILIATION_REQUIRED"
        item.error_message = "A persisted output exists but failed the recovery validity checks; inspect it before retrying."
        item.updated_at = now
        return "FAILED"

    if item.provider_operation_name:
        # Keep the provider handle. The capability must resume/poll this operation;
        # a terminal FAILED provider operation is the only basis for a new attempt.
        item.status = ProductionJobItemStatus.PENDING.value
        item.error_code = "PRODUCTION_RECOVERED_PROVIDER_OPERATION"
        item.error_message = "Recovered with a persisted provider operation handle; resume that operation before creating another."
        item.updated_at = now
        return "PENDING"

    # No durable result and no provider handle: we cannot prove that a paid call did not
    # start before the process stopped. Hold the item instead of automatically regenerating.
    item.status = ProductionJobItemStatus.FAILED.value
    item.error_code = "PROVIDER_OUTCOME_UNKNOWN"
    item.error_message = "The worker stopped without a persisted result or provider operation handle. Reconcile the provider outcome before retrying to avoid duplicate generation."
    item.updated_at = now
    return "FAILED"


async def _recover_stale(job_id: UUID) -> None:
    threshold = datetime.now(timezone.utc) - timedelta(seconds=_stale_seconds())
    async with SessionFactory() as session:
        job = (
            await session.execute(
                select(ProductionJobModel).where(ProductionJobModel.id == job_id).with_for_update()
            )
        ).scalar_one_or_none()
        if job is None or job.status != ProductionJobStatus.RUNNING.value or job.updated_at >= threshold:
            return
        stale_items = (
            await session.execute(
                select(ProductionJobItemModel)
                .where(
                    ProductionJobItemModel.job_id == job_id,
                    ProductionJobItemModel.status == ProductionJobItemStatus.RUNNING.value,
                    ProductionJobItemModel.updated_at < threshold,
                )
                .with_for_update()
            )
        ).scalars().all()
        outcomes = [await _reconcile_stale_item(session, job_id, item) for item in stale_items]
        requires_reconciliation = any(
            item.error_code in {
                "PROVIDER_OUTCOME_UNKNOWN",
                "PRODUCTION_OUTPUT_RECONCILIATION_REQUIRED",
            }
            for item in stale_items
        )
        job.status = ProductionJobStatus.QUEUED.value
        job.current_item_id = None
        job.error_code = (
            "PRODUCTION_RECONCILIATION_REQUIRED"
            if requires_reconciliation
            else "PRODUCTION_RECOVERED_AFTER_PROCESS_STALE"
        )
        job.error_message = (
            "One or more stale items have unknown provider outcomes and were held to prevent duplicate generation."
            if requires_reconciliation
            else "Recovered stale items after reconciling persisted outputs and provider operations."
        )
        job.updated_at = datetime.now(timezone.utc)
        await session.commit()
        logger.warning(
            "event=PRODUCTION_STALE_RECOVERY job_id=%s stale_items=%s completed=%s pending=%s failed=%s",
            job_id,
            len(stale_items),
            outcomes.count("COMPLETED"),
            outcomes.count("PENDING"),
            outcomes.count("FAILED"),
        )


async def _update_progress(job_id: UUID, current_item_id: UUID | None = None) -> tuple[int, int, int, int]:
    async with SessionFactory() as session:
        completed = int(
            (
                await session.execute(
                    select(func.count(ProductionJobItemModel.id)).where(
                        ProductionJobItemModel.job_id == job_id,
                        ProductionJobItemModel.status == ProductionJobItemStatus.COMPLETED.value,
                    )
                )
            ).scalar_one()
            or 0
        )
        failed = int(
            (
                await session.execute(
                    select(func.count(ProductionJobItemModel.id)).where(
                        ProductionJobItemModel.job_id == job_id,
                        ProductionJobItemModel.status == ProductionJobItemStatus.FAILED.value,
                    )
                )
            ).scalar_one()
            or 0
        )
        pending = int(
            (
                await session.execute(
                    select(func.count(ProductionJobItemModel.id)).where(
                        ProductionJobItemModel.job_id == job_id,
                        ProductionJobItemModel.status == ProductionJobItemStatus.PENDING.value,
                    )
                )
            ).scalar_one()
            or 0
        )
        running = int(
            (
                await session.execute(
                    select(func.count(ProductionJobItemModel.id)).where(
                        ProductionJobItemModel.job_id == job_id,
                        ProductionJobItemModel.status == ProductionJobItemStatus.RUNNING.value,
                    )
                )
            ).scalar_one()
            or 0
        )
        await session.execute(
            update(ProductionJobModel)
            .where(ProductionJobModel.id == job_id)
            .values(
                completed_items=completed,
                failed_items=failed,
                current_item_id=current_item_id,
                updated_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()
        return completed, failed, pending, running


async def _complete_item(job_id: UUID, item_id: UUID, artifact: Artifact) -> None:
    async with SessionFactory() as session:
        result = await session.execute(
            update(ProductionJobItemModel)
            .where(
                ProductionJobItemModel.id == item_id,
                ProductionJobItemModel.job_id == job_id,
                ProductionJobItemModel.status == ProductionJobItemStatus.RUNNING.value,
            )
            .values(
                status=ProductionJobItemStatus.COMPLETED.value,
                artifact_id=artifact.id,
                post_id=artifact.post_id if artifact.kind == ArtifactKind.POST else None,
                error_code=None,
                error_message=None,
                completed_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        if result.rowcount != 1:
            await session.rollback()
            raise RuntimeError(
                "Production item completion was not persisted because the item is no longer RUNNING."
            )
        await session.commit()


_MAX_ERROR_CODE_LENGTH = 80
_MAX_ERROR_MESSAGE_LENGTH = 1000


def _redact_error_text(value: object) -> str:
    """Bound provider diagnostics and remove common credential formats."""
    message = str(value)
    message = re.sub(
        r"(?i)(https?://api\.telegram\.org/bot)[^/\s]+",
        r"\1[REDACTED]",
        message,
    )
    message = re.sub(r"(?i)AIza[0-9A-Za-z_-]{20,}", "[REDACTED_API_KEY]", message)
    message = re.sub(
        r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+",
        r"\1[REDACTED]",
        message,
    )
    message = re.sub(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]+=*", "Bearer [REDACTED]", message)
    message = re.sub(
        r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|bot[_-]?token|secret)\b(\s*[:=]\s*)[^\s,;]+",
        r"\1\2[REDACTED]",
        message,
    )
    return message[:_MAX_ERROR_MESSAGE_LENGTH]


def _normalized_error_code(exc: Exception) -> str:
    """Preserve the provider's code as a bounded string for VARCHAR persistence."""
    raw_code = getattr(exc, "code", None)
    if raw_code is None:
        raw_code = getattr(exc, "status_code", None)
    if raw_code is None:
        return "PRODUCTION_ERROR"
    normalized = _redact_error_text(raw_code).strip()
    return normalized[:_MAX_ERROR_CODE_LENGTH] or "PRODUCTION_ERROR"


async def _fail_item(job_id: UUID, item_id: UUID, exc: Exception) -> None:
    code = _normalized_error_code(exc)
    message = _redact_error_text(exc)
    try:
        async with SessionFactory() as session:
            await session.execute(
                update(ProductionJobItemModel)
                .where(
                    ProductionJobItemModel.id == item_id,
                    ProductionJobItemModel.job_id == job_id,
                    ProductionJobItemModel.status == ProductionJobItemStatus.RUNNING.value,
                )
                .values(
                    status=ProductionJobItemStatus.FAILED.value,
                    error_code=code,
                    error_message=message,
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()
    except Exception as persistence_error:
        # A diagnostic write must not prevent a second, minimal state transition.
        # Do not log exception text: provider errors can contain credentials.
        logger.error(
            "event=PRODUCTION_FAILURE_DIAGNOSTICS_WRITE_FAILED job_id=%s item_id=%s error_type=%s",
            job_id,
            item_id,
            type(persistence_error).__name__,
        )
        async with SessionFactory() as session:
            await session.execute(
                update(ProductionJobItemModel)
                .where(
                    ProductionJobItemModel.id == item_id,
                    ProductionJobItemModel.job_id == job_id,
                    ProductionJobItemModel.status == ProductionJobItemStatus.RUNNING.value,
                )
                .values(
                    status=ProductionJobItemStatus.FAILED.value,
                    error_code="PRODUCTION_FAILURE_DIAGNOSTICS_UNAVAILABLE",
                    error_message="Provider operation failed; detailed diagnostics could not be persisted.",
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()


async def _finalize(job_id: UUID) -> None:
    async with SessionFactory() as session:
        pending = int(
            (
                await session.execute(
                    select(func.count(ProductionJobItemModel.id)).where(
                        ProductionJobItemModel.job_id == job_id,
                        ProductionJobItemModel.status.in_(
                            [ProductionJobItemStatus.PENDING.value, ProductionJobItemStatus.RUNNING.value]
                        ),
                    )
                )
            ).scalar_one()
            or 0
        )
        failed = int(
            (
                await session.execute(
                    select(func.count(ProductionJobItemModel.id)).where(
                        ProductionJobItemModel.job_id == job_id,
                        ProductionJobItemModel.status == ProductionJobItemStatus.FAILED.value,
                    )
                )
            ).scalar_one()
            or 0
        )
        if pending:
            return
        status = (
            ProductionJobStatus.FAILED.value
            if failed
            else ProductionJobStatus.COMPLETED.value
        )
        await session.execute(
            update(ProductionJobModel)
            .where(ProductionJobModel.id == job_id)
            .values(
                status=status,
                current_item_id=None,
                completed_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                error_code="PRODUCTION_ITEMS_FAILED" if failed else None,
                error_message=(
                    f"{failed} production item(s) failed."
                    if failed
                    else None
                ),
            )
        )
        await session.commit()


class ProductionJobRunner:
    """Durable item runner that executes each material through its pinned recipe."""

    def __init__(self, drafter, resolver: ControlPlaneResolver | None = None) -> None:
        self.engine = build_production_recipe_engine(drafter, resolver or ControlPlaneResolver())

    async def run(self, job_id: UUID) -> None:
        await _recover_stale(job_id)
        if not await _claim_job(job_id):
            return

        try:
            # Legacy jobs have no provable prompt provenance; never guess a version.
            async with SessionFactory() as session:
                job = (await session.execute(
                    select(ProductionJobModel).where(ProductionJobModel.id == job_id)
                )).scalar_one_or_none()
                if job is None:
                    return
                request_payload_row = None
                if job.claim_id is not None:
                    request_payload_row = (await session.execute(
                        select(ProductionClaimModel.request_payload).where(ProductionClaimModel.id == job.claim_id)
                    )).scalar_one_or_none()
                job_request_payload = request_payload_row if isinstance(request_payload_row, dict) else {}
                resolved_context = None
                pinned_context_payload = job.resolved_context
                pinned_prompt_key = job.editorial_prompt_key
                pinned_prompt_version = job.editorial_prompt_version
                pinned_recipe = BOOK_TO_TELEGRAM_POST
                if job.resolved_context is not None:
                    try:
                        resolved_context = ResolvedProductionContext.from_dict(job.resolved_context)
                    except ValueError as exc:
                        raise LookupError(f"Production job has invalid resolved context: {exc}") from exc
                    pinned = resolved_context.prompt_template
                    if (
                        pinned.key != job.editorial_prompt_key
                        or pinned.version != job.editorial_prompt_version
                        or pinned.body != job.editorial_prompt_body
                    ):
                        raise LookupError("Production job resolved context conflicts with its legacy prompt pin.")
                    pinned_prompt = pinned.body
                else:
                    # Compatibility for jobs created before the context snapshot migration.
                    # These fields are an existing pin, not a lookup of the current published version.
                    pinned_prompt = job.editorial_prompt_body
                    if not job.editorial_prompt_key or job.editorial_prompt_version is None or not pinned_prompt:
                        raise LookupError(
                            "Production job has no pinned editorial prompt; "
                            "historical prompt provenance cannot be established."
                        )

                # Schema-v1 and pre-snapshot jobs predate recipe pinning; their only
                # existing path was BOOK_TO_TELEGRAM_POST, retained as the compatibility route.
                if resolved_context is not None and resolved_context.recipe is not None:
                    pinned_recipe = resolved_context.recipe
                self.engine.validate_recipe(pinned_recipe)
                if resolved_context is not None:
                    pinned_prompt = compose_editorial_prompt(pinned_prompt, resolved_context.identity)
                    if resolved_context.product is not None:
                        product_definition = ProductionProductDefinition.from_dict(resolved_context.product.definition)
                        pinned_prompt = (
                            f"{pinned_prompt}\n\nProduct audience: {product_definition.audience}"
                            f"\nProduct experience: {product_definition.experience}"
                        )
                # Task-scoped guidance is read from the durable claim payload at execution
                # time, so queued and resumed jobs use the same instructions. It may refine
                # the requested treatment, but does not replace the pinned product/recipe,
                # output contract, policy, or execution constraints.
                task_instructions = job_request_payload.get("custom_instructions")
                if isinstance(task_instructions, str) and task_instructions.strip():
                    pinned_prompt = (
                        f"{pinned_prompt}\\n\\n"
                        "Task-specific instructions (apply where compatible with the pinned "
                        "product, recipe, output contract, and policy; do not override them):\\n"
                        f"{task_instructions.strip()}"
                    )

            while True:
                item_id = await _claim_next_item(job_id)
                if item_id is None:
                    break

                async with SessionFactory() as session:
                    item = (
                        await session.execute(
                            select(ProductionJobItemModel).where(
                                ProductionJobItemModel.id == item_id,
                                ProductionJobItemModel.job_id == job_id,
                            )
                        )
                    ).scalar_one()
                    await session.execute(
                        update(ProductionJobModel)
                        .where(ProductionJobModel.id == job_id)
                        .values(
                            current_item_id=item.id,
                            updated_at=datetime.now(timezone.utc),
                        )
                    )
                    await session.commit()
                    knowledge_unit_id = item.knowledge_unit_id
                    provider_operation_context = {
                        "production_job_item_id": item.id,
                        "provider_name": item.provider_name,
                        "provider_operation_name": item.provider_operation_name,
                        "provider_operation_status": item.provider_operation_status,
                    }

                try:
                    async with SessionFactory() as session:
                        artifact = await self.engine.execute(
                            pinned_recipe,
                            ProductionExecutionContext(
                                session=session,
                                inputs={
                                    "knowledge_unit_id": knowledge_unit_id,
                                    **({"source_artifact_id": job_request_payload.get("source_artifact_id")} if job_request_payload.get("source_artifact_id") else {}),
                                    **({"source_post_id": job_request_payload.get("source_post_id")} if job_request_payload.get("source_post_id") else {}),
                                    **provider_operation_context,
                                    **({
                                        "thematic_theme": job_request_payload.get("thematic_theme"),
                                        "thematic_source_knowledge_unit_ids": job_request_payload.get("knowledge_unit_ids", []),
                                    } if job_request_payload.get("thematic_theme") else {}),
                                },
                                configuration={
                                    "editorial_prompt": {
                                        "key": pinned_prompt_key,
                                        "version": pinned_prompt_version,
                                        "body": pinned_prompt,
                                    }
                                },
                                run_id=job_id,
                                resolved_context=pinned_context_payload,
                            ),
                        )
                    validate_production_artifact(
                        artifact,
                        expected_job_id=job_id,
                        expected_source_knowledge_unit_id=knowledge_unit_id,
                    )
                    await _complete_item(job_id, item_id, artifact)
                    await _update_progress(job_id, None)
                except Exception as exc:
                    logger.error(
                        "event=PRODUCTION_ITEM_FAILED job_id=%s item_id=%s error_type=%s",
                        job_id,
                        item_id,
                        type(exc).__name__,
                    )
                    await _fail_item(job_id, item_id, exc)
                    await _update_progress(job_id, None)
                    continue

            await _finalize(job_id)
        except Exception as exc:
            logger.error(
                "event=PRODUCTION_JOB_FAILED job_id=%s error_type=%s",
                job_id,
                type(exc).__name__,
            )
            async with SessionFactory() as session:
                await session.execute(
                    update(ProductionJobModel)
                    .where(ProductionJobModel.id == job_id)
                    .values(
                        status=ProductionJobStatus.FAILED.value,
                        error_code=(
                            "PRODUCTION_IDENTITY_UNAVAILABLE"
                            if isinstance(exc, LookupError) and "identity" in str(exc).lower()
                            else "PRODUCTION_RECIPE_UNAVAILABLE"
                            if isinstance(exc, LookupError) and "recipe" in str(exc).lower()
                            else "PRODUCTION_CONTEXT_INVALID"
                            if isinstance(exc, LookupError) and "resolved context" in str(exc).lower()
                            else "PRODUCTION_PROMPT_UNPINNED"
                            if isinstance(exc, LookupError) and "pinned editorial prompt" in str(exc)
                            else "PRODUCTION_RUNNER_ERROR"
                        ),
                        error_message=_redact_error_text(exc),
                        current_item_id=None,
                        updated_at=datetime.now(timezone.utc),
                    )
                )
                await session.commit()


async def resume_production_job(
    session: AsyncSession,
    job_id: UUID,
    retry_failed: bool = False,
) -> ProductionJobModel:
    job = (
        await session.execute(
            select(ProductionJobModel).where(ProductionJobModel.id == job_id)
        )
    ).scalar_one_or_none()
    if job is None:
        raise ValueError("Production job not found.")
    if job.status == ProductionJobStatus.RUNNING.value:
        raise ValueError("Production job is already running.")
    if job.status == ProductionJobStatus.COMPLETED.value:
        return job

    if retry_failed:
        unresolved = (
            await session.execute(
                select(ProductionJobItemModel.id)
                .where(
                    ProductionJobItemModel.job_id == job_id,
                    ProductionJobItemModel.status == ProductionJobItemStatus.FAILED.value,
                    ProductionJobItemModel.error_code.in_(
                        ["PROVIDER_OUTCOME_UNKNOWN", "PRODUCTION_OUTPUT_RECONCILIATION_REQUIRED"]
                    ),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if unresolved is not None:
            raise ValueError(
                "A failed item has an unresolved provider/output outcome; reconcile it before retrying failed items."
            )

    await session.execute(
        update(ProductionJobItemModel)
        .where(
            ProductionJobItemModel.job_id == job_id,
            ProductionJobItemModel.status == ProductionJobItemStatus.RUNNING.value,
        )
        .values(
            status=ProductionJobItemStatus.PENDING.value,
            error_code="PRODUCTION_RESUMED_STALE_ITEM",
            error_message="Reset to pending during explicit resume.",
            updated_at=datetime.now(timezone.utc),
        )
    )
    if retry_failed:
        await session.execute(
            update(ProductionJobItemModel)
            .where(
                ProductionJobItemModel.job_id == job_id,
                ProductionJobItemModel.status == ProductionJobItemStatus.FAILED.value,
            )
            .values(
                status=ProductionJobItemStatus.PENDING.value,
                error_code=None,
                error_message=None,
                completed_at=None,
                updated_at=datetime.now(timezone.utc),
            )
        )
    job.status = ProductionJobStatus.QUEUED.value
    job.current_item_id = None
    job.error_code = None
    job.error_message = None
    job.completed_at = None
    job.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(job)
    return job


async def recover_stale_production_jobs() -> list[UUID]:
    threshold = datetime.now(timezone.utc) - timedelta(seconds=_stale_seconds())
    recovered: list[UUID] = []
    async with SessionFactory() as session:
        stale_ids = list((await session.execute(
            select(ProductionJobModel.id).where(
                ProductionJobModel.status == ProductionJobStatus.RUNNING.value,
                ProductionJobModel.updated_at < threshold,
            )
        )).scalars().all())
        queued_ids = list((await session.execute(
            select(ProductionJobModel.id).where(
                ProductionJobModel.status == ProductionJobStatus.QUEUED.value
            )
        )).scalars().all())
    for job_id in stale_ids:
        await _recover_stale(job_id)
        recovered.append(job_id)
    for job_id in queued_ids:
        if job_id not in recovered:
            recovered.append(job_id)
    return recovered


async def run_production_job(job_id: UUID) -> None:
    await ProductionJobRunner(GeminiEditorialDrafter(), ControlPlaneResolver()).run(job_id)
