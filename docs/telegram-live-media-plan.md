# Specialized Telegram media follow-up

Verified current Bot API on2026-11-23: https://core.telegram.org/bots/api

- sendLivePhoto is available to bots. Requires a separately approved static photo and a motion video no longer than10seconds and no larger than10MB, uploaded as two multipart fields. Caption limit1024. The approved motion video caption becomes the review wrapper content and exact outgoing caption. Implement a dedicated review wrapper referencing immutable approved child snapshots, not a VIDEO alias. Do not support arbitrary file IDs, external URLs, destinations or method strings from metadata. Preview both assets. Revalidate at approval, activation and send. Record the one returned message ID. An uncertain response must not retry automatically.
- sendLocation accepts live_period60-86400seconds. Implement bounded finite live sessions only, no indefinite tracking. Initial point is a reviewable native draft, not device GPS. editMessageLiveLocation and stopMessageLiveLocation require exact original publication destination and message ID. Changes need a separate reviewable revision and a claimed operation ledger, with errors preserving uncertainty rather than retrying. Expose edit and stop controls linked to the actual published location. Synthetic test starts0,0, updates a nearby synthetic point, then stops. A finite live period provides a bounded fallback if stop fails.
- Tests: endpoint payload allowlists, coordinate/duration/type/size validation, revocation and snapshot mismatch, sent result identity, duplicate/concurrent operation prevention, private-channel actual send/update/stop, visual review distinction.
- Existing static location remains unchanged. No actual user location, paid broadcast, invoices, or spending.

## Verified outcome

PR178 was merged and deployed on 2026-11-23. A new synthetic Live Photo was accepted once. A synthetic live location with a 300-second period was accepted once, updated, and stopped on the same message before expiry. The start schedule and reviewed UPDATE/STOP operations completed. No real device location was used. Evidence is Bot API acceptance and the internal ledger, not a visual Telegram-client inspection.
