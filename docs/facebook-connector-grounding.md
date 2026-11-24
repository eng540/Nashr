# Facebook Page integration,24November2026

The next safe development stage is a dormant text/photo edge with synthetic tests, followed by a durable claim/result lifecycle and private review journey. Real connection and publication remain gated. Direct binary photo upload avoids exposing preview media by URL, but discloses to Meta only under a later explicit publication decision.

|Stage|Implemented|Open|
|---|---|---|
|Text/photo HTTP edge|SelectedPage identity, exact copy, explicit Page audience, private multipart bytes, known-ID readback|Durable claims, token lifecycle, owner Page/tasks selector|
|Video/Reels|Official contract research only|Durable session/offset/processing/finish implementation|
|Account setup|Owner handles Meta with main|No agent account/app/scope action|

Sources are in sources.md. Conflicts: Page photo4MB versus generic10MB, scheduled posts30days versus75days, different reference versions. Conservative local photo cap and no remote scheduling avoid relying on the unresolved wider interpretation. Mock tests prove local contracts only, not actual Meta acceptance or account readiness.

## Official sources
https://developers.facebook.com/docs/pages-api/posts/
https://developers.facebook.com/docs/graph-api/reference/page/feed/
https://developers.facebook.com/docs/graph-api/reference/page/photos/
https://developers.facebook.com/docs/graph-api/reference/photo/
https://developers.facebook.com/docs/graph-api/reference/user/accounts/
https://developers.facebook.com/docs/graph-api/reference/page/published_posts/
https://developers.facebook.com/docs/video-api/guides/reels-publishing/
https://developers.facebook.com/docs/graph-api/reference/page/video_reels/

## Dormant lifecycle, migration70
- `facebook_execution` is not imported by routes or scheduler. It pins approved original, exact saved Page message, Page, version and original private byte digest/count, not an approval grant.
- A write requires caller assertions for verified prerequisites, rights, explicit public Page audience and owner authority. These flags are not an authenticated permission system. Live use remains disabled until authenticated account/permission/task checks, inspections, private pinned storage and explicit review/approval are implemented together.
- Commit SENDING before the effect; concurrent claims serialize. Unknown responses and interrupted claims never automatically resubmit. A known provider post ID permits readback only, with exact Page/message/publication status, returning only provider-supplied supported permalinks.
- No fabricated destination URL, no feed scanning to guess identity and no cancellation claim after an external attempt. Operator recovery needs evidence that the worker stopped plus exact claim timestamp.
- Original JPEG/PNG or text only. Derived media, title, separate tags and alt text are blocked instead of silently omitted. No video/Reels, scheduling, polling, UI, OAuth or live acceptance yet.

## Private review, migration71
- Owner-authenticated same-origin preview/save/history/local cancellation is available for original text/photo only. It does not call the dormant executor, create a job or schedule, read media, connect Meta, grant access to private media, or record outgoing approval.
- Proposed numeric Page identity is explicitly unverified. Public Page audience and rights declarations are required for private saving. Missing provider/account or media-inspection blockers remain visible; a saved review is intentionally non-runnable.
- Exact current copy, source fingerprint, inspection evidence and review choices are hashed and rechecked under source/copy locks before save. Repeated identical saves reuse the active review. Source changes mark history stale; history remains readable even if the material changes to an unsupported kind.
- Checked locally:806 backend tests passed,1 skipped;7 frontend unit tests;61 browser tests across four shards; production frontend build; migration71 downgrade/upgrade; actual desktop/mobile screenshots inspected. No live Meta acceptance claimed.
