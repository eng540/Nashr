"""Bounded recipe execution over explicitly registered capabilities."""
import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field as dataclass_field, replace
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.application.artifacts import ensure_post_artifact, find_existing_generic_artifact, persist_generic_artifact
from app.application.control_plane import ControlPlaneResolver
from app.application.posts import DraftKnowledgeUnitText, ProducePost
from app.adapters.image_generation.gemini import GeminiImageGenerator
from app.adapters.audio_generation.gemini_tts import GeminiAudioGenerator
from app.adapters.video_generation.veo import VeoVideoGenerator
from app.domain.artifacts import Artifact, ArtifactKind, ArtifactStatus
from app.domain.output_contracts import OutputContractDefinition
from app.domain.production_context import PinnedOutputContract
from app.domain.recipes import ProductionRecipe, validate_recipe_stage_configuration
from app.infrastructure.artifact_storage import ArtifactStorageError, S3ArtifactStorage
from app.application.provider_operations import record_provider_operation, update_provider_operation_status
from app.infrastructure.database.models import KnowledgeUnitModel


@dataclass(frozen=True)
class ProductionExecutionContext:
    session: AsyncSession
    inputs: Mapping[str, object]
    configuration: Mapping[str, object]
    run_id: UUID | None = None
    resolved_context: Mapping[str, object] | None = None
    stage_configuration: Mapping[str, object] = dataclass_field(default_factory=dict)


class RecipeCapability(Protocol):
    key: str
    version: int

    async def execute(
        self,
        context: ProductionExecutionContext,
        previous_output: object | None,
    ) -> object: ...


class CapabilityRegistry:
    def __init__(self) -> None:
        self._capabilities: dict[tuple[str, int], RecipeCapability] = {}

    def register(self, capability: RecipeCapability) -> None:
        identity = (capability.key, capability.version)
        if identity in self._capabilities:
            raise ValueError(f"Capability '{capability.key}' v{capability.version} is already registered.")
        self._capabilities[identity] = capability

    def resolve(self, key: str, version: int) -> RecipeCapability:
        capability = self._capabilities.get((key, version))
        if capability is None:
            raise LookupError(f"Recipe capability '{key}' v{version} is not registered.")
        return capability


def _stage_system_prompt(context: ProductionExecutionContext, capability_key: str) -> str:
    editorial_prompt = context.configuration.get("editorial_prompt")
    if not isinstance(editorial_prompt, Mapping) or not isinstance(editorial_prompt.get("body"), str):
        raise ValueError(f"{capability_key} capability requires a resolved editorial_prompt body.")
    system_prompt = editorial_prompt["body"]
    style_instructions = context.stage_configuration.get("style_instructions")
    if style_instructions is not None:
        if not isinstance(style_instructions, str) or not style_instructions.strip():
            raise ValueError(f"{capability_key} style_instructions must be a non-empty string.")
        system_prompt = f"{system_prompt}\n\nRecipe-specific instructions:\n{style_instructions.strip()}"
    return system_prompt


class ProducePostCapability:
    key = "produce_post"
    version = 1

    def __init__(self, drafter, resolver: ControlPlaneResolver | None = None) -> None:
        self.producer = ProducePost(drafter, resolver or ControlPlaneResolver())

    async def execute(
        self,
        context: ProductionExecutionContext,
        previous_output: object | None = None,
    ) -> Artifact:
        knowledge_unit_id = context.inputs.get("knowledge_unit_id")
        if not isinstance(knowledge_unit_id, UUID):
            raise ValueError("produce_post capability requires a knowledge_unit_id input.")
        system_prompt = _stage_system_prompt(context, self.key)
        post = await self.producer.execute(
            context.session,
            knowledge_unit_id,
            system_prompt=system_prompt,
        )
        return await ensure_post_artifact(
            context.session,
            post,
            production_job_id=context.run_id,
            resolved_context=(
                dict(context.resolved_context)
                if context.resolved_context is not None
                else None
            ),
        )


class ProduceTextArtifactCapability:
    key = "produce_text_artifact"
    version = 1

    def __init__(self, drafter, resolver: ControlPlaneResolver | None = None) -> None:
        self.generator = DraftKnowledgeUnitText(drafter, resolver or ControlPlaneResolver())

    async def execute(
        self,
        context: ProductionExecutionContext,
        previous_output: object | None = None,
    ) -> Artifact:
        knowledge_unit_id = context.inputs.get("knowledge_unit_id")
        if not isinstance(knowledge_unit_id, UUID):
            raise ValueError("produce_text_artifact capability requires a knowledge_unit_id input.")
        if context.resolved_context is None or "output_contract" not in context.resolved_context:
            raise ValueError("produce_text_artifact capability requires a pinned output contract.")
        pinned_contract = PinnedOutputContract.from_dict(context.resolved_context["output_contract"])
        contract = OutputContractDefinition.from_dict(pinned_contract.definition)
        drafted = await self.generator.execute(
            context.session, knowledge_unit_id, system_prompt=_stage_system_prompt(context, self.key)
        )
        now = datetime.now(timezone.utc)
        artifact = Artifact(
            id=uuid4(),
            source_knowledge_unit_id=knowledge_unit_id,
            kind=ArtifactKind.TEXT,
            content=drafted.content,
            status=ArtifactStatus.AVAILABLE.value,
            created_at=now,
            updated_at=now,
            mime_type=contract.mime_type,
            production_job_id=context.run_id,
            output_contract_key=pinned_contract.key,
            output_contract_version=pinned_contract.version,
            resolved_context=dict(context.resolved_context),
            metadata={"title": drafted.title},
        )
        return await persist_generic_artifact(
            context.session, artifact, resolved_context=dict(context.resolved_context)
        )


class ProduceImageArtifactCapability:
    """Generate and persist one private, reviewable IMAGE Artifact."""

    key = "produce_image_artifact"
    version = 1

    def __init__(self, generator=None, storage_factory=None) -> None:
        self.generator = generator or GeminiImageGenerator()
        self.storage_factory = storage_factory or S3ArtifactStorage.from_environment

    async def execute(
        self,
        context: ProductionExecutionContext,
        previous_output: object | None = None,
    ) -> Artifact:
        knowledge_unit_id = context.inputs.get("knowledge_unit_id")
        if not isinstance(knowledge_unit_id, UUID):
            raise ValueError("produce_image_artifact capability requires a knowledge_unit_id input.")
        if context.resolved_context is None or "output_contract" not in context.resolved_context:
            raise ValueError("produce_image_artifact capability requires a pinned output contract.")
        product = context.resolved_context.get("product")
        if not isinstance(product, Mapping) or not isinstance(product.get("definition"), Mapping):
            raise ValueError("produce_image_artifact capability requires a pinned product definition.")

        existing = await find_existing_generic_artifact(
            context.session,
            production_job_id=context.run_id,
            source_knowledge_unit_id=knowledge_unit_id,
            kind=ArtifactKind.IMAGE,
        )
        if existing is not None:
            return existing

        pinned_contract = PinnedOutputContract.from_dict(context.resolved_context["output_contract"])
        contract = OutputContractDefinition.from_dict(pinned_contract.definition)
        if contract.artifact_kind != ArtifactKind.IMAGE.value or contract.content_mode != "STORAGE_URI":
            raise ValueError("produce_image_artifact requires an IMAGE storage-backed output contract.")

        # Fail before spending on generation if durable storage is not configured.
        storage = self.storage_factory()
        result = await context.session.execute(
            select(KnowledgeUnitModel)
            .options(selectinload(KnowledgeUnitModel.source))
            .where(KnowledgeUnitModel.id == knowledge_unit_id)
        )
        unit = result.scalar_one_or_none()
        if unit is None:
            raise ValueError("Knowledge unit not found.")
        source = unit.source
        source_name = (source.book_title or source.filename) if source is not None else "المصدر"
        product_definition = product["definition"]
        audience = str(product_definition.get("audience", "Readers of Arabic literature and culture"))
        experience = str(product_definition.get("experience", "A source-grounded editorial illustration"))
        style_instructions = context.stage_configuration.get("style_instructions")
        if style_instructions is not None and (
            not isinstance(style_instructions, str) or not style_instructions.strip()
        ):
            raise ValueError("produce_image_artifact style_instructions must be a non-empty string.")

        aspect_ratio = context.stage_configuration.get("aspect_ratio", "1:1")
        image_size = context.stage_configuration.get("image_size", "1K")
        prompt = (
            "Create one original, high-quality editorial illustration inspired by the source material below. "
            "Do not include readable text, captions, logos, or watermarks unless the recipe instructions explicitly require them. "
            "Respect the source's cultural context; do not invent named people or historical facts.\n\n"
            f"Audience: {audience}\nIntended experience: {experience}\n"
            f"Source title: {unit.title}\nSource name: {source_name}\n"
            f"Source material (bounded excerpt):\n{unit.content[:6000]}"
        )
        if style_instructions:
            prompt += f"\n\nVisual direction:\n{style_instructions.strip()}"

        generated = await self.generator.generate(
            prompt,
            aspect_ratio=aspect_ratio,
            image_size=image_size,
        )
        if generated.mime_type != contract.mime_type:
            raise ValueError(
                f"Generated image MIME type {generated.mime_type!r} does not match the pinned contract {contract.mime_type!r}."
            )
        extension = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}[generated.mime_type]
        artifact_id = uuid4()
        storage_key = f"artifacts/{knowledge_unit_id}/{context.run_id or uuid4()}/{artifact_id}.{extension}"
        storage_uri = await storage.put(
            key=storage_key,
            content=generated.content,
            content_type=generated.mime_type,
        )
        now = datetime.now(timezone.utc)
        artifact = Artifact(
            id=artifact_id,
            source_knowledge_unit_id=knowledge_unit_id,
            kind=ArtifactKind.IMAGE,
            content=None,
            status=ArtifactStatus.AVAILABLE.value,
            created_at=now,
            updated_at=now,
            storage_uri=storage_uri,
            mime_type=generated.mime_type,
            production_job_id=context.run_id,
            output_contract_key=pinned_contract.key,
            output_contract_version=pinned_contract.version,
            resolved_context=dict(context.resolved_context),
            metadata={
                "title": unit.title,
                "source_name": source_name,
                "model": generated.model,
                "aspect_ratio": aspect_ratio,
                "image_size": image_size,
            },
        )
        try:
            return await persist_generic_artifact(
                context.session,
                artifact,
                resolved_context=dict(context.resolved_context),
            )
        except Exception:
            try:
                await storage.delete(storage_uri)
            except (AttributeError, ArtifactStorageError, ValueError):
                pass
            raise


class ProduceVideoArtifactCapability:
    """Generate a long-running Veo video while persisting the provider handle for retries."""

    key = "produce_video_artifact"
    version = 1

    def __init__(self, generator=None, storage_factory=None, *, poll_interval_seconds: float = 10, timeout_seconds: float = 900) -> None:
        self.generator = generator or VeoVideoGenerator()
        self.storage_factory = storage_factory or S3ArtifactStorage.from_environment
        self.poll_interval_seconds = poll_interval_seconds
        self.timeout_seconds = timeout_seconds

    async def execute(
        self,
        context: ProductionExecutionContext,
        previous_output: object | None = None,
    ) -> Artifact:
        knowledge_unit_id = context.inputs.get("knowledge_unit_id")
        item_id = context.inputs.get("production_job_item_id")
        if not isinstance(knowledge_unit_id, UUID):
            raise ValueError("produce_video_artifact capability requires a knowledge_unit_id input.")
        if not isinstance(item_id, UUID):
            raise ValueError("produce_video_artifact capability requires a durable production_job_item_id.")
        if context.resolved_context is None or "output_contract" not in context.resolved_context:
            raise ValueError("produce_video_artifact capability requires a pinned output contract.")
        product = context.resolved_context.get("product")
        if not isinstance(product, Mapping) or not isinstance(product.get("definition"), Mapping):
            raise ValueError("produce_video_artifact capability requires a pinned product definition.")

        existing = await find_existing_generic_artifact(
            context.session,
            production_job_id=context.run_id,
            source_knowledge_unit_id=knowledge_unit_id,
            kind=ArtifactKind.VIDEO,
        )
        if existing is not None:
            return existing

        pinned_contract = PinnedOutputContract.from_dict(context.resolved_context["output_contract"])
        contract = OutputContractDefinition.from_dict(pinned_contract.definition)
        if contract.artifact_kind != ArtifactKind.VIDEO.value or contract.content_mode != "STORAGE_URI":
            raise ValueError("produce_video_artifact requires a VIDEO storage-backed output contract.")

        # Validate storage before submitting a paid, long-running provider operation.
        storage = self.storage_factory()
        result = await context.session.execute(
            select(KnowledgeUnitModel)
            .options(selectinload(KnowledgeUnitModel.source))
            .where(KnowledgeUnitModel.id == knowledge_unit_id)
        )
        unit = result.scalar_one_or_none()
        if unit is None:
            raise ValueError("Knowledge unit not found.")
        source = unit.source
        source_name = (source.book_title or source.filename) if source is not None else "المصدر"
        product_definition = product["definition"]
        audience = str(product_definition.get("audience", "Readers of Arabic literature and culture"))
        experience = str(product_definition.get("experience", "A source-grounded editorial video"))
        style_instructions = context.stage_configuration.get("style_instructions")
        if style_instructions is not None and (
            not isinstance(style_instructions, str) or not style_instructions.strip()
        ):
            raise ValueError("produce_video_artifact style_instructions must be a non-empty string.")

        aspect_ratio = context.stage_configuration.get("aspect_ratio", "9:16")
        resolution = context.stage_configuration.get("resolution", "720p")
        duration_seconds = context.stage_configuration.get("duration_seconds", 5)
        prompt = (
            "Create a short, coherent, source-grounded editorial video inspired by the material below. "
            "Avoid captions, logos, or watermarks; do not invent historical facts or named people. "
            "Use culturally respectful visual storytelling.\n\n"
            f"Audience: {audience}\nIntended experience: {experience}\n"
            f"Source title: {unit.title}\nSource name: {source_name}\n"
            f"Source material (bounded excerpt):\n{unit.content[:6000]}"
        )
        if style_instructions:
            prompt += f"\n\nVisual direction:\n{style_instructions.strip()}"

        provider_name = getattr(self.generator, "provider_name", "google-veo")
        operation_name = context.inputs.get("provider_operation_name")
        stored_provider = context.inputs.get("provider_name")
        operation_status = context.inputs.get("provider_operation_status")
        if operation_name is not None and stored_provider != provider_name:
            raise ValueError("Persisted provider operation belongs to a different provider.")
        if not isinstance(operation_name, str) or operation_status == "FAILED":
            operation_name = await self.generator.start(
                prompt,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                duration_seconds=duration_seconds,
            )
            await record_provider_operation(
                context.session,
                item_id=item_id,
                provider_name=provider_name,
                operation_name=operation_name,
            )
            operation_status = "SUBMITTED"

        deadline = asyncio.get_running_loop().time() + self.timeout_seconds
        while True:
            operation = await self.generator.poll(operation_name)
            if operation.done:
                if operation.status != "SUCCEEDED" or not operation.content:
                    await update_provider_operation_status(
                        context.session, item_id=item_id, status="FAILED"
                    )
                    raise ValueError(operation.error_message or "Video provider returned no usable video.")
                if operation_status != "SUCCEEDED":
                    await update_provider_operation_status(
                        context.session, item_id=item_id, status="SUCCEEDED"
                    )
                generated_content = operation.content
                generated_mime_type = operation.mime_type
                generated_model = operation.model or "unknown"
                break
            if operation_status == "SUCCEEDED":
                raise RuntimeError("Provider operation was marked SUCCEEDED but is still running.")
            if operation_status != "RUNNING":
                await update_provider_operation_status(
                    context.session, item_id=item_id, status="RUNNING"
                )
                operation_status = "RUNNING"
            if asyncio.get_running_loop().time() >= deadline:
                # Keep the provider handle in RUNNING so a later retry resumes polling instead of resubmitting.
                raise TimeoutError("Video generation is still running; retry the item to resume the persisted provider operation.")
            await asyncio.sleep(self.poll_interval_seconds)

        if generated_mime_type != contract.mime_type:
            raise ValueError(
                f"Generated video MIME type {generated_mime_type!r} does not match the pinned contract {contract.mime_type!r}."
            )
        artifact_id = uuid4()
        storage_key = f"artifacts/{knowledge_unit_id}/{context.run_id or uuid4()}/{artifact_id}.mp4"
        storage_uri = await storage.put(
            key=storage_key,
            content=generated_content,
            content_type=generated_mime_type,
        )
        now = datetime.now(timezone.utc)
        artifact = Artifact(
            id=artifact_id,
            source_knowledge_unit_id=knowledge_unit_id,
            kind=ArtifactKind.VIDEO,
            content=None,
            status=ArtifactStatus.AVAILABLE.value,
            created_at=now,
            updated_at=now,
            storage_uri=storage_uri,
            mime_type=generated_mime_type,
            production_job_id=context.run_id,
            output_contract_key=pinned_contract.key,
            output_contract_version=pinned_contract.version,
            resolved_context=dict(context.resolved_context),
            metadata={
                "title": unit.title,
                "source_name": source_name,
                "model": generated_model,
                "aspect_ratio": aspect_ratio,
                "resolution": resolution,
                "duration_seconds": duration_seconds,
            },
        )
        try:
            return await persist_generic_artifact(
                context.session, artifact, resolved_context=dict(context.resolved_context)
            )
        except Exception:
            try:
                await storage.delete(storage_uri)
            except (AttributeError, ArtifactStorageError, ValueError):
                pass
            raise


class ProduceAudioArtifactCapability:
    """Create spoken narration as a private AUDIO Artifact for generic review."""

    key = "produce_audio_artifact"
    version = 1

    def __init__(self, drafter, resolver: ControlPlaneResolver | None = None, audio_generator=None, storage_factory=None) -> None:
        self.drafter = drafter
        self.resolver = resolver or ControlPlaneResolver()
        self.audio_generator = audio_generator or GeminiAudioGenerator()
        self.storage_factory = storage_factory or S3ArtifactStorage.from_environment

    async def execute(
        self,
        context: ProductionExecutionContext,
        previous_output: object | None = None,
    ) -> Artifact:
        knowledge_unit_id = context.inputs.get("knowledge_unit_id")
        if not isinstance(knowledge_unit_id, UUID):
            raise ValueError("produce_audio_artifact capability requires a knowledge_unit_id input.")
        if context.resolved_context is None or "output_contract" not in context.resolved_context:
            raise ValueError("produce_audio_artifact capability requires a pinned output contract.")
        product = context.resolved_context.get("product")
        if not isinstance(product, Mapping) or not isinstance(product.get("definition"), Mapping):
            raise ValueError("produce_audio_artifact capability requires a pinned product definition.")

        existing = await find_existing_generic_artifact(
            context.session,
            production_job_id=context.run_id,
            source_knowledge_unit_id=knowledge_unit_id,
            kind=ArtifactKind.AUDIO,
        )
        if existing is not None:
            return existing

        pinned_contract = PinnedOutputContract.from_dict(context.resolved_context["output_contract"])
        contract = OutputContractDefinition.from_dict(pinned_contract.definition)
        if contract.artifact_kind != ArtifactKind.AUDIO.value or contract.content_mode != "STORAGE_URI":
            raise ValueError("produce_audio_artifact requires an AUDIO storage-backed output contract.")

        storage = self.storage_factory()
        drafted = await DraftKnowledgeUnitText(self.drafter, self.resolver).execute(
            context.session,
            knowledge_unit_id,
            system_prompt=_stage_system_prompt(context, self.key),
        )
        voice = context.stage_configuration.get("voice", "Kore")
        speech_style = context.stage_configuration.get("speech_style", "clear, warm literary narration")
        generated = await self.audio_generator.generate(
            drafted.content,
            voice=voice,
            style=speech_style,
        )
        if generated.mime_type != contract.mime_type:
            raise ValueError(
                f"Generated audio MIME type {generated.mime_type!r} does not match the pinned contract {contract.mime_type!r}."
            )
        artifact_id = uuid4()
        storage_key = f"artifacts/{knowledge_unit_id}/{context.run_id or uuid4()}/{artifact_id}.wav"
        storage_uri = await storage.put(
            key=storage_key,
            content=generated.content,
            content_type=generated.mime_type,
        )
        now = datetime.now(timezone.utc)
        artifact = Artifact(
            id=artifact_id,
            source_knowledge_unit_id=knowledge_unit_id,
            kind=ArtifactKind.AUDIO,
            content=None,
            status=ArtifactStatus.AVAILABLE.value,
            created_at=now,
            updated_at=now,
            storage_uri=storage_uri,
            mime_type=generated.mime_type,
            production_job_id=context.run_id,
            output_contract_key=pinned_contract.key,
            output_contract_version=pinned_contract.version,
            resolved_context=dict(context.resolved_context),
            metadata={
                "title": drafted.title,
                "transcript": drafted.content[:20000],
                "model": generated.model,
                "voice": voice,
                "speech_style": speech_style,
            },
        )
        try:
            return await persist_generic_artifact(
                context.session, artifact, resolved_context=dict(context.resolved_context)
            )
        except Exception:
            try:
                await storage.delete(storage_uri)
            except (AttributeError, ArtifactStorageError, ValueError):
                pass
            raise


class ProductionRecipeEngine:
    def __init__(self, capabilities: CapabilityRegistry) -> None:
        self.capabilities = capabilities

    def validate_recipe(self, pinned_recipe: ProductionRecipe) -> None:
        # The persisted snapshot is the recipe source of truth for this run.
        # Only registered capability implementations may execute its declarative stages.
        for stage in pinned_recipe.stages:
            self.capabilities.resolve(stage.capability_key, stage.capability_version)
            validate_recipe_stage_configuration(stage)

    async def execute(
        self,
        pinned_recipe: ProductionRecipe,
        context: ProductionExecutionContext,
    ) -> Artifact:
        self.validate_recipe(pinned_recipe)
        output: object | None = None
        for stage in pinned_recipe.stages:
            capability = self.capabilities.resolve(
                stage.capability_key, stage.capability_version
            )
            stage_context = replace(context, stage_configuration=stage.configuration)
            output = await capability.execute(stage_context, output)

        if not isinstance(output, Artifact):
            raise TypeError("The final recipe stage must return a validated Artifact.")
        return output


def build_production_recipe_engine(
    drafter,
    resolver: ControlPlaneResolver | None = None,
) -> ProductionRecipeEngine:
    capabilities = CapabilityRegistry()
    capabilities.register(ProducePostCapability(drafter, resolver))
    capabilities.register(ProduceTextArtifactCapability(drafter, resolver))
    capabilities.register(ProduceImageArtifactCapability())
    capabilities.register(ProduceVideoArtifactCapability())
    capabilities.register(ProduceAudioArtifactCapability(drafter, resolver))
    return ProductionRecipeEngine(capabilities=capabilities)
