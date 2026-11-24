# Eligibility correction,24November2026

The current official migration guide states newly created apps cannot configure
Instagram API with Instagram Login. Existing integrations continue working with
no announced end date. Older business-login/get-started pages still describe
setup without this restriction and are insufficient eligibility evidence.

https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/migration-guide

The Nashr app screen currently exposes Unified Login and Facebook Login, not
the legacy direct setup. Do not request new direct credentials or create a new
app as a workaround. Unified is a different token/host/permission flow and needs
its own source-grounded permission decision, including mandatory messaging.

The direct UI now warns it is legacy-only and requires an explicit eligibility
acknowledgment before configuration save or starting OAuth. Existing saved
connections and settings are preserved. No automatic migration or fallback.

# Instagram Login, independent connection

Reviewed 2026-11-24. This is distinct from Unified and Facebook Page login.

Official sources:
- https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/ : professional accounts; no linked Facebook Page required.
- https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/business-login/ : Instagram product app ID/secret, authorization code POST exchange, returned permissions and app-scoped user ID; server-side long-lived exchange; 60-day maximum, no Facebook app credential substitution.
- https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/get-started/ : graph.instagram.com/v27.0/me with id (app-scoped), user_id (professional account ID), username.
- https://developers.facebook.com/docs/graph-api/changelog/non-versioned-changes/nvc-2023 : September 15 User Accounts change requires business_management for business-linked Pages. Four Page scopes are not universally sufficient.
- https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/page/ : additional ad permissions can apply to Business Manager-granted Page roles.
- https://developers.facebook.com/docs/permissions/reference/business_management : business_management grants Business Manager read/write, not read-only access.

The direct route requests only instagram_business_basic and instagram_business_content_publish. It never uses a supplied token, Facebook Page enumeration, ad permissions, business permissions, arbitrary callback host, or secret-bearing frontend response. Identity verifies the code exchange app-scoped user ID against /me.id, and records the distinct professional /me.user_id for future publishing. It requires explicit account selection and rechecks identity before saving. State is session-bound, browser-bound, configuration-bound, ten-minute and single-use. Tokens/settings are encrypted at rest. Query strings are removed before access logging. Long-lived expiry must be positive and no more than 60 days. No automatic refresh is implemented.

No publishing route is activated. No media reads, external media grants, uploads, or publications occur. Existing Unified/Page settings, connections, schedules, media and publication history remain separate and unchanged.

Standard access applies to owned/managed professional accounts added in App Dashboard. Serving other accounts can require Advanced Access/App Review. Current setup in Meta must be verified before promising a working login. Instagram App ID/Secret are product-specific; never substitute the earlier Facebook app ID/secret.

## Dormant publishing edge

`InstagramDirectPublisher` uses `graph.instagram.com/v27.0`, reuses the
single-image/Reel limits and mutation-unknown handling, and overrides all
Facebook/Unified verification. No production route imports it. It cannot
create a media grant or publication authority. A future caller must supply an
explicitly authorized, pinned provider-readable media grant and load the
provenance-bound encrypted connection after checking its current configuration,
enabled state, token deadline and saved identity. Local scope/deadline checks
and a read-only `/me` identity check are not proof of continued permission on
all future provider requests. Provider permission/auth failures remain blockers.

Publishing requirements and hosts were checked against:
https://developers.facebook.com/docs/instagram-platform/content-publishing/

## Private execution ledger

Direct-login review snapshots use an explicit INSTAGRAM_LOGIN mode, no fallback.
A private execution draft pins review ID/hash, config hash, account ID/username,
source fingerprint, copy version, measured digest and inspection. Repeated stage
requests recover the existing draft. Staging never grants permission or creates
a media URL. Current source, connection and inspection are rechecked at staging;
changes invalidate the snapshot. Existing execution records retain an empty
connection_binding and their old behavior.

Direct-bound core calls additionally require explicit public-publication and
media-disclosure flags, the direct provider host, and unchanged enabled/fresh
connection provenance. These internal flags are safeguards, not user consent
records. No publish/media-exposure endpoint or scheduler runner is enabled.
The UI exposes only review, private staging, history and local cancellation.
