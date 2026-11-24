# Unified execution

Uses the existing selected Unified System-user connection. It does not fall back to direct Instagram Login or Page login.

The owner first saves a private review and pinned execution draft. Proposal is a separate step with exact account, outgoing text, media SHA-256, Reel feed choice and due time. The approve action requires owner session, same-origin request, matching proposal hash and all three explicit confirmations. No existing material or connection is approved by deployment.

At due time a bounded worker verifies account/app/portfolio and pinned bytes before minting a fifteen-minute bearer media capability. The bearer query is stripped before access logging, stored only as a digest, not returned by owner status, and checked against current decision/source/connection on every read. The endpoint is unauthenticated only for holders of that capability, no source storage directory is exposed. Meta may retain its own copy. The owner can revoke remaining reads and pending execution, not undo a publication already accepted by Meta.

No automatic mutation retries after lost responses or interrupted claims. Such results remain reconciliation-only. Known media IDs are resolved to owner-checked Instagram permalinks. Expired decisions and changed source/copy/bytes/account/config/token generation block execution.

Only new explicitly confirmed decisions enter this runtime. Existing Telegram schedules and legacy Instagram connections remain unchanged. PR223's direct-only branch is not merged by this change.
