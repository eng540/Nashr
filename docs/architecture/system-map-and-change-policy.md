# Nashr System Map, Delivery Status, and Change Policy

**Document purpose:** A durable entry point for developers and reviewers. It records what exists, what has actually been verified, what remains a future goal, and when implementation work is justified.
**Last reviewed:** 2026-10-11
**Repository:** `eng540/Nashr`
**Latest UX review baseline:** `f2122d4ff75b1228d910f7ad6dd4c0461c00c774` (2026-10-12; verify current `main` before relying on this snapshot).
**Status semantics:** “Merged” means code/docs are on main; “CI passed” means the relevant PR checks passed; “deployed” means Railway reports a successful deployment for the commit; none of these alone proves full end-to-end production acceptance.

## 1. How to use this document

Start here when joining the project or resuming work after a break. Then read the linked, more detailed documents:
- [Current architecture baseline](current-baseline.md) — historical baseline and ownership decisions; check its Shared Production Engine status addendum and the current main commit before relying on historical sections.
- [Shared Production Engine lifecycle audit](shared-production-engine-lifecycle-audit-2026-10-11.md) — original audit findings and subsequent follow-up status.
- [Shared Production Engine contract](shared-production-engine-contract.md) — required boundaries and output/lifecycle rules; it is a contract, not proof that every acceptance item has passed.
- [Foundation roadmap](foundation-roadmap.md) — wider product/architecture sequence.
- [UX experience audit](../ux/experience-audit.md) — verified UX findings, target flows, and acceptance rules.
- [UX workflow/function inventory](../ux/workflow-and-function-inventory.md) — durable function IDs and end-to-end workflow contracts.
- [UX implementation log](../ux/implementation-log.md) — current branch/PR/test status and handoff notes.

For any new task, inspect the current `main`, relevant code, tests, recent PRs, and these documents first. Do not assume a status in a dated snapshot is still current without checking.

## 2. Product map

Nashr is an Arabic content-production system. Its main workspaces and responsibilities are intentionally separate:

1. **Library / Console** — source ingestion, analysis, knowledge, and material inventory.
2. **Content Factory** — production jobs, generated outputs, editing, review, and approval.
3. **Publishing** — selection of eligible approved content, scheduling, and distribution.
4. **Control Plane** — versioned configuration that affects production, including prompt templates and pinned run context.

Conceptual flow:

`Source → Knowledge / Inventory → Production Job + Recipe → Capability / Provider → Artifact → Review → Publication / Distribution`

This is a logical flow, not a claim that every modality has passed complete live end-to-end acceptance.

### Ownership rules

- **Production Job / Item:** durable orchestration, state, attempts, progress, and completion.
- **Recipe Engine:** ordered stages and registered capability resolution.
- **Capability/provider adapter:** modality-specific input preparation, external provider interaction, and type-specific output checks.
- **Artifact:** provider-neutral output contract and provenance; it must not contain Telegram-specific domain logic.
- **Post:** current editorial persistence and approval state for post-backed content. It is not automatically replaced by Artifact.
- **Review:** remains Post-centric where current product persistence requires it; generic Artifact review paths also exist for non-Post outputs.
- **Publishing / Scheduling:** owns publication eligibility, timing, and distribution state. Telegram remains an external adapter.
- **Control Plane:** resolves/pins configuration for a run; an active run must not silently change configuration halfway through execution.

Do not migrate ownership or add new abstractions merely to make the model look more symmetrical. Require a real consumer, a compatibility plan, and tests.

## 3. Shared Production Engine Reliability: what is implemented

The following follow-up PRs were merged to `main` and their PR CI passed, according to the review record through PR #121:

| PR | Delivered change | What it does not prove |
|---|---|---|
| #108 | Initial lifecycle audit and identified risk areas | Does not itself fix all audit findings |
| #109 | Guarded conditional item completion by checking update row count | Does not prove every crash window is covered |
| #110 | Documented shared engine/capability contract | A contract is not implementation evidence by itself |
| #111 | Common Artifact result-envelope validation before completion | Does not prove the object is physically readable in storage |
| #112 | Stale recovery checks for existing Artifact and persisted provider operation; unknown outcomes are held instead of blindly retried | Does not resolve unknown external outcomes automatically |
| #113 | Ambiguous video provider-start outcomes classified as unknown | Does not guarantee the provider supports lookup/idempotency |
| #114 | Shared ambiguous-outcome classification used at Gemini text/image/audio and fal image call boundaries | Does not eliminate every provider-specific ambiguity |
| #115 | Regression test reuses a saved Artifact after a simulated completion crash window | Does not cover all storage/database crash permutations |
| #116 | Architecture/status documentation update | Documentation only |
| #117 | Persisted item-derived status counts and visible running/reconciliation indicators; unsafe retry is suppressed for unknown outcomes | Does not provide a privileged reconciliation action |
| #118 | Fake-provider timeout regression tests for Gemini text/image/audio | Does not exercise paid live providers |
| #119 | Documentation/status update | Documentation only |
| #120 | Item-level provider operation diagnostics exposed read-only in API/UI for unknown/reconciliation states | Does not resolve or override held states |
| #121 | Documentation updated to reflect the above status and remaining work | Documentation only |

### Reliability behavior now intended by the implementation

- A conditional database state update that affects no row must not be reported as successful completion.
- A candidate Artifact must pass the shared envelope/linkage checks before an item is marked complete.
- Recovery should reuse a valid saved Artifact when available.
- If a persisted provider operation handle exists, recovery should preserve and resume/poll that operation instead of starting a new paid request.
- If provider acceptance may have occurred but there is neither a recoverable Artifact nor a known operation handle, the system holds the item as an unknown outcome instead of automatically repeating potentially billable work.
- The API/UI surfaces diagnostic information and suppresses the unsafe ordinary retry path for held unknown outcomes.

These are implementation behaviors and selected regression tests, not a declaration that every crash, storage, concurrency, and UI acceptance case has passed.

## 4. Verification record and limits

For the reviewed snapshot after PR #121:
- PR checks were reported successful for PRs #108–#121, including the corrected CI run for PR #120.
- Railway deployment for commit `a0577225be13dd76a20df43d89674fd0cb09196d` was reported `SUCCESS`, with the service online and no warning/critical deployment issues at the time checked.
- This verifies deployment/startup health for that commit only. It is **not** proof of full modality-level production acceptance, object-store readback, all restart/concurrency windows, or end-to-end review visibility after a browser reload.
- No local tests were run as part of this work.
- No Telegram publication was triggered, and no new paid live generation was deliberately run for testing.

Re-check live CI and Railway state before making claims about a later commit. Never infer deployed status merely from a merge.

## 5. Known gaps / future goals — not automatic implementation tasks

The following are recorded as acceptance gaps or future goals. They are **not authorization to implement them immediately**. Revisit them when there is a concrete need, a scheduled acceptance cycle, or evidence of a real production failure:

1. **Controlled reconciliation of held unknown outcomes.** Define a safe, authenticated operator workflow with evidence, reason, fresh Artifact/provider-operation checks, and an audit trail. Do not add a public unauthenticated override. Where the provider lacks lookup or idempotency, document the uncertainty and safe choices rather than promising exactly-once execution.
2. **Fault-injection coverage.** Simulate provider acceptance before operation-handle persistence; provider generation followed by storage failure; object upload followed by Artifact database commit failure; Artifact saved but item completion failed; concurrent resume; restart with stale items; and Artifact metadata whose storage object is missing/unreadable.
3. **Cross-modality contract acceptance.** Maintain a clear POST / TEXT / IMAGE / VIDEO / AUDIO matrix covering transitions, result validation, storage/linkage, recovery/retry, job progress, and review visibility after reload. Use fake providers in CI.
4. **Storage verification and orphan handling.** Distinguish metadata existence from object existence/readability; establish a safe way to identify and reconcile missing or orphaned objects.
5. **Operations / observability.** Document how to detect stale items and provider operations, unknown outcomes, storage read failures, and orphan objects. Add metrics only when their collection path and operational consumer are clear.
6. **Evidence-based production acceptance.** Where acceptance needs live infrastructure, prefer read-only inspection and existing records. Do not create new paid provider jobs or publish to Telegram just to make a checklist look complete.

For every gap, record: status (not started / in progress / verified / deferred), exact evidence, relevant PR/tests, what is still unverified, and the reason for deferral if applicable. Do not label a future goal “implemented” because it is described here.

## 6. Change policy: when to implement

**Default mode is documentation, review, and evidence gathering—not speculative implementation.**

Create an implementation PR only when at least one condition is true:
- a reproducible defect currently blocks normal operation;
- a real failure causes incorrect state, lost output, unsafe duplicate paid work, inaccessible output, or another material operational error;
- a security or data-integrity issue needs prompt remediation;
- a specifically approved milestone is being implemented and its scope is explicit.

Otherwise, document the gap and its trigger for reconsideration. A future goal does not, by itself, justify a code change.

### Required workflow for a justified code change

1. Inspect current `main`, relevant source/call paths, tests, docs, recent PRs, and live evidence where relevant.
2. State the observed failure or approved milestone and its user/operational impact.
3. Keep each PR narrow and reviewable; separate documentation from code when useful.
4. Do not change tests merely to make a failing implementation pass. Update tests only for intentionally changed behavior and explain why.
5. Do not run local tests when the project owner has prohibited them. Report actual CI results, not assumed results.
6. Use fake providers in CI for provider failure/recovery tests.
7. Do not send anything to Telegram. Do not launch new paid live generation solely for testing.
8. After merge, verify the exact deployed commit and Railway health. State explicitly what was and was not verified.
9. Update this document and the detailed contract/audit when implementation status changes.

## 7. Definition of done for the reliability program

Do not mark the shared engine reliability program complete until there is evidence for all of the following:

- A POST / TEXT / IMAGE / VIDEO / AUDIO acceptance matrix with test results and explicit untested cells.
- Crash, concurrency, recovery, and storage-boundary fault-injection results.
- Evidence that completed outputs are actually accessible to review, not merely represented by Artifact rows.
- A safe and documented operator reconciliation process for ambiguous external outcomes.
- An operator runbook and usable diagnostics/metrics for stale items, provider operations, unknown outcomes, storage failures, and orphan objects.
- Links to relevant PRs and actual CI results.
- Exact Railway deployed commit and health evidence for the reviewed release.
- An explicit list of remaining risks and anything not tested.

This gate is intentionally open in the reviewed snapshot. The open gate is a record of acceptance status, not a command to implement every remaining item immediately.

## 8. Scope boundaries

- No Telegram sends as part of this reliability program.
- No paid live generation solely for tests.
- No local tests when prohibited by the project owner.
- No public unauthenticated reconciliation override.
- No claim of exactly-once provider execution unless the provider contract actually supports the required guarantees.
- No broad architecture rewrite, queue/worker expansion, or schema migration without a concrete requirement and a reviewed plan.


## UX workflow implementation — 2026-10-12

The UX review is tracked in `docs/ux/` rather than duplicating detailed findings here. At the reviewed main baseline `f2122d4ff75b1228d910f7ad6dd4c0461c00c774`, `PostBankPage.tsx` still combines production setup, job monitoring, post bank/review, and generic Artifact review. PR #127 (`feat/content-factory-ux-workflow`) is open and unmerged. It adds separated setup/task/review views, a guided three-step production setup, an accurate preflight summary, Arabic job/item status labels, and searchable paginated material selection. CI workflow `38300427595` passed on code/test SHA `065d22aac54cd6782a85ef78889b1f7ba2f3d944` (backend, frontend typecheck/unit/build, and Playwright). PR #127 remains open and unmerged. The corrected wizard and E2E code passed workflow `38303151649` on code/test SHA `fe32899e86ba0ac697e6aabd04a0f353c12b4f87`; later branch commits only update UX documentation and the inventory. See `docs/ux/implementation-log.md` for the final branch HEAD and exact status. No manual responsive/RTL visual verification has been claimed. The job lifecycle still has QUEUED/RUNNING/COMPLETED/FAILED and no separately verified cancel/pause endpoint; unknown provider outcomes remain protected from ordinary retry. See the three UX references above for the inventory, acceptance criteria, and ongoing log.


## UX wizard follow-up — 2026-10-12

PR #127 remains open and unmerged. A code review found that the initial wizard placed TOPIC and SELECTION controls inside the review step. The branch now places all scope-dependent controls in step 2 and labels step 3 “مراجعة إعداد الإنتاج”. Shared readiness checks validate active product/recipe and selected identity, source/book map, and scope-specific requirements before review/start. Browser tests intercept the actual create request for SOURCE/TOPIC/SELECTION and check its payload, selection persistence, option-load failures, and ambiguous-response idempotency. The latest CI SHA must be read from implementation-log.md after the documentation commits; no visual mobile/RTL validation or production validation is claimed.