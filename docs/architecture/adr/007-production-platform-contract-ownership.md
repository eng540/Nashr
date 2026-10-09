# ADR-007: Production Platform Contract Ownership

- **Status:** Accepted for implementation planning
- **Date:** 2026-10-09
- **Scope:** Production Platform Foundation — Package A
- **Baseline:** `main` at the start of branch `architecture/package-a-contract-ownership`
- **Decision type:** Ownership and contract boundaries; no persistence migration in this ADR

## Context

Nashr already has a working book-to-Post-to-Telegram path, a provider-neutral `Artifact` domain contract, Post-backed editorial state, scheduling/publication persistence, and a versioned Prompt Template Control Plane. PR #68 pins the resolved editorial prompt on a `ProductionJob`.

The next platform work must extend those foundations without making `Post`, Telegram, or a Prompt Template synonymous with the whole production system. It must also avoid introducing empty abstractions or changing existing ownership before a compatible consumer exists.

This ADR fixes the ownership and data-contract direction for subsequent implementation packages. It does not claim that the target entities described below already exist in code.

## Decisions

### 1. Current ownership — keep stable

| Concept | Current owner / source of truth | Contract and boundary |
|---|---|---|
| Source and source provenance | Library domain and its persistence | Identifies the original input and its stored reference/metadata. |
| Knowledge / Inventory | Library domain and its persistence | Reusable discovered knowledge linked to its source; it is not a generated artifact. |
| Prompt Template and versions | Control Plane domain/service and persistence | Owns editable, versioned prompt instructions and lifecycle. A prompt is not Identity, Policy, or Recipe. |
| ProductionJob and items | Production application and persistence | Durable orchestration for the existing production path. Prompt key/version/body are pinned when the job is created. |
| Artifact | `app.domain.artifacts.Artifact` | Provider-neutral output contract. It is currently an in-memory/domain contract; it is not an independent persistence model. |
| Post | Editorial domain and persistence | Source of truth for current DRAFT/APPROVED/REJECTED content and editorial state. |
| Review / Approval | Existing Post application/domain flow | Remains Post-centric during the transition. |
| Schedule / ScheduleItem | Existing scheduling application and persistence | Owns timing, eligibility, and execution state; remains Post-centric. |
| Publication ledger | Publication application and persistence | Owns publication outcome/idempotency and consumes an Artifact at the application boundary. |
| Telegram | Distribution adapter | Provider-specific behavior stays outside Artifact and production domain contracts. |
| Frontend workspaces | Their existing workspace boundaries | Library, Content Factory, and Publishing remain distinct; no cross-workspace ownership is introduced here. |

These ownerships are intentional. The existence of a generic Artifact contract does not itself justify an `artifact_id` migration, moving Review or Scheduling ownership, or removing/renaming Post.

### 2. Target Control Plane contract shapes

The following are the approved logical shapes for later implementation. They are not new database tables or public APIs in this package.

- **IdentityVersion** — `identity_key`, `version`, `status`, `purpose`, `audience`, `voice`, `tone`, `principles`, `objectives`, `constraints`, timestamps.
- **PolicyVersion** — `policy_key`, `version`, `status`, typed/validated policy configuration, timestamps. Policies are declarative data interpreted by known validators/capabilities; never Python, SQL, secrets, or arbitrary executable expressions.
- **RecipeVersion** — `recipe_key`, `version`, `status`, ordered stages referencing registered capability keys and validated stage configuration, timestamps. No arbitrary code, unrestricted branching, or provider SDK details.
- **OutputContractVersion** — `contract_key`, `version`, `status`, `artifact_kind`, typed schema/configuration, validation requirements, storage/media expectations, timestamps. Must represent text, image, video, audio, and other planned artifact kinds without requiring every kind to be implemented in one change.
- **PromptTemplateVersion** — the existing versioned prompt contract; it remains a component of resolved context, not a replacement for the four concepts above.

Each independently versioned configuration follows the existing Control Plane lifecycle convention (`DRAFT`, `PUBLISHED`, `ARCHIVED`): published versions are immutable; changes create a new draft; at most one active published version exists per key; production must reject missing/invalid required published configuration rather than guessing.

The eventual `ResolvedProductionContext` must reference explicit keys and versions for each configuration actually used and retain the resolved payload needed to interpret a run. It must distinguish pinned facts from unavailable historical facts. This context is a later package, not implemented by this ADR.

### 3. Target execution and output contracts

- **Recipe** describes an ordered, bounded workflow; it does not own the execution engine.
- **Production Engine / Run** executes registered capabilities and persists status, item progress, attempts, errors, timestamps, and pinned context. Existing `ProductionJob` remains compatible during migration.
- **Artifact** is the generic output boundary. At minimum, the target durable artifact contract needs an ID, kind, state, content or storage reference, source/knowledge provenance, production-run reference, relevant configuration versions, and creation metadata.
- **Post** remains the current editorial representation and maps to the POST artifact kind. The engine must not require every artifact to be a Post.
- **Product** is a later layer that expresses the user-facing purpose/experience and its outputs; it is neither Recipe nor Artifact.
- **Publication** records the act/outcome of making an artifact available; **Distribution** is the adapter boundary that delivers it to a channel/provider.

Image and video products are explicit roadmap goals. Their specialized generation capabilities belong behind registered capability/provider ports; they must not be embedded as type-specific branches throughout the generic orchestration engine.

## Compatibility and migration rules

1. Keep the current `BOOK_TO_TELEGRAM_POST` behavior working throughout the transition.
2. Do not delete or rename Post, rewrite Review/Scheduling/Publication, or add an `artifact_id` migration as part of Package A.
3. Do not add a second source of truth for current editorial status or scheduling state.
4. Keep provider SDKs, retries, quotas, Telegram IDs, and provider payloads out of domain contracts.
5. Do not add queues, workers, microservices, or new infrastructure as part of this contract-definition work.
6. Apply database changes only in the package that introduces a real consumer and includes safe Alembic migration and integration coverage.
7. Any change to this ownership matrix requires a new ADR or an explicit amendment with migration and compatibility consequences.

## Acceptance checks for Package A

- Current Artifact and ResolvedPrompt domain contracts have focused unit coverage.
- Tests protect the Post-to-Artifact compatibility mapping and ensure the generic Artifact boundary remains provider-neutral.
- Existing Post, Review, Scheduling, Publication, and workspace ownership is unchanged.
- No schema, API, runtime behavior, or production configuration changes are introduced.
- Future contract implementations must add validation tests for version lifecycle, invalid/missing configuration, immutable published versions, recipe stage constraints, output-kind schema validation, and pinned-context stability before being consumed by production.

## Consequences

This ADR gives the next implementation packages a stable ownership map and typed logical contract direction without pretending that future entities are already implemented. It preserves current production behavior while making the target separation explicit enough to test as each capability is introduced.
