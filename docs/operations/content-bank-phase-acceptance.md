# Ready-content phase acceptance, 2026-11-24

Historical checkpoint. The current platform-capability section below supersedes
its old connector status. It does not change any publication authority.

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

## Current platform capabilities, 2026-11-25

- Telegram supports explicit channel selection, reviewed drafts, schedules and
  execution history. A saved channel is not permission to publish every item.
- Instagram has separate official connection flows and review-gated execution
  with durable result recovery. A real publication was verified. This proves
  that one completed operation, not that any account is connected or authorized
  now. Read live connection/preflight and review the exact item/target.
- Facebook has a separate Page connection plus review-gated Reels execution,
  including delivery preparation, status recovery and a verified real result.
  Connecting a Page does not upload or publish. Other Facebook formats are not
  implied by Reels support.
- TikTok Login Kit implements identity-only connection with user.info.basic.
  Selected account, app acceptance and live consent must be checked separately.
  There is no implemented upload, video listing, direct post or auto-refresh.
- YouTube upload edges and review preparation have synthetic tests. No live
  connected-channel upload or scheduling acceptance has been demonstrated.
- X and Snapchat have no implemented execution connector in this app. This is
  an implementation statement, not a claim that their external APIs lack one.
- Current capability labels do not authorize execution, grant additional scopes,
  approve external terms or permit paid calls. Readiness, account connection,
  item approval and execution remain separate.

## Still unfinished

- Optional semantic suggestions and full campaign/analytics workflows need
  separate acceptance. Unchanged originals remain the default, not an AI rewrite.
- Live setup/eligibility for future connectors must be verified against current
  provider/account evidence, not inferred from these implementation notes.

## Independent next work versus external setup

New connector work can be built and synthetic-provider tested without an
account. Synthetic tests do not replace the authorized app/configuration,
selected account, required permissions and explicit publishing authority. An OAuth token
must not be assumed refreshable: verify the chosen Meta login/token type first.

An optional adaptation pipeline can be built against the existing provider port
with fake tests and strict unchanged-original fallback. A configured key does not
prove provider availability, free usage or spend authority. Do not activate paid
calls just to claim this checklist complete. No new subscription or generation
cost is part of this phase.

## Distribution follow-through, 2026-11-25

The read-only unified queue keeps unresolved failures visible. A later confirmed
publication supersedes an earlier failed publication only for the same original,
platform, exact destination, saved connection identity and identical content.
A different channel or changed copy does not clear the failure. Editorial target
records remain unique and an in-place confirmed retry naturally leaves FAILED.
A failed schedule item is treated as recovered only when its linked publication
confirms delivery for that same original. None of this retries or changes records.

The plan handoff prioritizes an unresolved failed plan, then an existing pending
or processing plan, then history. A newer cancelled plan cannot hide the relevant
active or failed plan. The link explains which case it represents. Published
status still requires an external identifier and never means every destination
has completed. Account, media and execution checks remain separate.
