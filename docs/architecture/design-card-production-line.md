# Nashr — approved-output visual derivatives and multi-source composition

**Status:** deterministic card renderer is implemented; this branch makes the Arabic font reproducible and seeds a published deterministic card product. End-to-end Railway rendering, AI-assisted backgrounds, carousel output, and Publishing handoff remain separate acceptance gates.  
**Implementation branch:** `feature/complete-visual-production-line-20261017`  
**Baseline:** `main` at `6be4870b384d2fbb8c08dabe5188c511c13a708b`

This record governs implementation direction. Documentation is not feature completion. Every completion claim must be backed by source changes, tests, CI and deployment evidence.

## Decision summary

Retain the core value of design cards, but do not build a second heavy production system around a headless browser. Prioritize reusable capabilities that transform approved outputs and make Nashr's existing knowledge inventory more valuable.

1. **Multi-source thematic composition** is the strongest differentiated content capability, but is not assumed to be a trivial one-line change. It requires explicit multi-unit selection, source provenance, citation/reference preservation, prompt/version pinning, and tests against unsupported claims.
2. **Lightweight deterministic visual derivatives** should turn an already-approved text output into a real image/carousel without asking an image model to typeset Arabic. Prefer an SVG/vector renderer or a lightweight library only after verifying Arabic shaping, font handling, output fidelity, deploy compatibility and measured resource use. Do not assume marketing claims such as “15 ms” or “near-zero memory” without benchmarks on Nashr's actual runtime.
3. **Multi-format bundle** should reuse the same approved text to prepare configured delivery formats (e.g. Telegram HTML, static card, optional vertical visual/audio pairing) without another editorial-generation call. It is a product-controlled set of derivatives, not a hard-coded rule that every post must produce every format.
4. **Heritage/poetry layout** is a rendering mode, not a rewriting mode. It may arrange the same characters into configurable lines/hemistichs but must not silently normalize, vocalize, correct, paraphrase, or reorder source text.

## Findings and boundaries

### Approved output is the source boundary

The visual derivative pipeline consumes a content Artifact or canonical Post that has passed the existing editorial approval workflow. It must not use a raw Knowledge Unit as the card's final text source. Preserve exact text, punctuation, paragraph and line ordering. If text cannot fit, use an explicitly configured lossless sequence layout or return a clear overflow failure; never silently truncate.

### Reuse the platform

Use existing Product/ProductVersion and immutable component manifests, Recipe and capability registry, Output Contract, Policy/Identity/Prompt where appropriate, Artifact, private artifact storage, shared job/retry machinery, generic artifact review, and the canonical publishing workflow. Do not create a parallel card registry, object store, job queue, review engine, or scheduler. Add a durable model only if code evidence proves current models cannot represent the needed request and per-item outcomes.

The current inspected code indicates that production jobs primarily resolve Knowledge Units, generic Artifact review exists for non-POST outputs, and publication currently selects eligible Posts. Do not assume an IMAGE Artifact is automatically publishable. Add an explicit, tested boundary between approved text and its derivatives.

### Rendering choice

Do not require Playwright/Chromium in the production rendering path by default. Evaluate a lightweight SVG/image path (for example, SVG with a renderer that supports the required font shaping) against actual Arabic text fixtures. Selection must be evidence-based, not based on an assumed library speed claim.

The frontend may show a live template preview, but the saved PNG must come from the same rendering specification and be visually consistent with the preview. A browser preview alone is not the persisted image. Browser automation may still be used in CI for UI tests; the restriction is against making a full headless browser the routine server-side image renderer without measured justification.

Acceptance tests must cover Arabic joining and RTL, punctuation, diacritics, mixed Latin/Arabic, long text, font availability, exact output dimensions/MIME, clipping/overflow, and byte-level/source-text preservation. Pin fonts and relevant renderer dependencies. Fail clearly when required fonts or rendering dependencies are unavailable.

## Multi-source thematic composition

The composer should allow a user to select a theme and explicitly choose several Knowledge Units from one or more books. Retrieval can suggest candidates, but the selected source set must be visible and inspectable before generation. Each source's title, book, page/reference metadata and exact content must be supplied to the drafting layer.

The generated result must preserve traceability to all source units. Do not invent page numbers or attribute a claim to a source unless the stored source metadata supports it. Distinguish direct quotation from synthesis, and test unsupported attribution cases. The user remains the editorial judge; engineering validates provenance and structure, not literary beauty.

This is a separate production mode within the existing production engine, not a new standalone engine. Extend the drafter interface compatibly or introduce an explicit multi-source input contract only after inspecting its callers and tests. Do not change the existing single-unit path's semantics.

## Multi-format derivatives and review

A configured product may declare a bundle of derivatives from one approved text: canonical delivery text (including destination-specific formatting), image card(s), optional carousel, and optional audio/video packaging where the existing capabilities support it. Generate only configured outputs. Reuse existing providers, storage, artifacts, review and publishing interfaces.

Editorial approval authorizes the source text; it does not automatically mean every derivative is visually approved or published. Keep technical validation distinct from human visual review, but avoid unnecessary duplicated clicks: present the text and derivative preview together where the existing UI can support it, and allow one review action to cover only the clearly identified objects the reviewer is approving. Never send anything to Telegram or another external destination as part of tests.

## Product controls

Variable design decisions belong in versioned product/component configuration, not hard-coded prompt strings or arbitrary frontend defaults. Controls should include at least: format/output dimensions, template/style, typography/font, text alignment/direction, spacing, source/attribution display, overflow policy, sequence/card limits, and which derivatives to create. Pin the effective settings and component versions to each generated Artifact. Code owns security, validation, rendering correctness and lifecycle invariants.

## Prioritized implementation sequence

| Stage | Deliverable | Evidence required | Status |
|---|---|---|---|
| 0 | Verify current main, call paths, model contracts, existing tests, dependency/runtime constraints | GitHub source and CI evidence | Inspected in part; continue verification |
| 1 | Multi-source input contract in the existing production engine | Backward-compatibility tests; selected units and provenance retained | Implemented; current-head CI passed (backend, frontend, Playwright) on `28879ffd41e37d9bf4aa62fb17b58f18eb2f3c10` |
| 2 | Thematic composition using multiple explicit Knowledge Units | Explicit multi-book selection, one durable production job item, pinned product prompt/contract, all-source provenance metadata, idempotent Artifact reuse, generic review boundary | Backend capability and workspace/API wiring implemented; current-head CI and browser E2E passed. Production deployment and real Artifact review remain unverified. |
| 3 | Lightweight deterministic renderer proof | CI fixtures for Arabic/RTL and measured runtime/resource behavior in the target environment | Renderer fixtures and overflow checks pass in CI; runtime/resource benchmark and Arabic font/RAQM verification in the production container remain pending. |
| 4 | Versioned visual product/template configuration and pinned provenance | API/schema tests; old products and artifacts unchanged | Recipe-level visual settings, provenance metadata, and Control Plane capability configuration are implemented and CI-tested; production verification remains pending. |
| 5 | Approved-output library selection and derivatives from approved text only | Tests reject raw/unapproved inputs and preserve exact source text | Approved TEXT Artifact → separate PNG derivative is implemented and integration-tested; broader reusable approved-output library selection remains pending. |
| 6 | Configurable multi-format bundle / carousel with per-item results | Tests for partial failures, idempotency, retries, and intentional variants | Pending |
| 7 | Preview and human review of the actual stored image | UI/browser checks show the exact persisted image; review remains distinct from editorial approval | Pending |
| 8 | Safe handoff to existing publication workflow | Integration tests; no parallel scheduler; no external publish during tests | Pending |
| 9 | Full CI and regression review | Required checks green; failures repaired rather than bypassed | Pending |
| 10 | Railway deployment and safe end-to-end proof | Correct commit deployed; real stored Artifact reviewed; no external publication | Pending |

## Non-negotiable invariants

- Never rewrite approved text during visual rendering.
- Never use an image-generation model to render the card's actual Arabic text.
- Never truncate text silently or claim lossless splitting without tests.
- Never infer literary quality with an automated LLM judge; human editorial judgment remains human.
- Never equate editorial approval, visual approval, and publication.
- Never claim renderer performance, CI success, or Railway behavior without direct evidence.
- Never run external Telegram publication as a test.
- Do not stop at this document: implement, test, open a reviewable PR, fix CI failures, and continue through the verified deployment path.


## Implementation update — deterministic card capability

The current branch now adds a bounded `render_approved_text_card v1` recipe capability to the existing production engine. Its request names a source Artifact ID, and the API and capability independently enforce that the source is an available, human-approved inline TEXT Artifact whose Knowledge Unit matches the job's lineage anchor. It rejects raw Knowledge Units as card text. The output is a separate storage-backed `image/png` Artifact with the source Artifact ID, source-text SHA-256, renderer version, and effective render configuration recorded in metadata. The generic Artifact review flow remains the review boundary for the image.

The renderer uses Pillow with RAQM layout for Arabic shaping and requires a configured Arabic-capable font. It is deliberately fail-closed: if RAQM or the font is unavailable, generation fails; if the text does not fit, it fails without truncating the text. Product recipe configuration controls canvas size, padding, colors, font family (default, Naskh, or sans), body alignment, optional title and source-attribution display, their typography sizes, line spacing, and line-count ceiling. Attribution is composed only from stored source title/reference/page metadata; thematic outputs retain every stored source in the attribution list, missing references are not invented, and an attribution that cannot fit causes an explicit overflow failure rather than silently omitting sources. Font-family choices resolve through the matching `NASHR_CARD_FONT_PATH`, `NASHR_CARD_FONT_NASKH_PATH`, or `NASHR_CARD_FONT_SANS_PATH` setting, with common system font paths used only as a fallback. This first version is a single-card layout, not yet a lossless multi-card sequence renderer.

**Deployment prerequisite:** set `NASHR_CARD_FONT_PATH` to a licensed Arabic font file available in the production container, and verify Pillow's RAQM support in that exact runtime before enabling the card product. A green CI run alone does not prove production font availability or correct glyph shaping. Do not publish a card product as operational until the deployment prerequisite and a real visual review are verified.

The review panel exposes card creation only for approved TEXT Artifacts and only when a published product has an active recipe containing `render_approved_text_card v1`. The request goes through the durable production-job API and the product's pinned image output contract; no new job queue or review system is introduced.


### Example recipe contract for an operator-created card product

This is a configuration example, not a seeded product and not a production-readiness claim. Publish it only after selecting the product's other required pinned components and a compatible IMAGE output contract.

```json
{
  "key": "ARABIC_APPROVED_TEXT_CARD",
  "stages": [
    {
      "key": "render-card",
      "capability_key": "render_approved_text_card",
      "capability_version": 1,
      "configuration": {
        "width": 1080,
        "height": 1350,
        "padding": 88,
        "background": "#F7F2E8",
        "foreground": "#24211D",
        "font_family": "naskh",
        "font_size": 42,
        "line_spacing": 18,
        "max_lines": 22,
        "show_title": true,
        "show_source_attribution": true,
        "title_font_size": 34,
        "attribution_font_size": 22,
        "text_alignment": "right"
      }
    }
  ]
}
```

The matching output contract must declare `artifact_kind=IMAGE`, `mime_type=image/png`, and `content_mode=STORAGE_URI`. The card button is offered only after the source TEXT Artifact is human-approved. The resulting IMAGE Artifact starts in its own DRAFT review state; approving the text does not approve the image.


## Follow-up implementation record — 2026-10-17

- The renderer now resolves the bundled Noto Naskh Arabic font before host-specific fallback paths, and the font is packaged with the Python application under the SIL Open Font License 1.1. This removes the prior dependency on a font being incidentally installed in the Railpack image.
- Renderer provenance now records the resolved font family, file name and SHA-256, the renderer version, deterministic solid-background mode, and the absence of an AI asset. The approved TEXT Artifact remains the exact text source; no image model is used for typesetting.
- A published product/version is seeded through migration 0048 with a pinned recipe, IMAGE_ARTIFACT output contract, policy, prompt, and identity manifest. The recipe configuration is the versioned design specification; no separate Template entity is introduced.
- This does not establish that the live Railway database has applied migration 0048 or that a production image has been generated and reviewed. Those are deployment/runtime acceptance gates, not inferred from CI.


## Design variants and optional backgrounds — 2026-10-17

- Migration 0049 adds three deterministic recipe/product configurations (quote, text with source, poetry/literary RTL) and one explicitly AI-assisted background product. They are versioned through existing Recipe and ProductVersion manifests; there is no separate Template registry.
- AI-assisted mode sends only the versioned visual background prompt to the existing Gemini/FAL image adapter. The approved text is never sent to the image generator and is typeset afterward by the deterministic Pillow/RAQM renderer.
- If background generation fails, the renderer falls back to the configured solid background and records the failure metadata. The approved text is still rendered and the IMAGE Artifact remains independently reviewable.
- These additions are covered by code and CI tests; they do not yet complete multi-card carousel or Publishing handoff.
