# Ready-content phase acceptance, 2026-11-24

Historical checkpoint. The current platform-capability section below supersedes
its old connector status. It does not change any publication authority.

This checkpoint covers originals, catalog organization, central approval, linked
platform copies, explicit distribution choices, preflight, Telegram draft plans
and execution history. It does not mean all social platforms can publish.

## Explicit organization

The bank now stores a catalog title, series and category in a separate table.
These labels do not change original text, metadata, approval, source fingerprint,
platform-copy text, destination selection or schedule times. The catalog title is
never silently copied into a platform publishing title. Explicit series labels
win over filename inference, and labels are searchable and filterable.

Single-material editing allows all three labels. Batch editing, up to100 items,
allows only explicitly chosen series/category fields; an unchecked field stays
unchanged and an explicitly selected empty field clears only the stored label.
No shared batch title overwrites distinct material titles. Updates require the
current version of every item and are atomic on a conflict or missing material.
Catalog selection is separate from publishing selection and works on draft,
approved and rejected originals. Platform variants and legacy Posts are excluded.
No existing imported material is automatically reclassified by deployment.

## Acceptance checklist

- Import/manual entry preserves the original and provenance.
- Browse/search/filter the bank; organize individual originals or a batch.
- Approve the original once; automatically prepare linked platform-copy records.
- Retain editable copies and original fallback without silent length trimming.
- Select or exclude platforms per material/batch, with individual exceptions.
- Show field, media, account and execution checks as separate states.
- For Telegram, choose channels explicitly, preview each, save DRAFT plans and
  activate separately. Pin channel/bot/copy/source identities and keep outcomes.
- Preserve existing originals, approvals, publication IDs and schedule times.

## Current platform capabilities, 2026-11-25

- Telegram supports explicit channel selection, reviewed drafts, schedules and
  execution history. A saved channel is not permission to publish every item.
- Instagram has separate official connection flows and review-gated execution
  with durable result recovery. A real publication was verified. This proves
  that one completed operation, not that any account is connected or authorized
  now. Read live connection/preflight and review the exact item/target.
- Facebook has a separate Page connection plus review-gated Reels execution,
  including delivery preparation, status recovery and a verified real result.
  Connecting a Page does not upload or publish. Other Facebook formats are not
  implied by Reels support.
- TikTok Login Kit implements identity-only connection with user.info.basic.
  Selected account, app acceptance and live consent must be checked separately.
  There is no implemented upload, video listing, direct post or auto-refresh.
- YouTube upload edges and review preparation have synthetic tests. No live
  connected-channel upload or scheduling acceptance has been demonstrated.
- X and Snapchat have no implemented execution connector in this app. This is
  an implementation statement, not a claim that their external APIs lack one.
- Current capability labels do not authorize execution, grant additional scopes,
  approve external terms or permit paid calls. Readiness, account connection,
  item approval and execution remain separate.

## Still unfinished

- Optional semantic suggestions and full campaign/analytics workflows need
  separate acceptance. Unchanged originals remain the default, not an AI rewrite.
- Live setup/eligibility for future connectors must be verified against current
  provider/account evidence, not inferred from these implementation notes.

## Independent next work versus external setup

New connector work can be built and synthetic-provider tested without an
account. Synthetic tests do not replace the authorized app/configuration,
selected account, required permissions and explicit publishing authority. An OAuth token
must not be assumed refreshable: verify the chosen Meta login/token type first.

An optional adaptation pipeline can be built against the existing provider port
with fake tests and strict unchanged-original fallback. A configured key does not
prove provider availability, free usage or spend authority. Do not activate paid
calls just to claim this checklist complete. No new subscription or generation
cost is part of this phase.

## Distribution follow-through, 2026-11-25

The read-only unified queue keeps unresolved failures visible. A later confirmed
publication supersedes an earlier failed publication only for the same original,
platform, exact destination, saved connection identity and identical content.
A different channel or changed copy does not clear the failure. Editorial target
records remain unique and an in-place confirmed retry naturally leaves FAILED.
A failed schedule item is treated as recovered only when its linked publication
confirms delivery for that same original. None of this retries or changes records.

The plan handoff prioritizes an unresolved failed plan, then an existing pending
or processing plan, then history. A newer cancelled plan cannot hide the relevant
active or failed plan. The link explains which case it represents. Published
status still requires an external identifier and never means every destination
has completed. Account, media and execution checks remain separate.

## Organized distribution list, 2026-11-25

The publishing queue displays the saved catalog title before import/source titles,
without copying that label into publication text. Search includes saved series and
category labels. Exact series/category filters and an explicit platform-choice
filter narrow the read-only operations list. The no-destinations filter includes
original artifacts with no saved selection or an explicitly empty one. Editorial
legacy posts are excluded from platform-choice filters because they do not store
central artifact choices. Stale choices remain visible and flagged; filtering by
a platform is never evidence of media/account readiness or execution authority.
No existing catalog, original, choice, approval or schedule is changed.

## Historical per-platform results, 2026-11-25

Each unified-queue original now shows publication evidence grouped by platform.
Confirmed destination/account pairs are counted once, even across repeated sends.
Only records with a published status and external identifier count. Unresolved
failed attempts use the same target/account/content recovery rule as overall
attention status. Saved platforms lacking any confirmed historical result are
listed separately. This is history, not delivery of the current copy, completion
of all selected destinations, connection readiness or permission to retry.
No content, choices, plans or publication records are changed by reading it.

## Connector result history, 2026-11-25

The read-only artifact ledger also includes scoped Instagram Unified and Facebook
Reel execution records. Drafts, cancelled jobs, unbound synthetic Instagram jobs
and the dormant Facebook text/photo table are excluded. Exact-decision provenance
is required. Confirmed results need a published lifecycle state, numeric external
ID and an expected-platform result URL. Nonconfirmed links are never rendered.
No raw snapshots, token hashes, media grants or approval evidence references are
returned. Connector results remain a separate record scope rather than being
copied into PublicationModel or added to its deduplicated target counts.

The queue recognizes confirmed connector history and flags nonconfirmed started
operations for review, not retry. A selected platform with connector confirmation
is no longer described as lacking all historical evidence. Earlier uncertain
jobs are not silently cleared by another job. Historical results still do not
prove current-copy delivery, all-destination completion or live account readiness.

## Calendar wall-clock safety, 2026-11-25

The scheduling UI rejects invalid calendar values, nonexistent DST times and
repeated clock hours rather than silently choosing a different instant. Existing
stored UTC timestamps and schedule zones are not rewritten. The daily calendar
starts on the date in its displayed zone, lets the operator choose another valid
IANA display zone and formats each daily item in that same zone. Upcoming items
still show their saved plan zone. A view-only zone change never edits a plan.

## Elapsed-minute scheduling review

New editorial schedule generation now uses elapsed UTC minutes, avoiding repeated/reversed instants at DST boundaries. The creation form lists every selected item in selection order, its local date/time and explicit zone plus UTC instant before saving. Saving remains DRAFT, not activation. Invalid/non-integer intervals or invalid/ambiguous start times block saving. Existing schedules are not recalculated. Proof: fresh PostgreSQL suite1044passed1skipped;15frontend tests/typecheck/build; isolated calendar and schedule-preview browser tests. No production schedule creation or publication used for acceptance.

## Coherent workspace journey, first acceptance batch

Root opens bank; old console entry opens book analysis within common shell. Read-only GET analysis tool remains reachable, discovery still requires its explicit start control. PDF lists use stored MIME, never filename guesses; other originals remain accessible behind an explicit source toggle. Upload wording no longer promises automatic analysis. Review decision precedes destination selection, with working stage anchors and visible approve-first explanation, no approval bypass. Calendar initial display follows browser zone, leaving new-plan default and persisted plans unchanged. Selected plan scrolls into view and status is localized. Tests cover Sources → review → destination requirements → publishing, zero writes, plus selected plan visibility, calendar, editorial notes and schedule preview. This is not a claim of full platform/UX completion.

## Workspace progress and human plan summaries

Read-only progress counts original available non-POST materials separately from editorial posts and platform copies. Counts are saved state, never readiness or permission; unreviewed originals remain explicit, failed requests do not become zero. Plan cards show up to three saved item titles and types, Telegram plan route and saved destination where present, keeping original plan names and all history. No title-based synthetic classification. Latest fifty-plan scope remains explicit. Isolated checks cover failed summary/calendar reads, 100-item bulk selection boundary, and media platform-copy unsaved approval gate without live mutation. Source EXTRACTED status translated. Existing scheduling and execution permissions unchanged.

## Plan browsing and feed isolation

Saved-plan search, status and failed-item filters now apply before server pagination and count, including old plans beyond the previous newest-fifty window. Literal substring search covers saved plan names/zones and saved original/post titles/captions/content, not inferred categories. No schedules or items are rewritten. Publishing navigation, unified queue, calendar and saved plans remain accessible if the separate editorial-ready feed is unavailable; explicit feed/plan errors are not empty-state messages. A fresh backend suite validates older failures and API filtering. Browser checks cover failing editorial reads, server pagination/search parameters and failed plan reads without writes.

## Truthful loading and failure-filter polish

Pagination now says that a page is loading rather than showing a temporary incompatible page/total pair. Both navigation buttons stay disabled during that fetch. Unknown/error counts remain unknown. An active failure-only plan filter is always visible and can be cleared even when it has results. This is read-only display/navigation work, with a deliberately delayed isolated browser response validating the intermediate state.

## Copy-count scope correction

Home progress counts central platform_copies saved-field records and legacy PLATFORM_VARIANT output artifacts separately. The former total was incorrectly derived from legacy outputs only. Neither is an original-material count, a sum of unique materials or proof of readiness. Read-only source correction preserves all records. Integration/browser coverage seeds both types independently and verifies their separate labels/counts.

## Readiness to saved-copy review handoff

Single-original readiness details can open that platform's saved-copy panel by GET only, keeping the original identity and central approval. Missing copies remain missing until explicit preparation; no GET prepares them. Dirty copy fields block a requested platform switch without clearing edits. The copy panel follows readiness in the review journey. Existing Instagram and YouTube reviews remain distinct from account/media/execution readiness. Facebook VIDEO now links to its implemented separate Reel review with the original UUID prefilled; merely following it creates no preview, transfer or authorization. Unsupported X/TikTok execution remains explicit. Isolated browser coverage follows the handoff to Reel review, rejects dirty switching and verifies zero writes.

## Exact app-local platform scheduling

Unified Instagram already had a due-time decision/dispatch runtime. Its UI now
accepts an explicit local start time and IANA zone rather than always choosing
two minutes ahead. Facebook Reel previews can pin the same bounded future intent.
Both use a maximum seven-day app-local horizon. Telegram plans remain unchanged.
This does not add executors for TikTok, X, Snapchat, YouTube, or Facebook text/image.

The chosen time is the start of verification/upload, never guaranteed remote
appearance. No early Instagram container/grant or Facebook upload is created by
saving the scheduled decision. Instagram due-time verification refreshes the same
pinned connection read-only, then keeps the existing identity/content/media gates.
Changed/revoked/expired configuration blocks rather than selecting another account.
Facebook uses its existing platform-specific derivative and exact-byte checks,
not an assumption that the Instagram original meets Facebook audio requirements.

Decisions expire fifteen minutes after the Instagram due time or thirty minutes
after the Facebook due time. Processing that exceeds that window cannot cause a
new publish mutation; known published identifiers can still be reconciled by reads.
Unknown writes never replay. Facebook pre-send cancellation shares the worker's
advisory lock; after a write begins, local cancellation cannot promise remote undo.
Rescheduling requires cancellation/revocation and a new exact review/approval.
Legacy Facebook NOW snapshots are not rewritten or reapproved.

The owner-only operations index returns due times, public account labels, states,
and confirmed result links, never raw snapshots, private evidence or token hashes.
It is paginated separately from Telegram plans and is read-only. No deployment
creates or approves a job, changes any existing schedule, or triggers a new post.

Provider constraints checked 2026-11-25:
- https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-user/media
  documents 24-hour container expiry and 400 containers per rolling 24 hours.
- https://developers.facebook.com/documentation/video-api/guides/reels-publishing.md
  documents Page CREATE_CONTENT and pages_* permissions and 30 API-published Reels
  per rolling 24 hours. Provider limits/eligibility still apply at execution.
  Native SCHEDULED is not used; local dispatch preserves current failure semantics.

## YouTube account connector, read-only (2026-11-25)

- Separate Google Web OAuth configuration, encrypted client secret and offline tokens.
- Exact callback: `/api/connections/youtube/callback`, HTTPS and same host.
- Only `https://www.googleapis.com/auth/youtube.readonly`, never upload/modify/delete.
- Google-returned complete channel list, explicit choice, fresh channel identity check before saving. A hand-entered channel ID or old private review draft is not a connection.
- Browser/session/config-bound one-use ten-minute OAuth flow. Existing connection remains until successful explicit selection. Expired temporary credentials are cleaned up.
- Status GET does not contact Google. Explicit verify may refresh access credentials, preserving rotated refresh tokens and the selected channel. Missing/changed channel never switches silently.
- External Testing is explicitly recorded and caps refresh authorization at seven days from grant, never extended by refresh. Provider's earlier expiry and revocation also win. Published/Internal is not proof of indefinite refresh lifetime.
- Disconnect deletes local credentials and pending flows only, no remote revocation and no content deletion.
- No upload, execution or scheduling route added. Dormant resumable-upload code remains isolated, independent rights/privacy/audience review remains required.
- No live Google account/app or channel proof from synthetic tests. Cloud project/API/consent configuration and owner channel choice remain prerequisites.

Official sources checked 2026-11-25:
- https://developers.google.com/youtube/v3/guides/auth/server-side-web-apps
- https://developers.google.com/identity/protocols/oauth2
- https://developers.google.com/youtube/v3/docs/channels/list
- https://developers.google.com/youtube/data/reference/rest/v3/videos/insert
- https://developers.google.com/youtube/data/guides/quota_and_compliance_audits

Current Google pages no longer impose the former unverified-project private-only upload restriction. Do not use that stale rule as an account blocker. This does not activate uploads or waive OAuth/account requirements.

## Facebook Page text runtime, 2026-11-25

A saved approved TEXT original and its exact Facebook copy can now be privately
previewed against the saved Page, then separately approved for public Page text
publication. Image/video inputs and nonempty extra copy fields are rejected,
not silently dropped. Central approval, copy validity, connection verification
and the explicit execution decision remain separate facts.

The decision pins source/copy/Page and optional app-local time up to seven days.
The worker checks current prerequisites at dispatch, commits SENDING before the
single POST, persists a known post ID before readback, and never auto-resends an
unknown outcome. A Page readback, not a returned ID, establishes publication.
An interrupted worker becomes OUTCOME_UNKNOWN. Legacy dormant rows cannot enter
this scanner. Cancel is local and only before sending; it does not delete posts.

No live public text acceptance test was run for this tranche. Existing live
posts and held production videos were not used. No claim of end-to-end provider
acceptance follows from the synthetic tests or deployment alone.
