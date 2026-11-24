# YouTube connector, checked24November2026

## Implemented boundary
A dormant HTTP adapter supports selected-channel verification, resumable session initiation, one bounded chunk, session status reconciliation and video processing/privacy readback. It is not imported by a production route or scheduler. No Google app, consent grant, credentials, session URL or real video was created during development. MockTransport tests are synthetic only.

Every upload requires an explicit privacy value, made-for-kids declaration, synthetic-media declaration, category and caller authorization. There is no fallback to public, no hidden metadata trimming, no publishAt, no cost commitment and no network retry. A timeout at session initiation is unknown; there is no silent second POST. A timed-out chunk can be reconciled against the same session, rather than restarting a video. A308 response supplies the confirmed received offset and optional Retry-After. Expired sessions are reported, not restarted. Video identity must match the selected channel. A known video ID does not prove processing completed or public visibility.

Session URLs are capabilities. Only the documented HTTPS www.googleapis.com upload path is accepted, redirects are disabled, and upload_id is redacted from HTTP diagnostics. A dormant durable core encrypts the full session URL, pins byte digests and metadata, claims work before requests and serializes offset changes. Interrupted workers require explicit proof of termination, not age-based lease stealing. Provider delays are persisted without shortening and apply to reconciliation too. Processing readback is distinct from upload completion and checks the selected privacy. This does not constitute live publishing readiness.

## Current source facts
- videos.insert accepts video media up to256GB. Metadata/privacy must be explicit. The current docs say an omitted privacyStatus can default to public and unverified projects are no longer restricted to private. Never rely on the former2020 private-only policy.
- Current quota docs describe100 videos.insert calls per day in its own quota bucket. Verify the actual connected project quota before execution; do not translate quota into a currency price or promise no charges.
- YouTube title maximum100characters; description maximum5000UTF-8 bytes; tags maximum500characters including separators and quotes around phrases.
- Resumable initiation returns a Location capability. An empty PUT with Content-Range bytes */total checks a lost upload response;308 plus Range gives the accepted contiguous prefix. Non-final chunks must be multiples of256KiB.
- channels.list mine=true selects the authenticated owner's channels. Incomplete pagination or a missing chosen channel fails closed.
- OAuth web-server flow needs exact redirect matching, unguessable browser-bound state, review of granted scopes and encrypted tokens. youtube.upload does not by itself replace the read permission needed for selected-channel checks. No real OAuth scope request is implemented in this stage.

## Official sources
https://developers.google.com/youtube/data/reference/rest/v3/videos/insert
https://developers.google.com/youtube/data/reference/rest/v3/videos
https://developers.google.com/youtube/data/guides/using_resumable_upload_protocol
https://developers.google.com/youtube/data/reference/rest/v3/channels/list
https://developers.google.com/youtube/data/revision_history
https://developers.google.com/youtube/data/guides/quota_and_compliance_audits
https://developers.google.com/youtube/data/guides/auth/server-side-web-apps
https://developers.google.com/identity/protocols/oauth2/resources/best-practices

## Next acceptance gates
A production private-storage reader with inspected immutable bytes, bounded streaming and explicit owner channel/metadata/privacy/rights decision; own Google OAuth configuration and selection journey; live quota/permission verification; independently authorized real upload test and confirmed processing/visibility. None is satisfied by a passing mock test.
