# Production job prompt pinning

The Control Plane's currently published `editorial.drafter` version is the version selected for a newly created ProductionJob. The job stores the prompt key, version number, and exact prompt body in the same durable record as its lifecycle state. Every item, retry, resume, and stale-job recovery uses that stored body; child items do not resolve the active version again.

A draft version is not eligible for production. Publishing a new version affects jobs created after that publication becomes visible, not jobs already created.

Historical jobs created before prompt pinning have null snapshot fields. Unless independent reliable evidence identifies the prompt they used, their historical prompt version is unknown. The runner deliberately fails such a job with `PRODUCTION_PROMPT_UNPINNED` rather than attributing the current prompt to it or silently falling back.

This records three distinct facts:
- **Currently published version:** Control Plane state at the time it is inspected.
- **Job-pinned version:** the key, version number, and body recorded when the job was created.
- **Historically used version:** known only when reliable provenance was recorded; it must not be inferred for legacy jobs.
