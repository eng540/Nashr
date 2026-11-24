# Instagram execution gates

This release implements dormant mechanics only. No decision, media capability,
dispatch or publication HTTP endpoint is registered. The production scheduler
does not import the dispatch coordinator. No environment switch activates it.
Existing private review/staging UI cannot record consent or expose a media URL.

## Exact decision

An internal proposal binds execution, account, connection generation, exact
caption/alt text, selected media inspection/digest, source/copy, public audience,
due time and timezone. Its disclosure says a bearer link is readable by anyone
holding it for up to15minutes and Meta may retain its copy. A future authenticated
handler must present this exact proposal and record the actual owner approval
with its original trusted source. Caller booleans alone are not evidence.

Approval of the central material, a review snapshot, a staged execution draft or
an OAuth grant is not this publication/disclosure decision. Revocation cancels
pending dispatch and capability reads, not a post already accepted by Meta.

## Bounded media access

Capabilities have256bits of randomness and only their SHA256digest is stored.
They are pinned to one job/decision/media digest, no longer than15minutes,
revocable and bounded to20reads. Minting is prohibited before the approved due
time. Every read verifies decision/connection/source/inspection and exact private
bytes. No token or URL enters the ledger. No HTTP media handler exists yet.

The future endpoint must disable body/query/access-token logging, send no-store,
no-referrer/nosniff, enforce a bounded request/range policy and avoid redirecting
to storage. It must not treat a Meta-looking user-agent/IP as identity. The
bearer-capability disclosure is intentional, not a claim of Meta-only access.

## Dispatch and reconciliation

One dispatch per job, due scan bounded to20, claim persisted before effects.
Runtime disabled by default and no production registration. A synthetic test
can inject a provider and a deliberately unresolvable URL factory. Default calls
stop before provider/storage access. Unknown mutation outcomes never resubmit.
A verified waiting-container state can resume a status read and one publish
attempt. No tight polling. Grants remain bounded while media is processing,
then revoke on known completion/failure/unknown outcome. Interrupted claims need
operator proof the worker stopped, not a timeout guess. Readback is independent
of current consent because it reports the already-attempted provider result.

## Remaining acceptance gates

- Real Instagram Login configuration and explicit owner OAuth.
- Authenticated exact-decision UI/handler and original-source evidence.
- Reviewed media capability HTTP handler with safe streaming/range behavior,
  access-log redaction, request limits and cleanup, still off until consent.
- A production scheduler registration and verified-provider construction path,
  including a real policy for account-check freshness at the approved due time.
- Owner-approved public publication and media disclosure for a specific test.
- Provider acceptance, async readiness/reconciliation and reported live result.

No production acceptance is claimed by synthetic tests.
