# Nashr Shared Production Engine — Lifecycle Audit

**Audit date:** 2026-10-11  
**Audited ref:** `main` at `733aa369c73124658ee551cda3649a726b526bad` (after PR #107)  
**Scope:** Production job/item lifecycle, registered recipe capabilities, provider-operation persistence, artifact storage/persistence, API/runtime recovery, review visibility. Telegram publishing is explicitly excluded from tests and actions in this program.

## Executive finding

Nashr already has a durable database-backed production job model, a registered Recipe Engine, pinned recipe/control-plane context, generic Artifact persistence/review, private media storage, and a durable provider-operation record intended for long-running media providers. These are valuable foundations; a rewrite or new queue is not justified by this audit alone.

The principal reliability risk visible in the current implementation is the **recovery boundary**: stale `RUNNING` items are reset to `PENDING` by the runner/startup recovery and explicit resume paths. This is unsafe unless the capability first reconciles a persisted provider operation and/or checks for an already-persisted artifact. The video capability has a provider-operation handle and attempts to resume it, but generic stale recovery can change item state before that reconciliation. Paid-provider outcomes can therefore become ambiguous across crashes/timeouts. A second risk is that lifecycle policy is split between `ProductionJobRunner`, `ProductionRecipeEngine`, individual capabilities, provider-operation helpers, artifact persistence, and API/UI projections rather than enforced by one explicit state-transition contract.

This is a code-based audit, not a claim that every path has been exercised in Railway. CI status observed for audited HEAD is successful in the repository's reported combined status, but it is not proof of media production or crash recovery in production.

## 1. Current lifecycle map

```text
Content Factory UI
  -> production job API (app/api/routes.py)
  -> create_production_job()
       resolve + pin prompt / recipe / identity / output contract / policy / product
       resolve source materials
       INSERT ProductionJob + ProductionJobItem(PENDING)
       COMMIT
  -> API/background dispatch and startup recovery (app/main.py)
  -> ProductionJobRunner.run(job_id)
       recover stale records
       atomically claim QUEUED job
       load and validate pinned context / recipe
       atomically claim PENDING item -> RUNNING
       pass item ID + persisted provider-operation fields to Recipe Engine
  -> ProductionRecipeEngine.execute()
       validate recipe and stage configuration
       resolve registered capability
  -> capability
       validate pinned product/contract and source
       optional existing-artifact lookup
       invoke provider / poll external operation
       validate provider result
       upload media where required
       persist Artifact / Post + provenance
  -> runner marks item COMPLETED with artifact_id/post_id
  -> recalculate item counts and finalize job
  -> generic artifact review API/UI (non-Post) or Post review UI
```

**Important ordering:** for media capabilities, object storage may succeed before database Artifact persistence. The implementation attempts cleanup in some error paths, but a process crash between object upload and DB commit can still leave an orphan object. Conversely, if the Artifact row is committed but the item completion update fails, the retry must discover and reuse the Artifact before invoking a paid provider.

## 2. Component responsibility inventory

| Component | Current responsibility | Audit observation |
|---|---|---|
| `app/api/routes.py` | Production create/read/resume API and job dispatch | Must be checked alongside runner semantics; HTTP acceptance is not completion. |
| `app/application/production_jobs.py` | Resolve/pin context; create job/items; claim job/items; recovery; progress; item/job finalization; error persistence; resume | Lifecycle and retry/recovery policy are concentrated here, but transitions are implemented as direct conditional SQL updates rather than a single documented transition contract. |
| `app/application/recipe_engine.py` | Registry and recipe-stage execution; capability dispatch; modality-specific execution adapters | Shared orchestration exists, but output idempotency and provider-operation behavior still vary by capability. |
| `app/application/provider_operations.py` | Persist provider handle/state and constrain operation transitions | Important recovery primitive; must be reconciled before a stale item is reset or resubmitted. |
| `app/application/artifacts.py` | Post/generic Artifact lookup and persistence/provenance | Provides a reusable persistence boundary; it is not yet the sole lifecycle owner. |
| `app/infrastructure/artifact_storage.py` | S3-compatible private object storage and signed read URLs | Storage is separate from DB transactions; crash consistency needs reconciliation/orphan handling. |
| `app/infrastructure/database/models.py` + Alembic | Durable job/item/provider-operation/artifact state | Database is the durable source, but the model currently lacks a general attempt/event history sufficient to reconstruct every retry decision. |
| `app/main.py` lifespan | On startup recover stale production jobs and launch their runners | Recovery is automatic; it must not assume every stale RUNNING operation is safe to regenerate. |
| Content Factory UI + `productionJobsApi.ts` | Submit/poll jobs and display item/progress states | UI must use server item states and avoid presenting a RUNNING/stale task as complete. |
| Generic Artifact review API/panel | Display/review non-Post artifacts and signed media URLs | Separate from Post review by design; availability requires both a valid Artifact record and accessible storage object. |

## 3. State and transition observations

The production runner uses job states including `QUEUED`, `RUNNING`, `COMPLETED`, and `FAILED`; item states include `PENDING`, `RUNNING`, `COMPLETED`, and `FAILED`. Provider operations have their own persisted status.

| Transition/path | Current observed behavior | Reliability implication |
|---|---|---|
| Create | Job is persisted as QUEUED; items as PENDING in one DB transaction | Good durable starting point. |
| Claim job | Conditional update QUEUED → RUNNING, increments attempts | Prevents two runners from claiming the same queued job. |
| Claim item | Conditional update PENDING → RUNNING, increments attempts | Prevents two runners from claiming the same pending item at the same instant. |
| Success | Capability returns Artifact; runner updates RUNNING item → COMPLETED with artifact reference | Completion update should verify rowcount and that referenced Artifact is durable/valid. |
| Item error | RUNNING item → FAILED with normalized/redacted error | All exceptions currently converge on failure at runner boundary; retryability is not generally classified here. |
| Finalize | If no PENDING/RUNNING items, job becomes FAILED if any failed items else COMPLETED | Ensure counts include all terminal and future retry/cancel states if model evolves. |
| Stale recovery | Stale RUNNING items are reset to PENDING; stale jobs return to QUEUED | Critical risk: does not itself distinguish a dead process from a still-active paid provider operation. |
| Explicit resume | RUNNING items reset to PENDING; optional failed items reset too | Can cause a new execution unless the capability reconciles existing operation/artifact first. |
| Startup | Recovered and queued jobs are scheduled as tasks | Depends on safe recovery decisions and process lifetime. |

This audit does **not** recommend blindly adding states before tracing existing enums, migrations, API contracts, and UI mappings. The next behavioral PR should formalize allowed transitions and introduce a reconciliation/unknown outcome only if the implementation requires it and compatibility can be preserved.

## 4. Modality comparison

| Capability | Existing shared path | Modality-specific behavior found in code | Main audit concern |
|---|---|---|---|
| POST | Recipe Engine → drafting service → Post/Artifact adapter | Editorial Post persistence and Post review lifecycle | Runner error/retry behavior is generic, but historical Post idempotency semantics must remain unchanged. |
| TEXT | Registered `produce_text_artifact` capability → pinned output contract → generic Artifact persistence | Inline content; the visible implementation invokes drafting before persistence and does not perform the same pre-generation existing-artifact lookup shown in media capabilities | A crash after paid text generation but before persistence may repeat the call; confirm service-level idempotency before changing. |
| IMAGE | Registered `produce_image_artifact` → provider factory (Gemini/fal) → private storage → generic Artifact | Checks for existing Artifact before generation; checks storage availability before provider call; validates returned MIME against pinned contract; attempts object cleanup if DB persistence fails | A crash after upload or during DB persistence can leave an orphan; result must be reconciled before regeneration. The recently fixed FLUX PNG contract mismatch is a concrete provider/contract integration regression. |
| VIDEO | Registered `produce_video_artifact` → Veo adapter → persisted provider operation → polling → MP4 validation → private storage → generic Artifact | Carries item/provider operation state, records operation handle, can resume a named operation, checks for an existing Artifact before starting | Stale reset and explicit resume must not discard the distinction between active, failed, and unknown provider operations. Do not trigger a live video request merely to test this. |
| AUDIO | Registered `produce_audio_artifact` → Gemini TTS → private storage → generic Artifact | Produces WAV and records transcript/model/voice provenance for review | Must verify idempotency around provider success/storage/DB persistence and ensure shared lifecycle changes preserve the existing gimiNashr-backed flow. |

The rows above describe code paths, not a declaration that all modalities have passed full crash-recovery acceptance tests.

## 5. Confirmed findings and severity

| ID | Finding | Evidence in audited code | Severity | Status |
|---|---|---|---|---|
| A-01 | Stale RUNNING items are reset to PENDING without provider reconciliation in generic recovery | `_recover_stale()` and `recover_stale_production_jobs()` update RUNNING items to PENDING; job is queued again | **Critical for paid/long-running work** | Confirmed code behavior; outcome depends on capability and timing |
| A-02 | Explicit resume resets RUNNING items to PENDING | `resume_production_job()` performs this reset before requeue | **High** | Confirmed code behavior |
| A-03 | Item completion update does not inspect update rowcount | `_complete_item()` issues conditional RUNNING → COMPLETED update and commits without checking affected row count | **High** | Confirmed code behavior; stale/racing completion can be silently ignored |
| A-04 | Shared runner classifies every caught item exception as FAILED, without common retryability/unknown-outcome policy | `ProductionJobRunner.run()` catches Exception and calls `_fail_item()` | **High** | Confirmed code behavior; capabilities may have local retries |
| A-05 | Progress projection is limited to completed, failed, pending, running | `_update_progress()` returns four counts and persists only completed/failed counts plus current item; no first-class retry-wait/cancel count in this path | **Medium** | Confirmed code behavior against current runner |
| A-06 | Artifact persistence and item completion are separate commits | Capability persistence returns before runner calls `_complete_item()` | **High** | Confirmed architecture; existing-artifact lookup can help some modalities recover |
| A-07 | Capability idempotency differs: IMAGE/VIDEO explicitly look for an existing generic Artifact before generation; TEXT visible implementation does not | `ProduceImageArtifactCapability.execute`, `ProduceVideoArtifactCapability.execute`, `ProduceTextArtifactCapability.execute` | **High** | Confirmed code behavior; investigate whether lower-level text service provides equivalent protection |
| A-08 | Current baseline document references an old baseline commit and an earlier architecture stage | `docs/architecture/current-baseline.md` says baseline is `f25764e9...`; audited HEAD is `733aa369...` and includes media capability PRs #98–#107 | **Medium** | Confirmed documentation drift |
| A-09 | A successful HTTP response or RUNNING state is not an output acceptance criterion | API/job model and asynchronous runner design | **High** | Acceptance principle; add API/UI and lifecycle tests |

## 6. Hypotheses requiring targeted tests or production evidence

1. **Video stuck at RUNNING:** determine whether it is a genuinely active provider operation, a polling timeout, a process restart, or an artifact/item-finalization split. Inspect its persisted provider handle/status and timestamps before any resume. Do not start a replacement generation while outcome is unknown.
2. **Text duplicate generation:** test crash/failure between model response and Artifact/Post commit with a fake drafter and assert the safe recovery policy.
3. **Media orphan objects:** inject a crash/failure after storage PUT and before Artifact commit; verify cleanup or a reconciliation mechanism.
4. **Concurrent resume/runner race:** race two resume/dispatch attempts against the same job/item and assert only one provider operation is initiated.
5. **Review visibility:** prove that a completed item has a valid Artifact, resolvable signed media URL where applicable, and appears in the expected review panel after a page reload.
6. **Audio recovery:** prove gimiNashr/Gemini TTS output remains reviewable after simulated storage or DB failure without an unintended second paid synthesis.

## 7. Priority order and dependencies

1. **PR-A (this document):** establish evidence-based lifecycle map, findings, scope, and acceptance plan; no runtime behavior change.
2. **PR-B:** define/implement transition and recovery policy. Before resetting a stale item, reconcile provider-operation state and existing artifacts. Add guarded completion rowcount checks and safe handling of unknown provider outcomes. Preserve schema/API compatibility where possible; any migration requires an explicit Alembic migration.
3. **PR-C:** make all capabilities conform to a shared typed execution/result/error contract. Keep provider-specific fields in typed extensions. Add consistent preflight, artifact validation, and idempotency/reconciliation hooks.
4. **PR-D:** contract, recovery, fault-injection, modality integration, API/UI acceptance tests; update operational documentation with exact CI/deployment evidence.

Do not add a queue or new service unless PR-B demonstrates a concrete durability gap that cannot be closed safely with the existing DB-backed runner and startup recovery.

## 8. Safety and validation boundary

- No Telegram messages/posts are sent by this audit or its tests.
- No live image/video/audio/text generation was initiated by this audit.
- No local tests are claimed as run.
- The combined GitHub status observed for audited HEAD `733aa369c73124658ee551cda3649a726b526bad` reported success, but the result is a repository status context rather than evidence of every required reliability scenario.
- Railway deployment/runtime state was not independently inspected in this audit step.
- This is the first audit deliverable, not a claim that the Shared Production Engine program is complete.
