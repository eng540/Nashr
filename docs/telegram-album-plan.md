# Telegram albums implementation plan

Use an inline TEXT review wrapper with telegram_album metadata containing a bounded list of2-10 approved stored artifact IDs. No recipient or BotAPI method in user-controlled metadata. Existing approval separation is preserved; selecting source content never approves it.

- Validate IDs, uniqueness and grouping rules. Only IMAGE/VIDEO combinations, homogeneous AUDIO, or homogeneous DOCUMENT. LivePhoto is a separate currently unsupported type; do not silently call a video a live photo.
- At creation, approval, schedule activation and send: reload children, require AVAILABLE+APPROVED, supported MIME+private storage. At send pin a fingerprint of IDs/kinds/storage/captions so approved album cannot silently inherit changed child media.
- Send media through multipart attach:// fields with per-item current approved caption, max1024. No paid broadcast flag. Check total memory bound and each upload limit before reading bytes.
- Parse array result; persist all message IDs in a new ledger field, retain first external_id for compatibility. Return exact list on schedule/publication responses and record result details. An ambiguous result is not safely retryable.
- One album publication is one atomic claim. Repeated creation returns same wrapper by explicit idempotency token; repeated send or schedule must never resend published children as individual test items. Do not use already published photo2517/video2518 or current175fixtures in album tests; generate distinct tiny album fixtures once.
- UI: select approved eligible children, explicit create-album action distinct from batch individual drafts; review ordered list/captions with previews, draft, schedule, activate, result.
- Tests: allowed and rejected mixes,2/10bounds, revoked/changed child, filenames/MIME/size, multipart2items and parsedallIDs, no-paid-flags, concurrent claim/retry safety, current legacy tests, browser desktop/mobile.

Known follow-up UI issues from live175tests: quiz has immediate publish but lacks schedule and multi-select UI despite backend support; media schedule titles fall back to quiz, and list details stay stale after sends until reload; position rendered plus1 despite one-based model.
