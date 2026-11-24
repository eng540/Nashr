# Instagram execution core, not live publishing

The provider edge and persistent execution state machine can be exercised with
synthetic providers. They are not reachable from production execution routes,
schedulers, previews or media inspections. No account or token is assumed, and
no signed or publicly readable user-media URL is minted by this implementation.

The existing connection handoff uses Unified Login, with Business Integration
System User access tokens, not the Instagram Login token-refresh recipe. The connection controls store client_business_id, token type/expiry/check
state and local enabled state. Actual account acceptance and permission matching
remain unverified; the controls do not expand scopes. Token management requiring business_management must not be
assumed from the current instagram_basic and instagram_content_publish grant.

## Implemented core

- Single JPEG image or Reel container with exact reviewed caption. Reel feed
  visibility is explicit. No carousel, Story, trial reel, branded post or ads.
- Fixed versioned Meta endpoint and bearer token header, no secrets in returned
  errors or request URLs. No mutation retries, including transient provider errors.
- Persisted DRAFT, CREATING, CONTAINER_CREATED, WAITING_MEDIA, PUBLISHING,
  PUBLISHED_ID_KNOWN, PUBLISHED and unknown/failure states. Claims persist before
  a provider mutation; competing calls cannot submit the same claim twice.
- Pin account, original fingerprint, copy version and supplied media byte digest.
  Provider calls require a separate explicit authorization argument. This is an
  internal guard, not a user-permission record and not sufficient for live use.
- A timeout or lost mutation response stays unknown. Container status is read
  without automatic republish. PUBLISHED without a returned media ID is distinct
  from confirmed media identity; no invented permalink or successful ledger.
- No media URLs stored in the execution row. Future media grants must be minted
  only as part of an explicitly authorized publishing action, not preview.

## Still required before live execution

1. Verified account lifecycle and selected-account pinning, including disabling,
   expiry, reauthorization and preserving historical attempts.
2. Exact inspected original/selected-media bytes tied to the digest, measured
   media requirements and a bounded provider-readable grant. The supplied digest
   in this core is a pin, not a claim the media has been inspected.
3. Owner-approved outgoing words/account/media/destination/time and audit record,
   scheduler claims and cancellation behavior. No production toggle enables this
   core until these conditions are implemented together.
4. Owner-only operator surface and worker-stop proof for interrupted claims.
   The internal compare-and-set helper can mark a stopped CREATING/PUBLISHING
   claim unknown without retrying it. Its explicit argument is not authenticated
   evidence and no production route calls it. No timeout heuristic may turn a
   claim into a retry.
5. External acceptance against an authorized real account and publishing scope.
   Synthetic tests prove code behavior, not account connection or platform acceptance.

Sources checked2026-11-24:
- https://developers.facebook.com/documentation/instagram-platform/content-publishing
- https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-unified-login/get-started
- https://developers.facebook.com/documentation/facebook-login/facebook-login-for-business

## Additional synthetic safeguards

An unclaimed DRAFT can be cancelled locally. Cancellation is refused after any
provider claim, so it cannot be mistaken for undoing a remote operation. An
interrupted claim can only be marked unknown after a caller explicitly confirms
the worker stopped and supplies the exact observed state and update timestamp.
Stale operator reads cannot overwrite a newer result. Both create and publish
claims have independent concurrent-call tests. A failed read before publishing
returns to WAITING_MEDIA, while an uncertain mutation still remains unknown.

These are internal safeguards only. They do not enable publishing or authorize
a future caller to expose media, select an account, or claim an external result.

The dormant provider also has a read-only selected-account check. It validates
token validity, app identity, required existing scopes, expiry, client business
identity and exact membership in assigned Instagram accounts. It refuses an
incomplete paginated list and never follows upstream pagination URLs. It returns
no publishing grant, performs no refresh and requests no new scope. Production connection controls and token fact persistence are described below;
actual account acceptance remains unverified.

## Owner connection controls

Migration0065 stores the client business identity from Unified Login, identifies
the BISU flow, and keeps enabled state and last-check facts separate. Existing
connections preserve their identity; a missing business ID is filled only by an
explicit successful check. A different business ID fails without replacing it.
Owner-authenticated same-origin verify and local-state endpoints send no content.
A check does not re-enable a disabled connection. Re-enabling requires a successful
check within five minutes. No credentials are returned, and input_token is
redacted from standard HTTP diagnostics. Neither endpoint enables publishing.


## Private inspected-byte pinning

New drafts require a saved inspection of the currently selected Instagram media,
including explicit original selection. The inspection must match the original
fingerprint, copy version, selected asset, current probe version and measured
hash, with no media blockers. Pending checks remain pending, not platform
acceptance. Existing synthetic drafts without evidence fail closed.

Before either provider mutation the dormant core re-reads the private file with
the bounded local probe. It compares the current hash to both saved inspection
and attempt, checks the selected path and validates the outgoing fields again.
Private media reads occur only after the internal authorization/account checks.
No presigned URL is minted and no media is made provider-readable by these reads.

This closes the supplied-digest-only gap, but it does not prove that an arbitrary
caller-supplied provider URL serves those bytes. A future immutable grant must bind
the provider-readable bytes to the exact digest and publishing permission, with
expiry and retention rules. No production route, scheduler or UI enables this
core before that binding, owner publishing authority, unresolved media checks
and actual external acceptance are complete. The internal boolean is still not
an owner-permission record. This implementation does not authorize live calls.
