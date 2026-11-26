# TikTok Sandbox draft consent, not a publishing implementation

Default off. Existing basic identity storage and exact-scope adapter are unchanged.
This feature only obtains and stores a separate encrypted grant for
`user.info.basic,video.upload`. It cannot send media, publish or refresh tokens.

## Grounded setup

The developer Sandbox product preview on 2026-11-26 showed Content Posting API
adds video.upload and enables Upload to TikTok by default. Direct Post is a
separate switch, deliberately left off. No Apply changes was submitted.

Sources:
- https://developers.tiktok.com/docs/en/add-a-sandbox
- https://developers.tiktok.com/doc/content-posting-api-get-started-upload-content/
- https://developers.tiktok.com/doc/content-posting-api-reference-upload-video

Sandbox is restricted, not approval for public videos. The normal upload guide
requires approved video.upload and the user's grant. A Sandbox grant alone is
not proof any transfer endpoint will accept an upload.

## Rollout steps, each distinct from media approval

1. Review and deploy this default-off code and migration 0081.
2. In the existing nashr-test Sandbox, add Content Posting API without Direct Post.
   Preserve existing callback and add the separate callback shown below. Save only
   these changes and verify the target account and video.upload scope.
3. Add the independent callback under Login Kit:
   `/api/connections/tiktok-inbox/callback`, on the same HTTPS origin as basic.
4. Set `NASHR_TIKTOK_INBOX_SANDBOX_REVIEWED=true` only after checking the actual
   product and callback. This is configuration review, not posting approval.
5. The user reviews the new permissions and follows TikTok consent. Explicitly
   select and save the same open_id as the existing basic identity. Different
   accounts are rejected; existing local identity data is never replaced.
6. Do not report drafts as working. No media endpoint exists. Any later experiment
   needs an approved exact original video and scope, a separate transfer design,
   source constraints and outcome tracking. Finishing a draft requires TikTok inbox.

Setting the flag off blocks new grants and selection. Local removal stays usable.
The flag is not a remote revocation. Neither local disconnect revokes TikTok.
No automatic refresh is included for either this grant or basic identity.
Provider-side token effects of authorizing another scope are unverified; do not
promise that an older token cannot be changed by TikTok itself.

## Isolation and safety

Separate callback, cookie path, tables, advisory lock and flow records. Owner auth,
CSRF origin checks, StrictBool review, session/browser/config/state/expiry binding,
one-use code exchange, encrypted pending tokens, explicit identity selection and
exact accepted scopes. video.publish is rejected. The basic lifecycle lock is
also taken before the final identity comparison and configuration recheck.
The scheduler only deletes expired temporary flows, never selected grants.
