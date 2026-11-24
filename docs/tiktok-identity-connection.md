# TikTok Login Kit, identity only

This connector requests only `user.info.basic`. It cannot upload, publish, list videos,
create schedules, or authorize execution. Existing Instagram and Facebook connections
are separate and remain untouched.

Configure an existing TikTok developer app, Web Login Kit, its exact HTTPS callback
`/api/connections/tiktok/callback`, and the basic identity scope. App creation,
Individual/organization ownership, terms and app review remain separate decisions.
Sandbox requires the intended test user. Production eligibility is not guaranteed.
Store client key and client secret through the owner-only write-only settings form.

OAuth state is single-use, ten-minute, hashed, browser/session/config-bound. Callback
queries are removed before access logging. A callback prepares an encrypted candidate,
not a saved connection. Explicit choice plus a fresh provider identity read is needed
to save or replace a connection. Display name is not a verified @username.

Access and refresh tokens are encrypted together. Provider-returned expiry values are
used, never example durations. This first version intentionally does not refresh tokens:
when the access token expires, reconnect. It does not rotate or revoke remote tokens.
Local disconnect removes the local secret and pending flows only. TikTok permissions
can be revoked separately from TikTok. No background polling is added.

Tests use synthetic HTTP responses only. A test pass does not mean a real TikTok
account is connected; that requires configured credentials and completed consent.

Official references:
- https://developers.tiktok.com/docs/en/login-kit-web
- https://developers.tiktok.com/docs/en/tiktok-api-v2-get-user-info
- https://developers.tiktok.com/docs/en/oauth-get-a-user-access-token
- https://developers.tiktok.com/docs/en/oauth-refresh-a-user-access-token
- https://developers.tiktok.com/docs/en/add-a-sandbox
