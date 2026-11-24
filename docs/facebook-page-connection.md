# Facebook Page connection only

Separate settings key facebook_page, OAuth cookie/state, encrypted pending flow and selected Page tables. Existing Instagram app configurations and connections are never read as a fallback or changed. No publishing, upload, refresh, scheduler or media exposure hook.

## Configuration and owner flow

Use the existing Meta app with a separate Facebook Login for Business configuration. Three permissions: pages_show_list, pages_read_engagement, pages_manage_posts. Owner chooses actual USER or SYSTEM_USER token mode, reviewed against Meta configuration. Callback is /api/connections/facebook/callback on the authenticated Nashr HTTPS origin. Enter app secret only in the write-only settings form, never chat. Authorization must start on Nashr in the same browser. Owner reviews Meta assets and selects the exact Page after returning. No first-item auto-selection.

Provider GETs verify token validity, actual type, app, three scopes, expiry bounds, SYSTEM_USER client_business_id, and /me/accounts fields id,name,tasks,access_token. Require explicit CREATE_CONTENT task, do not substitute MODERATE or MANAGE. Reject partial pagination instead of silently using a partial list. Pending tokens stay encrypted server-side; public candidate list never carries tokens. Before saving or verifying: rediscover selected Page/tasks from source token, debug Page token and assert its /me identity. No implicit token replacement. Null expiration is not a durability guarantee.

Empty or ineligible response is a diagnostic, not proof that the user failed to select an asset. Inspect current token type/scopes/access and returned Page/tasks before asking to relogin. Real BISU behavior remains empirical until account flow is completed. Standard access, app role and configuration availability must be checked on the actual Meta app; do not promise review exemption.

## Sources inspected 2026-11-24

- https://developers.facebook.com/docs/marketing-api/system-users/guides/api-calls/ documents system-user /me/accounts returning Page access_token, tasks and id.
- https://developers.facebook.com/documentation/facebook-login/facebook-login-for-business documents BISU permissions, asset delegation and client_business_id.
- https://developers.facebook.com/docs/permissions/
- https://developers.facebook.com/docs/video-api/guides/reels-publishing/

Connection is not publication approval. Other execution modules remain dormant and unconnected to this lifecycle.
