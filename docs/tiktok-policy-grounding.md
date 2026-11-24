# TikTok capability boundary, reviewed 2026-11-24

This release adds a read-only requirements panel and pure offline assessment. It does not create an app, grant scopes, start OAuth, read/upload a media object, expose a media URL, publish, schedule, charge, or write a posting record. No environment switch enables live execution.

## Separate products

Inbox Upload requires app acceptance for `video.upload` plus user authorization. The user follows the TikTok inbox notification to finish editing and posting. Delivery to that inbox is not publication. Up to five pending shares in a 24-hour period is a platform ceiling, not reserved account capacity.

Direct Post uses `video.publish`. Current intended-use guidelines exclude internal utilities for accounts owned or managed by the developer or their team. Nashr's current private shape does not establish eligibility. Even accepted app/scope parameters in the pure assessment are only caller-supplied assumptions. They never become a verified grant or executable state. No account-privacy change is proposed as a workaround.

Fresh creator information and explicit privacy choices are required, with no preselected privacy. Unaudited Direct Post requires private creator accounts and SELF_ONLY. A permissive transport or accepted scope does not waive intended-use restrictions.

## Media and outcomes

The Direct Post guidelines say media already on app servers must use PULL_FROM_URL, not FILE_UPLOAD. The transfer guide requires verified ownership of the domain/URL prefix, HTTPS without redirection, and accessibility for the entire download (timeout one hour). The Inbox tutorial describes both transfers but does not settle whether every Direct Post intended-use rule applies to Inbox app review. We take the conservative server-media boundary here and do not promise approval of either product.

A later media-transfer design needs separate owner permission at the actual upload/publication decision. No private file is made accessible merely to test this UI.

SEND_TO_USER_INBOX means notification delivered. PUBLISH_COMPLETE means posted, including user-completed Inbox posts, not necessarily publicly viewable. Public IDs follow public moderation; an Inbox draft may produce multiple posts. No automatic retry after uncertain transmission is introduced.

## Official sources

- https://developers.tiktok.com/docs/en/content-sharing-guidelines
- https://developers.tiktok.com/docs/en/content-posting-api-reference-upload-video
- https://developers.tiktok.com/docs/en/content-posting-api-get-started-upload-content
- https://developers.tiktok.com/docs/en/content-posting-api-reference-direct-post
- https://developers.tiktok.com/docs/en/content-posting-api-reference-query-creator-info
- https://developers.tiktok.com/docs/en/content-posting-api-reference-get-video-status
- https://developers.tiktok.com/docs/en/content-posting-api-media-transfer-guide

Fetched live on 2026-11-24. Source dates: guidelines/media/upload/status August 4 2026; direct/creator October 27 2026. Only official API/policy sources were used because third-party workarounds cannot establish platform eligibility.

## Limits

The panel is not a binding or complete platform review, app submission, verified OAuth connection, real quota check or upload-capability test. Photos and video execution remain unavailable. External facts must be rechecked before any later effect. The assessment's all-inputs-present state is explicitly not executable.
