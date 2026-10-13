# Product Architecture — Operational Status

**Checked:** 2026-10-13  
**Current main HEAD after PR #129:** `195bf73b0276203f125f7f8a2d45950cf7d9971e`  
**Production code commit:** `f0ea7a2c23f9f927e2f0f7cc8c9c9eba810b613c`  
**Current commit message:** `fix: prevent Book Map 500 for discovery jobs (#128)`

## Evidence categories

- **Repository:** the GitHub repository `eng540/Nashr` exists, is private, and reports `main` as its default branch.
- **Latest commit:** GitHub commit search returned `f0ea7a2...` as the latest commit observed at check time.
- **PR #129:** merged as `195bf73b0276203f125f7f8a2d45950cf7d9971e`. Its latest PR head `a8bb682918fcec5149b60ab6c6938550b5de1639` had GitHub Actions workflow `test` run #670 complete successfully. The merge commit itself had no reported workflow runs/status checks in the queried endpoints.
- **Railway deployment:** project `zealous-communication`, workspace `CoinTellx`, environment `production`, service `Nashr`; latest deployment `5e6e8d3a-2ccb-45c5-b0db-4fe72cd10b16` reports SUCCESS for commit `f0ea7a2c23f9f927e2f0f7cc8c9c9eba810b613c`, created 2026-10-12 21:02:49 UTC. The docs-only merge was not deployed, as expected; no staged Railway changes were present.
- **PR #127:** verified CLOSED and MERGED as `01634eb9312eb13abb76235af032b7008529cf74`; the older UX implementation log statement that it remains open was stale and is corrected in this follow-up.
- **Railway live app/database:** not queried in this documentation pass. No claim is made about live deployment SHA, database product rows, provider operation state, or Artifact availability.
- **Telegram/external distribution:** no send or publication was initiated by this task.

## Product integration snapshot

| Area | Status | Evidence |
|---|---|---|
| Versioned product definition | Implemented | `app/domain/products.py`; resolver in `app/application/control_plane.py` |
| Product version resolution | Implemented | `ControlPlaneResolver.resolve_product` returns a pinned product identity/version/definition |
| Prompt/identity pinning | Partial / needs end-to-end proof | Pinned types in `app/domain/production_context.py`; not fields in `ProductionProductDefinition` |
| Product audience/experience prompt integration | Implemented for the inspected runner | `app/application/production_jobs.py` appends both to prompt |
| Legacy job compatibility | Explicit path exists | Runner uses saved prompt pin for jobs without context and refuses to guess a missing pin |
| Product derivation lineage | Unverified | Not established by inspected code |
| Provider-specific video duration | Unverified | No live product/recipe/provider/output metadata read |
| QUL_WA_LA_TAQUL_VIDEO previous run | Unverified | No live DB/API query |
| Full modality artifact review after reload | Open acceptance item | See architecture system map and shared-engine contract |
| Live deployment of observed HEAD | Unverified | Railway combined status is not a deployment-SHA check |

## Safety constraints for future checks

1. Inspect current product/job/artifact records read-only first.
2. Do not start another video job until the previous operation and Artifact are reconciled.
3. Do not produce the entire book; if authorized and safe, use one material only.
4. Do not send to Telegram or publish externally.
5. Never treat provider request acceptance as successful output creation.
6. Record app commit, product/version, job/item IDs, pinned components, provider operation state, Artifact storage/readback, media duration/dimensions, and review visibility.
7. Keep CI, merge, deploy, and live acceptance as separate statuses.


## Additional execution evidence (2026-10-13)

- Railway logs show repeated HTTP 200 GETs to `/production-jobs/9a1f240a-4e6f-4a69-859a-551b444af087` during 16:42–16:48 UTC. Logs expose request paths/status only, not response JSON. They do not prove the job's current status.
- A job-created log entry exists at 2026-10-13 15:36:19 UTC, but it does not establish item status or provider state.
- Filtered logs did not show a provider-operation event for this job; this is not proof no provider operation exists because no provider API/database query was available.
- The Railway connector provided deployment/configuration and logs but no read-only SQL or arbitrary HTTP response action. The public-web retrieval path could not fetch the live job endpoint. No production mutation or new video request was attempted.
- Current main includes the docs-only PR #129 merge after the production commit; production app SHA remains `f0ea7a2...`.

## Proven product-manifest gaps

The updated Product Model and Gap Audit proves that prompt is resolved globally as `editorial.drafter` before product resolution; identity comes from optional request `identity_key`; recipe, policy, and output contract resolve active versions by key rather than exact versions stored in the product; video capability bypasses the pinned editorial prompt/identity; and the recipe contract allows only 5/6/8-second clips. The current Control Plane draft action versions the same product, not a separate derived product with lineage. No code fix for these gaps has been merged. ADR-001 remains Proposed.

## Product manifest implementation checkpoint — 2026-10-13

- PR #131 (video capability consumes the runner's pinned editorial context) was merged after a successful CI rerun on its exact head. The first run had one Playwright failure in product creation; the same test passed on the base `main` run and passed on rerun. This is treated as a transient E2E failure, not as proof of a code regression.
- Candidate product-manifest work is on `feat/immutable-product-component-manifest`; it is not yet merged or deployed.
- The candidate freezes prompt/identity/recipe/policy/output-contract version IDs into newly published product versions, resolves those exact versions for new jobs, and refuses to start a new job from a legacy product version that lacks a manifest rather than silently adopting active defaults.
- A migration adds new manifest-backed versions only for built-in literary post/text products and keeps the previous versions as history. Custom product definitions are deliberately not auto-rewritten.
- The Control Plane now requires prompt and identity selection for new product drafts; the factory uses the product's pinned identity and filters out legacy products until they are explicitly upgraded.

**Status boundary:** no CI result, merge, Railway deployment, or production acceptance is claimed for the candidate manifest branch. Derivation/lineage, complete compatibility preflight, legacy-product upgrade UX, and actual video duration acceptance remain open. No Telegram send or external publication was performed.

## PR #132 live status checkpoint (2026-10-13)

- PR #132 remains open and must not be merged as part of this task.
- The CI environment failure on SHA 59ddd43b36d0dd122cea5d24d26b59eea47be0fb was not an application-test failure: PostgreSQL container initialization failed while pulling public.ecr.aws/docker/library/postgres:16 with toomanyrequests: Data limit exceeded; no migrations or tests ran on that attempt.
- .github/workflows/test.yml now uses mirror.gcr.io/library/postgres:16. Workflow run 38447408736 succeeded end-to-end on SHA f55b11af828b24b19abcc113dff4f859b481efd1: Initialize containers, Apply migrations, backend tests, frontend typecheck/unit/build, and Playwright all passed. This is evidence for that exact SHA only.
- Subsequent commits add migration rollback/collision guards, product retry coverage, legacy-product upgrade messaging, and identity-override/legacy-product tests. Confirm the latest workflow run for the current PR head before calling this branch CI-passing.
- The migration creates new versions for selected built-in post/text products and preserves previous definitions; custom products are not auto-assigned a generic identity. Legacy products without a manifest are explicitly upgraded in /control; old jobs retain their stored context.
- The migration has not been applied to Railway. No live product row for QUL_WA_LA_TAQUL_VIDEO was retrieved, and no video request, Telegram send, or external publication was performed.

Still open: product derivation lineage and component diff, full capability/provider compatibility preflight, live custom-product inventory/upgrade, and video duration acceptance based on actual output metadata.
