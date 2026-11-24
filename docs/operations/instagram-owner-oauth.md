# Owner-driven Instagram connection

2026-11-24. Unified Login connection lifecycle only. No personal sign-in, password collection, media upload, publishing adapter, account conversion or schedule changes.

## State and limits

The accounts dashboard shows missing setup honestly and disables the Meta action. No authorization URL is generated without configuration, owner authentication, a reviewed configuration flag and a valid dedicated Fernet key. The registered HTTPS callback must end in `/api/connections/instagram/callback`. This is a single-owner deployment integration, not a multi-tenant account model.

An explicit POST from the same origin starts a 10-minute one-use random state, stored only by hash and bound to the existing signed Nashr session and a separate HttpOnly Secure SameSite=Lax browser cookie. State consumption is atomic before the remote exchange. The callback strips query strings before access logging and returns only fixed errors or a clean redirect. Tokens and upstream errors are never returned to the browser. Callback cancellation, expiry, replay, configuration change, different session and partial failure preserve the old connection.

The server exchanges the code using fixed Meta endpoints, verifies token validity, exact app ID and `instagram_basic` plus `instagram_content_publish`, then reads the assigned Instagram accounts. The user must choose one explicitly, even if only one is returned. Selection saves a Fernet-encrypted token and the chosen account, scopes and recorded expiry. The old connection is unchanged until selection. Concurrency locks prevent disconnect from being undone by a late callback. Pending expired credentials are removed on the next start; local disconnect removes all pending credentials and the saved connection.

Connection status means checked at connection time, not continuous provider verification. Expiry or configuration changes require reconnect. There is no background token refresh in this release. Unified Login token expiry depends on the actual Meta configuration, so no Instagram Login 60-day refresh assumption is applied. Local disconnect deletes credentials from Nashr only and explicitly does not claim remote revocation. The owner can remove the app in Meta's settings. No paid or public test is required to deploy the unconfigured UI.

## External setup, not performed by this change

An owner-authorized Meta app with the Instagram use case, business portfolio and Facebook Login for Business configuration; professional Instagram account and app role for Standard Access tests; exact HTTPS redirect registration; HTTPS webhook endpoint/configuration as Meta requires; privacy/data deletion and review requirements appropriate to actual use. No claim these assets exist or their review is complete.

The dashboard now stores app settings encrypted. Legacy environment configuration remains a fallback only when no saved settings exist: `META_APP_ID`, `META_APP_SECRET`, `META_INSTAGRAM_CONFIG_ID`, `META_INSTAGRAM_REDIRECT_URI`, `NASHR_CONNECTION_ENCRYPTION_KEY`, existing `NASHR_AUTH_PASSWORD`, and `META_INSTAGRAM_CONFIG_REVIEWED=true` only after inspecting the actual assets and permission list. Keep secrets outside source control and frontend code. The configuration flag is not a substitute for Meta acceptance. Do not request extra ads, comments or messaging rights without explaining the actual Meta-required configuration and obtaining the owner's decision. The default configuration in Meta may include more permissions than publishing needs.

The supported start URL is constructed from the actual IDs and registered callback, not a pasted provider URL. No placeholder account or inferred identity is stored. After real setup, the owner opens the button on their own device and approves at Meta. They never share an Instagram password with Nashr or the assistant.

## Validation

Local mocked-provider tests cover missing/invalid configuration, no fake URL, owner/origin/session checks, one-use/expired/cancelled state, configuration changes, token app/scope validation, fixed hosts, encrypted storage, explicit selection, replay, concurrent callbacks and disconnect during exchange. Browser tests cover unconfigured state, disabled action, mobile pixels, explicit account selection and local deletion. No live Meta OAuth acceptance has been performed.

Official sources read:
- https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-unified-login/get-started
- https://developers.facebook.com/documentation/instagram-platform/overview/
- https://developers.facebook.com/docs/graph-api/reference/debug_token/
- https://developers.facebook.com/documentation/instagram-platform/content-publishing
