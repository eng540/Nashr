# Snapchat Public Profile identity preparation

Checked26November2026 against official Snap documentation:
- https://developers.snap.com/marketing-api/Public-Profile-API/GetStarted
- https://developers.snap.com/marketing-api/Public-Profile-API/Profiles

## Current boundary

Nashr has no Snapchat OAuth/account connector, token store, upload, scheduler or
publisher. The connections page now lists Snapchat explicitly as not implemented
instead of silently omitting the requested platform. It describes prerequisites,
not a claim about the current owner's account or permission to make changes.

The isolated `snapchat_profile.py` adapter implements only the documented GET
`https://businessapi.snapchat.com/v1/public_profiles/my_profile`. It requires an
already authorized token supplied by its caller. It has no application route or
scheduled caller. No real Snap request or owner eligibility proof was performed.

It checks SUCCESS, a valid profile UUID, bounded nonempty display name/username,
and an optional exact expected UUID. It returns only those three identity fields,
not address, phone, email, organization, media URLs or arbitrary response fields.
It refuses redirects, non200 status, partial/error/malformed responses, unexpected
profile changes and network failures, using generic errors without provider body
or token content. It makes no retry or write request.

## External prerequisites, not performed

Snap documents allowlisting for the Public Profile API, a Snapchat account,
Business organization and an OAuth app generated in Business Details. It warns
that a Developer Portal client ID will not work for this API. Profile-owner OAuth
uses scope `snapchat-profile-api`. Login Kit identity is not interchangeable with
Public Profile API access. Documentation does not prove any particular account,
app or profile is currently approved or even exists.

A future account flow needs separately reviewed configuration, encrypted secrets,
CSRF/session-bound one-use callback, exact returned identity selection and current
permission checks. Do not request broad scopes, create a business account, accept
terms, contact Snap or publish to claim this preparation is complete. Owner token
consent is not a publishing decision. Actual account setup, allowlisting, upload
rights and public posting authority remain independent unresolved work.

## Acceptance

Unit tests use httpx.MockTransport only. They cover minimum returned identity,
missing/wrong types, invalid UUID, changed identity, error/partial statuses,
redirect refusal and generic network errors. A fake-session overview test checks
Snapchat is explicitly NOT_IMPLEMENTED and execution_authorized remains false.
The existing connections browser test checks its navigation/requirements, no
Snapchat connect button, preserved Telegram flow, phone layout and no unintended
writes. These are local engineering tests, not real Snapchat acceptance.
