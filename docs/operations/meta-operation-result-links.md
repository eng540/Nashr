# Identity-bound Facebook Page links in operation lists

The read-only Meta operation list and daily calendar now reuse the same SQL permalink projection as material history for Facebook TEXT and IMAGE results. A link must use a supported numeric Page/post path or permalink query and match both parts of the saved Page-scoped post ID. Unknown, wrong-post, wrong-Page, vanity, malformed, fragment and nonstandard-port URLs are withheld. Missing or invalid IDs also withhold the link.

The existing confirmed execution-state gate still applies. Withholding a URL does not delete or downgrade the recorded operation state. Counts, filters, scheduling, workers, dispatch, provider calls, permissions and saved records are unchanged. Instagram and Facebook Reel URL rules are unchanged.

Regression evidence: before the fix, two isolated integration tests showed TEXT and IMAGE operation lists exposing a same-domain URL for post 999 while the saved result was 123_456. After the fix, 31 operation-link cases cover both kinds, accepted forms, identity boundaries and unconfirmed states. The existing material-history tests protect unchanged semantics of the shared helper. A mobile browser test checks that a confirmed photo without a safe URL retains its visible result and local review link, while a text result with a matched URL keeps its external link. This test uses mocked reads and makes no writes.

No live post, schedule, permission or stored result was created or changed to validate this fix. Local tests are not proof of a new live publication.
