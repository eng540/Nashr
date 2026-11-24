# Bounded temporary-file video inspection

2026-11-24. Read-only private preparation, no schedule or execution changes.

Videos now use a private temporary file, not a whole-object byte array. S3 reads are at most1MiB each, with declared and actual byte limits of300,000,000bytes, a full SHA-256 and a60second download deadline checked before and after each read. The response-body socket timeout is15seconds where the provider supports it. Connection setup uses the existing storage client's retry/timeout policy; the60seconds is not a hard wall-clock limit for setup or an individual blocked read. Two inspections at a time per process bound temporary disk use and worker count. Busy requests fail clearly rather than queue unbounded disk work.

The same worker owns download, inspection and cleanup. If its async caller is cancelled, the worker still reaches cleanup. The body closes and the temporary file unlinks on success, size overflow, malformed media or failed probe. No URI, source bytes or provider diagnostics are returned from this helper. No S3 writes happen.

MP4 structure uses a read-only memory map to skip payload boxes without copying the entire file. FFprobe remains bounded, and H.264 trace output retains its separate15second/8MiB limit. Reaching that header limit leaves GOP unverified, not invalid. VBR and HEVC GOP remain unverified. Images retain their existing50MiB path; existing Telegram execution and scheduling code are untouched.

After inspection the original fingerprint and platform-copy version are re-read, as before. A concurrent edit cannot be presented as a current measurement. Selected derivative bytes must match their recorded hash. Nothing becomes approved, scheduled or published through inspection.

Verification includes chunk/hash/privacy checks, declared/actual size overflow, cleanup after failed probe and cancellation, worker saturation, a real60MiB sparse MP4 container, API use of the streaming path with original/copy/schedules untouched, frontend video label and unchanged image save flow.

Source: https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media/ documents the300MB Reel input limit. This is a local inspection ceiling, not a guarantee of platform acceptance.
