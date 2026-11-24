# Accounts and connections dashboard

Open `/connections` after signing into Nashr. This page separates app administration, a user's account connection, and a publishing decision.

## Infrastructure key

Set one stable random Fernet key as `NASHR_CONNECTION_ENCRYPTION_KEY` through the deployment's secret settings. Never commit, return, log or display it. Back it up in the deployment's secret store. Losing or changing it makes stored credentials unreadable. Credentials fail closed, never fall back to a different bot. The dashboard remains read-only for new credentials until the key is available. `NASHR_AUTH_PASSWORD` must also be configured. The key is infrastructure, not a platform account setting.

## Telegram

Enter a label, bot token and channel ID or username in the dashboard. The token is write-only and Fernet-encrypted in the database. Verification calls only `getMe`, `getChat` and `getChatMember`. It requires a channel and a bot administrator with `can_post_messages`. It does not send a test message or change Telegram permissions. Status is the last saved check, not a continuous live guarantee.

Existing environment-based bot/channel configuration is left intact. Adding a managed channel does not make it the global default, reroute a legacy plan or authorize publishing. The same canonical channel cannot be added twice under alternate bot bindings.

From the approved content bank, select one or more originals and choose their intended channels explicitly. Preview results, publication history and blockers are separate for each target. Saving creates one DRAFT plan per selected channel atomically, including a single-item plan. Each plan pins channel, bot identity, content fingerprints and reviewed copy versions. Existing scheduling review/activation remains a separate decision. No automatic routing rules are inferred. Leaving all managed channels unchecked uses the explicitly labelled legacy path, not every channel.

A confirmed publication to one destination must not suppress another selected destination. Repeated publication to the same destination remains blocked. Publication records bind the connection used; direct retry and live-location operations use that bot, not the current environment default. Connections referenced by plans or publication records cannot be deleted. This conservative restriction includes completed plans, until safe archival is implemented. Local removal does not revoke a Telegram token or delete a channel. Token rotation/editing is not implemented in this version.

## Instagram

The dashboard accepts settings for an existing Meta app, with a write-only app secret stored encrypted. It does not create an app, accept external terms, convert an account or configure a business portfolio. Review the permissions in Facebook Login for Business first. The HTTPS redirect must match this Nashr site's callback path. Saving configuration invalidates pending handoffs and can mark a previous account as needing reconnect.

The account connection runs on the user's own device at Meta. It uses expiring, single-use, session/browser-bound state, verifies the issuing app and required scopes, then asks the user to select the returned account explicitly. This version stores one selected Instagram account. Tokens stay encrypted on the server. No Instagram publishing adapter, background refresh or remote revocation is claimed. See `instagram-owner-oauth.md` for protocol limitations and references.

Other platforms show unsupported or paused states honestly. No fake OAuth URL, developer account creation, spending or public social post is part of dashboard setup.

## Safety and validation

Connection endpoints require owner auth and same-origin mutation requests. Validation errors omit submitted credential values. Connection responses are no-store; standard HTTP diagnostics redact token URLs, access tokens, state and callback codes. Never enable external request-body/header capture for credential endpoints in a reverse proxy or tracing service.

Sources checked during development:
- https://core.telegram.org/bots/api
- https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-unified-login/get-started
- https://developers.facebook.com/docs/graph-api/reference/debug_token/
