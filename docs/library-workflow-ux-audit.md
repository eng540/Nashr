# Library workflow UX audit

## Whole-journey findings

The bank rendered every editor, preview, preparation control and legacy action in
long two-column cards. One filtered record still occupied half the desktop width.
Opening many cards also requested preparation data for records the reader had not
chosen to work on. Selection and editing competed for attention.

The publishing ready list covers legacy Post records, not every approved generic
artifact. Saved generic Telegram plans had no direct handoff to their detail view,
and their detail view showed a disabled preview rather than a route to the original.
This made a valid bank-to-plan workflow look incomplete.

## Changes

- Compact browse is the default. Selection is independent of opening one record.
- One focused record uses the available desktop width. Closing restores selection.
- Approved original text has one read-only preview, not a disabled duplicate editor.
- Platform copies precede collapsed legacy tools. Technical metadata stays collapsed.
- A saved preview links directly to the draft plan. A plan links back to its original,
  copies and publication ledger. Publishing explains the legacy list boundary.
- Search, filter and pagination changes leave focus so they cannot hide other results.
- Existing expanded-card view remains available for operators and regression coverage.

## Material remaining gaps

This change does not claim a single unified queue across Post and generic Artifact
records. That requires a shared readiness contract, not relabeling a legacy count.
Bulk workflows remain capped at 100 with explicit remainder messaging. Non-Telegram
copies remain preparation-only until their account, connector, permissions and media
rules are verified. YouTube account selection affects only that connector.
Media measurement is not conversion or a complete cross-platform acceptance check.
A preview is not evidence of remote publication. Scheduling a draft is not executing it.

No migrations, original-content edits, approval changes, schedule changes or external
publication are needed to deploy this UI change.

## Verification

Frontend build and 42 browser cases passed locally against a dedicated database
where required, split across runs to stay within the runner timeout. Desktop and
390px mobile focused views were inspected. Dedicated tests cover selection retention,
full-width focus, no-write browsing and exact saved-plan links.
