# Ready-content phase acceptance, 2026-11-24

This checkpoint covers originals, catalog organization, central approval, linked
platform copies, explicit distribution choices, preflight, Telegram draft plans
and execution history. It does not mean all social platforms can publish.

## Explicit organization

The bank now stores a catalog title, series and category in a separate table.
These labels do not change original text, metadata, approval, source fingerprint,
platform-copy text, destination selection or schedule times. The catalog title is
never silently copied into a platform publishing title. Explicit series labels
win over filename inference, and labels are searchable and filterable.

Single-material editing allows all three labels. Batch editing, up to100 items,
allows only explicitly chosen series/category fields; an unchecked field stays
unchanged and an explicitly selected empty field clears only the stored label.
No shared batch title overwrites distinct material titles. Updates require the
current version of every item and are atomic on a conflict or missing material.
Catalog selection is separate from publishing selection and works on draft,
approved and rejected originals. Platform variants and legacy Posts are excluded.
No existing imported material is automatically reclassified by deployment.

## Acceptance checklist

- Import/manual entry preserves the original and provenance.
- Browse/search/filter the bank; organize individual originals or a batch.
- Approve the original once; automatically prepare linked platform-copy records.
- Retain editable copies and original fallback without silent length trimming.
- Select or exclude platforms per material/batch, with individual exceptions.
- Show field, media, account and execution checks as separate states.
- For Telegram, choose channels explicitly, preview each, save DRAFT plans and
  activate separately. Pin channel/bot/copy/source identities and keep outcomes.
- Preserve existing originals, approvals, publication IDs and schedule times.

## Still unfinished, not account-only blockers

- Semantic title/hook/description/SEO suggestions are not implemented. Current
  defaults are unchanged originals and rules, not an AI adaptation engine.
- Instagram has owner-driven OAuth code and encrypted settings, but no real
  connected account yet, no publishing adapter and no background token renewal.
- YouTube, Facebook and X lack execution connectors and account setup flows.
- TikTok remains paused by the owner.
- Analytics and full campaign workflow remain later work. Series labels are
  organization, not a campaign scheduler or performance model.

## Independent next work versus external setup

An Instagram adapter can be built and synthetic-provider tested without an
account: durable container/publish states, media delivery, per-target safety,
status recovery, expiry handling and clear no-account blockers. Real acceptance
still needs the owner's authorized Meta app/configuration, selected professional
account, required permissions and explicit publishing authority. An OAuth token
must not be assumed refreshable: verify the chosen Meta login/token type first.

An optional adaptation pipeline can be built against the existing provider port
with fake tests and strict unchanged-original fallback. A configured key does not
prove provider availability, free usage or spend authority. Do not activate paid
calls just to claim this checklist complete. No new subscription or generation
cost is part of this phase.
