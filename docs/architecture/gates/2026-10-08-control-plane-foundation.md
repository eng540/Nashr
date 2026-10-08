# Architecture Gate — Control Plane Foundation

Date: 2026-10-08
Base main HEAD: 159e9e56119bc8ebea5bf09e8bc5502214964b91
Branch: feature/control-plane-foundation

## Decision

The editorial policy previously owned by GeminiEditorialDrafter.SYSTEM_PROMPT is moved to a versioned Control Plane boundary while preserving Post, Artifact, Review, Scheduling, Publication, and Distribution ownership.

## KEEP

- Artifact and Publication boundary.
- Post as current editorial persistence/state source of truth.
- Review and Scheduling ownership.
- Gemini provider adapter boundary and provider policy/retry mechanics.
- Library / Content Factory / Publishing workspace separation.

## ADD

- Prompt Template + immutable version records.
- DRAFT / PUBLISHED / ARCHIVED lifecycle.
- One active PUBLISHED version per prompt key, enforced by the publish transition and resolver ambiguity check.
- Control Plane repository/application resolver/API/UI.
- Runtime injection of the resolved prompt into editorial production.
- Idempotent bootstrap through Alembic using the exact existing editorial instruction.

## DEFER

- Full Identity editor.
- Policy system.
- Recipe engine.
- Output Contract editor.
- Expanded Production Run provenance.
- GeminiBookMapper migration.

## PROHIBIT

- Browser → Gemini.
- Adapter → database coupling.
- Python code in configuration.
- Artifact/Post/Review/Scheduling rewrite.
- queues/workers/microservices/Redis/Kafka/Celery.
- Generic Control Plane abstractions without a real consumer.

## Runtime boundary

Application → ControlPlaneResolver → ResolvedPrompt → GeminiEditorialDrafter → Gemini

The resolver owns persistence access. The Gemini adapter receives the resolved instruction as runtime input and has no Control Plane persistence dependency.
