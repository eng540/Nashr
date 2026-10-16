# Design-card production line — implementation record

**Status:** implementation in progress  
**Base examined:** `main` at `3f6f52b0d0edfd24d8a41b0826f99cbecad469f4`  
**Branch:** `feature/design-card-production-line`

This document is the implementation record for the design-card capability. It must be updated with repository/CI/production evidence; a listed task is not proof of completion.

## Architectural findings from the examined main

### Existing capabilities to reuse

- `Artifact` already supports `POST`, `TEXT`, `IMAGE`, `VIDEO`, and `AUDIO`; media artifacts use a private storage URI and MIME type.
- `ProductionRecipe` and its versioned stages dispatch registered capabilities through the shared recipe engine.
- Published product versions carry an immutable component manifest; resolved production context pins component versions.
- `S3ArtifactStorage` provides private object storage and short-lived signed media URLs.
- `GenericArtifactReviewService` provides persisted `DRAFT`, `APPROVED`, and `REJECTED` review for non-POST artifacts.
- POST review remains owned by the canonical Post workflow.
- Publishing is a separate workflow and currently selects approved, eligible Posts. Generic IMAGE artifacts are not automatically proven eligible for that path.
- Production jobs currently resolve their primary inputs as Knowledge Units. Therefore the card line must add an explicit approved-Artifact input boundary; simply registering an image capability in the existing book-to-content job would violate the architecture.

### Required integration boundary

The card line consumes an already-produced and approved content Artifact (or a canonical Post whose editorial status is approved), never a Knowledge Unit as its text source. It creates a new IMAGE Artifact linked to that source Artifact, pins the visual product/recipe/template configuration in provenance, and keeps visual review separate from editorial review. Publishing integration must preserve the existing publishing workflow rather than treating every approved image as a Telegram-ready Post by assumption.

### Avoided duplication

Do not add a separate card database, product registry, object store, job queue, review engine, or publishing scheduler. Extend the existing Product/Recipe/Output Contract/Artifact/storage/review and publication boundaries only where the current contracts are insufficient. A new durable model is justified only if existing Artifact provenance and ProductionJob records cannot represent a real card-production request and its per-item status without conflating unrelated lifecycle states.

## Implementation gates

| Gate | Evidence required | Status |
|---|---|---|
| 0. Baseline and reuse map | Current-main source paths and live Railway status reviewed | Inspected; not a feature-completion claim |
| 1. Contracts and input eligibility | Tests reject unapproved/non-text sources and preserve source Artifact lineage | Pending |
| 2. Renderer selection | CI-tested Arabic shaping/RTL, real dimensions, no silent truncation; runtime compatibility assessed | Pending |
| 3. Shared-engine capability | Capability registered in the existing recipe engine and uses private Artifact storage | Pending |
| 4. Product/template controls | Published, versioned, pinned visual settings; prior output remains immutable | Pending |
| 5. Approved-output selection | Existing ready-output library/API reused; no direct raw-material bypass | Pending |
| 6. Batch/retry | Durable per-item outcomes, retry failed items only, intentional variants remain possible | Pending |
| 7. Visual review | Final stored image is the preview; independent approve/reject lifecycle | Pending |
| 8. Publishing handoff | Existing publication flow consumes the approved card output without creating a parallel scheduler | Pending |
| 9. CI and regression proof | Backend, migration, frontend, browser, contract and failure-path checks pass | Pending |
| 10. Railway proof | Intended commit deployed and safe end-to-end card review flow verified; no external publish | Pending |

## Safety and correctness invariants

1. The approved source text is immutable during rendering.
2. The renderer never asks an image model to typeset the actual card text.
3. Overflow is an explicit failure or an explicitly configured, lossless multi-card split; never silent truncation.
4. A visual approval never changes editorial approval, and vice versa.
5. A generated or approved card is not described as published until the existing publishing workflow confirms publication.
6. Existing product versions and artifacts are not rewritten by migrations or new defaults.
7. Provider/storage calls must fail visibly; no placeholder image is substituted.
8. User-controlled visual settings belong in versioned product/recipe/template configuration, while validation and security constraints remain in code.
9. Every stage's completion claim must cite the relevant PR/CI/deployment evidence.
