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
|Albums|Implemented, awaiting deployment and real delivery verification|sendMediaGroup|2-10 approved images/videos, or audio only, or documents only; child approval and fingerprints rechecked|
|Live Photo|Not implemented|sendLivePhoto|Separate specialized type, not a video alias|
|Live location lifecycle|Not implemented|sendLocation/editMessageLiveLocation|Requires stop/update workflow|
|Paid media/invoices|Out of current scope|sendPaidMedia/sendInvoice|Money requires separate authority|

Implementation and unit/integration verification do not establish actual private-channel delivery. Record each real test with publication id, schedule id, Telegram message id and time before marking it delivery-verified. Do not repeat existing photo2517/video2518tests.

Source: https://core.telegram.org/bots/api , checked2026-11-23.
