# Nashr Shared Production Engine Contract

**Status:** Architecture contract / implementation target  
**Last reviewed:** 2026-10-11  
**Relationship:** Complements `shared-production-engine-lifecycle-audit-2026-10-11.md`; this document defines the shared rules that follow from the audit. It does not claim every rule is already implemented.

## 1. Ownership boundary

The shared engine owns durable job/item lifecycle and orchestration. A capability owns only modality-specific input preparation, provider interaction, output validation, and returning a durable Artifact through the shared result contract.

| Concern | Owner |
|---|---|
| Resolve and pin recipe, prompt, identity, product, output contract, and policy | Job creation / Control Plane resolver |
| Durable job and item records; claims; attempts; status transitions; progress; finalization | Production job lifecycle |
| Stage order and capability lookup by registered key/version | Recipe Engine |
| Provider request, provider-specific polling, MIME/container validation | Capability + provider adapter |
| Persist provider operation handle/status for resumable long-running calls | Provider-operation service + capability |
| Persist Artifact metadata and provenance; object storage operations | Artifact persistence/storage layer |
| Review decision and user-facing inspection | Review API/UI |
| External distribution/publication | Publication subsystem; outside this reliability program's test scope |

Capabilities must not independently implement job finalization, mutate sibling items, calculate job progress, or bypass the Artifact persistence boundary.

## 2. Shared execution context

Each capability receives a `ProductionExecutionContext` containing:

- `run_id`: durable ProductionJob ID when available.
- `inputs`: source KnowledgeUnit ID and item/provider-operation context; future context fields must be explicitly documented.
- `configuration`: pinned prompt and resolved production context.
- `stage_configuration`: settings for the current recipe stage.
- `resolved_context`: persisted snapshot of recipe/product/output contract/policy/identity and other pinned configuration.
- `session`: the database session supplied for capability work.

A capability must validate required inputs and the pinned output contract before a paid provider call. It must not silently resolve a newer recipe/prompt/policy in the middle of a run.

## 3. Result contract

The final recipe stage must return an `Artifact`. The shared runner must treat that result as a proposal until it validates the result and successfully commits the item-to-Artifact link.

Common Artifact fields:

- stable Artifact ID;
- source KnowledgeUnit ID;
- output kind;
- status;
- creation/update timestamps;
- production job ID and resolved-context provenance where applicable;
- pinned output-contract key/version;
- metadata that does not contain credentials or secrets.

Type-specific requirements:

| Kind | Required result properties |
|---|---|
| POST | A valid Post-backed Artifact, with the corresponding Post association and text content suitable for review. Existing Post idempotency behavior must be preserved. |
| TEXT | Non-empty textual content, `text/plain` MIME, and persisted Artifact association. |
| IMAGE | Private storage reference, MIME type matching actual payload and pinned contract, and media metadata. |
| VIDEO | Private storage reference, validated MP4 payload/MIME matching the pinned contract, and provider-operation provenance where available. |
| AUDIO | Private storage reference, validated audio payload/MIME matching the pinned contract, and appropriate model/voice/transcript provenance. |

A storage-backed Artifact is not valid merely because the provider returned bytes. The storage object and Artifact row must be persisted and the item must reference that Artifact before the item is reported COMPLETED. Where the database and object store cannot participate in one transaction, recovery must reconcile the boundary rather than assuming atomicity.

## 4. Lifecycle states and current compatibility

The current persisted job states include `QUEUED`, `RUNNING`, `COMPLETED`, and `FAILED`. Current item states include `PENDING`, `RUNNING`, `COMPLETED`, and `FAILED`. Provider operation states are `SUBMITTED`, `RUNNING`, `SUCCEEDED`, and `FAILED`.

Do not introduce new persisted state strings without checking API/UI enum mappings, migrations, existing production rows, and older clients. A future `RETRY_WAIT`, `CANCELLED`, or `RECONCILIATION_REQUIRED` state requires a compatibility plan before implementation. Until then, use explicit error codes and a documented safe resume policy where possible.

| State | Meaning | Allowed owner/action |
|---|---|---|
| Job QUEUED | Durable job accepted and eligible to be claimed | Runner may claim it conditionally |
| Job RUNNING | A runner owns the job lifecycle | Runner updates progress/final state; stale recovery must verify recovery safety |
| Job COMPLETED | All items reached successful terminal completion | Must not be set while an item remains pending/running or lacks a valid Artifact association |
| Job FAILED | Job could not finish under current policy, or one or more items failed terminally | Explicit resume may be allowed only after checking item and provider-operation state |
| Item PENDING | Item has not been claimed for current attempt | Runner may claim conditionally |
| Item RUNNING | Item is executing or needs recovery reconciliation | Do not treat as success; do not blindly start a second paid operation |
| Item COMPLETED | Valid output persisted and linked to this item | Terminal for ordinary execution; rerun must be explicit |
| Item FAILED | Current attempt failed | Retry only when the error classification and prior provider state make retry safe |
| Provider SUBMITTED/RUNNING | External operation handle is known and operation may still be active | Poll/resume the same operation; do not replace it with a new operation |
| Provider SUCCEEDED | Provider completed successfully; output may still need local validation/persistence | Reconcile/fetch/persist existing result before any new generation |
| Provider FAILED | Provider operation is terminally failed | A new attempt may be permitted under retry policy, after validating no Artifact already exists |

## 5. Error contract

Errors should be classified by semantics rather than flattened into one message:

- `INPUT_INVALID`: required source, configuration, or pinned contract is invalid; no automatic retry.
- `PROVIDER_RETRYABLE`: provider explicitly rejected/transiently failed and retry is known to be safe; bounded retry with backoff.
- `PROVIDER_TERMINAL`: invalid request, unsupported model/format, or terminal provider rejection; no automatic retry.
- `PROVIDER_AUTH_OR_QUOTA`: authentication, permission, or quota issue; do not loop retries.
- `PROVIDER_OPERATION_RUNNING`: provider accepted the request and is still processing; persist handle and resume polling.
- `PROVIDER_OUTCOME_UNKNOWN`: request may have been accepted but no durable operation handle/result was captured; do not automatically issue another paid request.
- `OUTPUT_INVALID`: returned output fails MIME/container/content validation.
- `STORAGE_FAILED`: object-store write/read/verification failed; reuse generated bytes or provider result if still available, not a fresh generation by default.
- `PERSISTENCE_FAILED`: Artifact or item association could not be committed; reconcile existing records before retry.
- `INTERNAL_ERROR`: unexpected internal failure; preserve safe diagnostics and prevent credentials from entering logs.

These are semantic categories for implementation. Existing persisted provider codes may remain for backward compatibility if normalized and bounded. Do not claim an exception is retryable unless the provider adapter can prove it.

## 6. Idempotency and recovery rules

1. Before invoking a provider, query for an already persisted Artifact matching job, source unit, and output kind.
2. If a provider operation handle exists and status is SUBMITTED/RUNNING, poll that operation; never create a replacement operation merely because the worker restarted or a polling deadline elapsed.
3. If provider status is SUCCEEDED, attempt to retrieve/validate/persist that result before any new generation.
4. If provider status is FAILED, retry can be considered under bounded policy after checking for an existing Artifact.
5. If the request may have been accepted but no operation handle was durably recorded, classify the outcome as unknown and require reconciliation/manual action unless the provider supports a documented idempotency key or lookup mechanism.
6. After Artifact persistence but before item completion, retry must find and reuse the Artifact; it must not call the provider again.
7. A conditional item completion update must check that exactly one RUNNING row changed. A no-op update is a consistency signal, not successful completion.
8. Duplicate API resume requests and concurrent runners must be guarded by database conditional updates/locks.
9. Exactly-once external execution must not be claimed unless the provider's idempotency guarantees and the local persistence boundary actually provide it.
10. Object-store and database writes are not one transaction. Add cleanup where safe and reconciliation for crash windows; do not promise zero orphan objects until that behavior is implemented and tested.

## 7. Progress contract

The API/UI must distinguish at least completed, running, pending, failed, and any retry/reconciliation state adopted by implementation. Counts must derive from persisted item rows, not only the in-memory runner loop. Their sum must equal the total number of items once every state is mapped to exactly one category.

A RUNNING item must be visible and must expose an updated timestamp or diagnostic indicating whether it is active or stale. The initial HTTP response means only that the job was accepted; completion requires a terminal job state and valid linked output for every completed item.

## 8. Required test layers

- Contract tests for every capability's required inputs and output validity.
- Lifecycle tests for conditional claim/completion, item isolation, job finalization, and progress counts.
- Fault-injection tests at provider start, provider polling, object upload, Artifact commit, and item completion boundaries.
- Recovery tests for an existing provider operation, an existing Artifact, a stale RUNNING item, and an unknown provider outcome.
- Concurrent tests for duplicate job dispatch, duplicate resume, and simultaneous item claims.
- Modality tests for POST/TEXT/IMAGE/VIDEO/AUDIO using fake providers and isolated database/storage fixtures.
- API/UI tests proving progress survives page reload and completed outputs are reviewable.
- No live provider calls in CI, and no Telegram activity in any test in this program.

## 9. Acceptance and operational evidence

A capability is compliant only when tests prove the shared lifecycle, valid output persistence, safe retry/recovery, and review visibility—not after one successful generation.

Reports must distinguish:
1. code committed/merged;
2. CI checks passed on the relevant SHA;
3. deployed Railway release;
4. behavior verified in production;
5. untested scenarios;
6. known limitations.

Current limitation: a crash between an external provider accepting a request and Nashr durably recording the operation handle cannot be made exactly-once by local database logic alone. The adapter must support idempotency or lookup, or Nashr must enter an explicit unknown-outcome path instead of blindly retrying. This is a known reliability target, not a solved property claimed by this document.
