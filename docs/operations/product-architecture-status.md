# Product Architecture — Operational Status

**Checked:** 2026-10-13  
**Observed main HEAD:** `f0ea7a2c23f9f927e2f0f7cc8c9c9eba810b613c`  
**Current commit message:** `fix: prevent Book Map 500 for discovery jobs (#128)`

## Evidence categories

- **Repository:** the GitHub repository `eng540/Nashr` exists, is private, and reports `main` as its default branch.
- **Latest commit:** GitHub commit search returned `f0ea7a2...` as the latest commit observed at check time.
- **CI/deployment:** the commit combined-status endpoint returned a successful Railway integration status URL. This is not, by itself, evidence that all GitHub Actions workflows passed or that the app is deployed at the expected commit.
- **Open PR query:** the GitHub connector's open-PR search returned no results, but the query is not sufficient to prove there are no open PRs across every search mode. Recheck GitHub PR state directly before merge/release decisions.
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
