# Facebook text/photo result history

The shared read-only connector history includes live-bound Facebook text/photo attempts. This supplies the material history and content queue without creating publication ledger rows or changing runtime behavior.

A row needs an object runtime snapshot whose saved Page matches its Page ID, a text/photo kind and an owner-session/trusted-message evidence reference. Dormant, synthetic, draft and cancelled attempts are excluded. Evidence references, raw snapshots, tokens and media URLs are not returned.

`PUBLISHED_AT_LAST_CHECK` plus a numeric Page-scoped post identity is historical confirmation, even after approval expiry. A known ID alone, unknown outcome or invalid post identity is not confirmation and remains visible for review. HTTPS Facebook links are optional. Only numeric Page/posts/post paths and permalink.php query forms that match both saved Page and post ID are exposed. Other-page, other-post, vanity and unrecognized forms are withheld without erasing otherwise confirmed provider readback. A confirmed result is not proof that the current edited copy was published or permission to send again.

No schema, provider, worker, scheduler, grant or account changes are part of this projection. Verification does not require sending new content.
