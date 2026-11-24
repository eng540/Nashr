# Page-linked Instagram Login development, 2026-11-24

Owner app currently exposes Unified and Facebook Login setup. Direct Instagram Login was not shown in observed UI. Existing Nashr implementation is Unified Business Integration System User, not Page-linked User token. Never silently switch existing connections or claim changing a config ID changes token types.

Official sources checked:
- https://developers.facebook.com/docs/instagram-platform/instagram-api-with-facebook-login/get-started : professional Instagram linked to a Page; User token requests pages_show_list/instagram_basic for discovery, /me/accounts Pages and tasks, then linked instagram_business_account. Choose intended account, not first result.
- https://developers.facebook.com/docs/instagram-platform/content-publishing/ : Page route publishing instagram_basic/instagram_content_publish/pages_read_engagement; Business Manager-assigned roles may require ads scopes. This module never adds ads, messages or new scopes automatically.
- https://developers.facebook.com/docs/pages-api/getting-started/ : Page tokens and tasks supplied by /me/accounts. Its broader Page management permission examples are not an Instagram-only permission checklist.
- https://developers.facebook.com/docs/facebook-login/guides/access-tokens/get-long-lived/ : explicit long-lived User/Page token exchange, generally about60days, not perpetual validity.

Implementation first stage: dormant read-only User-token discovery and selected Page/linked account check. Token type/app ID/scopes/expiry are fenced. Viewing or advertising tasks alone cannot prove content creation. Never follow arbitrary paging URLs or select first candidate. Candidate repr/public payload excludes Page token. No production call/import yet.

Remaining: explicit reviewed login mode and type-safe encrypted per-candidate token persistence, state/session replay checks unchanged, Page identity on connection, fresh capability checks preserving expiry, owner-readable configuration/selection UI. Existing Unified connections must keep their mode, config fingerprint and verification flow. New mode selection must be explicit; no migration of secret/token or external account permission is implied by deployment. Live owner account permission and acceptance remain unverified.

## Completed separate lifecycle

Implemented explicit encrypted `instagram_page` app settings, separate flow/connection tables, ten-minute browser/session/config-bound one-time state, encrypted candidate User/Page tokens, explicit paired Page/Instagram selection and fresh User-task/link plus Page-token identity verification. Config changes invalidate only this mode. Verification never enables a disabled connection. Local enable requires a successful check within five minutes. Disconnect is local only. No publishing executor or scheduler is connected to this login mode.

Existing Unified tables, token records and configuration fingerprints are unchanged. Both journeys remain visible and separately named. No fallback from missing Page configuration to environment/Unified configuration.

Validation: 831 backend tests passed, one skipped; seven frontend unit tests; frontend production build; 62 browser tests across four shards. Initial repeated shard used stale fixed-name Control Plane fixtures, then passed on a newly migrated empty database. Migration 72 downgrade/upgrade checked. Desktop and 390px mobile rendered panels visually inspected with synthetic identities only. No live Meta OAuth/permission call or social post executed. Real Meta app permission availability and token-type acceptance are still unverified. Owner-side Instagram/Page linking is a prerequisite, not consent for Nashr OAuth or publishing.
