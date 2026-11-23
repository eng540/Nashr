# Telegram support status

Technical validation is not editorial approval. All new drafts require Nashr approval. A readiness label imported from a source is never approval. Public publishing and paid features remain separate decisions.

|Content|Bank and draft support|Method|Notes|
|---|---|---|---|
|Text|Implemented|sendMessage|4096visible-character limit at send|
|Quiz|Implemented|sendPoll|Structured question/options/correct answer|
|Regular poll|Implemented via typed JSON|sendPoll|Anonymous regular poll|
|Image|Existing|sendPhoto|JPEG/PNG/WebP,10MiB|
|Video|Existing|sendVideo|MP4,50MiB|
|Document|Implemented|sendDocument|Any file as attachment,50MiB;never executed|
|Audio|Implemented|sendAudio|MP3/M4A,50MiB|
|Voice|Implemented|sendVoice|OpusOGG/MP3/M4A,50MiB|
|Animation|Implemented|sendAnimation|GIF or silentH264MP4,50MiB|
|Video note|Implemented|sendVideoNote|SquareH264MP4,<=60seconds,no caption|
|Sticker|Implemented|sendSticker|WEBP/TGS/WEBM with format constraints,no caption|
|Location/venue|Implemented via typed JSON|sendLocation/sendVenue|Static coordinates only|
|Contact|Implemented via typed JSON|sendContact|Explicit phone/name fields|
|Dice|Implemented via typed JSON|sendDice|Allowlisted emoji|
|Albums|Deployed; private-test Bot API acceptance verified|sendMediaGroup|2-10 approved images/videos, or audio only, or documents only; child approval and fingerprints rechecked|
|Live Photo|Deployed; private-test Bot API acceptance verified|sendLivePhoto|Approved static photo + approved H264MP4, max10seconds and10MiB motion, distinct review wrapper|
|Live location lifecycle|Deployed; private-test Bot API acceptance verified|sendLocation/editMessageLiveLocation/stopMessageLiveLocation|Finite60–86400second initial point; reviewable update/stop operations target original message, uncertainty blocks retry|
|Paid media/invoices|Out of current scope|sendPaidMedia/sendInvoice|Money requires separate authority|

## Verification recorded on 2026-11-23

- PR177 deployed the album workflow. One fresh synthetic two-photo album was accepted as two messages, with one completed schedule and one send attempt. The ledger retains every returned message ID.
- PR178 deployed Live Photo and finite live-location operations. A new synthetic photo/motion pair was accepted once. A synthetic live location was accepted once, then updated and stopped on the same message before expiry. Both reviewed operations completed, with no second location message and no device GPS use.
- The standalone text, quiz, poll, voice, audio, document, animation, video-note, sticker, location, venue, contact and dice test paths were accepted. Existing image/video tests were not repeated.
- Acceptance is grounded in Bot API responses and Nashr publication, schedule and operation ledgers. It is not a visual inspection of the messages inside Telegram. The in-app preview is an approximation, not a Telegram client render.
- Internal operational ledgers retain exact publication IDs, schedule IDs, message IDs, attempt counts and timestamps. Do not publish private destination identifiers or user content in this repository.

Unit/integration tests and CI alone do not establish external acceptance. For a future regression, use new synthetic media only when a new external test is necessary; do not resend a completed test just to refresh documentation. No public social publishing, paid media, invoices or new spending were part of these tests.

Source: https://core.telegram.org/bots/api , checked2026-11-23.
