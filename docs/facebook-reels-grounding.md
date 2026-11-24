# Dormant Facebook Reels transport, 2026-11-24

## Scope

Synthetic transport tests only. No public route, scheduler, connection, media storage read, account grant, live request, or new cost. Existing Page text/photo adapter remains unchanged. Ordinary Page video and Reels are not interchangeable.

Future orchestration must durably record owner approval for the exact public Page post and media disclosure, current Page identity and CREATE_CONTENT task, current grants, encrypted upload-session capability and exact inspected bytes. Boolean gates in this edge are a defense against accidental calls, not an authority resolver or evidence of the user's consent.

## Current official requirements

Reels publishing requires Page token, CREATE_CONTENT task and pages_show_list, pages_read_engagement, pages_manage_posts. Instagram's Page connection does not imply Facebook posting permission. A Page Reel has public audience; no private rehearsal is claimed.

The official Reel guide separates initialization, byte upload and final publishing. Binary upload directly to the returned rupload.facebook.com URL is supported. No private URL need be made accessible for this dormant local-byte path. Both upload-host paths shown by the guide (with and without version) are allowlisted, bound to the exact video ID. Redirects, ports, credentials, query strings and fragments are rejected. Tokens only appear in headers.

Before byte transfer this edge reads remote uploading_phase.bytes_transfered and compares it to an explicit caller offset. Missing/malformed/mismatched offsets block transfer. Interrupted POSTs and ambiguous results produce no automatic retry. A future caller must persist uncertainty and reconcile before any further send. Transfer success is not publication. Final success is not verified public availability. Even all phase statuses complete do not produce public-post verification here.

Conservative LOCAL limits: inspected MP4 up to50MB, title up to200 characters. They are not claimed as Meta maximums. Real ffprobe inspection, content-rights review and current specs remain separate and required before execution. The July30 2026 Reel guide currently lists9:16, minimum540x960,24-60fps,3-90seconds and public audience. Do not generalize these to all Page videos.

## Conflicts/uncertainty

The generic Pages posts guide lists broader permissions and legacy publish_video, whereas the dedicated Reel guide and Page Videos reference list the three granular Page permissions above. Use the dedicated operation's current requirements, not a union of all scopes. No live token/app review/role acceptance has been verified. Current sources show different sample API versions (v25/v26/v27); the edge requires an explicit version rather than guessing it.

The Reel guide's resume prose says upload_phase.bytes_transfered while its status example says uploading_phase.bytes_transfered. The parser uses the actual status example's uploading_phase, and rejects unknown shapes. Do not silently guess an offset. The guide includes collaboration flows, but none are implemented or authorized.

## Official sources fetched live

- https://developers.facebook.com/docs/video-api/guides/reels-publishing/ (updated July30 2026)
- https://developers.facebook.com/docs/video-api/guides/publishing/
- https://developers.facebook.com/docs/graph-api/reference/page/videos/
- https://developers.facebook.com/docs/graph-api/guides/upload/
- https://developers.facebook.com/docs/pages-api/posts/
- https://developers.facebook.com/docs/graph-api/reference/video/
- https://developers.facebook.com/docs/permissions/
- https://developers.facebook.com/docs/pages-api/getting-started/

No app was created, no extra permission requested, no Meta account modified and no actual video transferred during this work.
