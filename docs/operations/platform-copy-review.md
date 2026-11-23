# Independent platform copy review

A platform variant is a separate review Artifact. Derivation reuses an existing DRAFT without refreshing its text or metadata, preserving saved editorial changes. The source row is locked during lookup/creation so simultaneous requests do not create duplicate drafts for the same source/platform. An approved variant remains immutable; a later derivation may create a new review draft, never overwrite the approved one.

TEXT copies edit their own content. Stored media copies edit metadata.caption while retaining the same stored media reference. The bank exposes a dedicated caption editor and a length counter labelled with its measure. Saving recomputes measured length; approval revalidates the text against the platform profile. Unsaved text blocks the review button. An approved copy clears its needs_review flag.

Source identity, platform, profile and constraint provenance are immutable through the generic edit endpoint. No source artifact, imported original, editorial instruction, schedule, destination or live publication is changed by preparing or editing a copy. Platform profiles remain preparation-only and retain their existing provenance caveats. These changes do not connect a platform or enable public publishing.

Checks cover saved text/media edits surviving derivation, independent approval, original preservation, overlength/empty text, provenance tampering, concurrent creation and desktop/mobile caption editing. They use synthetic local data, with no new external message sends.
