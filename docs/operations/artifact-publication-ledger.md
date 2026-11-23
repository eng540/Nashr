# Read-only Artifact publication ledger

GET /api/artifacts/{artifact_id}/publications returns the existing publication rows only. It checks that the generic artifact exists, uses stable descending pagination (limit1-100, offset zero or greater), and never calls draft creation or a publishing adapter.

Each row exposes the recorded platform, destination, publication status, frozen content, every returned message ID, error and acceptance time. Legacy single external_id values become one-element display lists. Linked schedule items show their status, attempts and last error. Destination and content stay within the existing application audience, not in public repository documentation.

The bank loads this ledger only after an explicit read action and offers manual refresh. It distinguishes approval from publication, uncertain PUBLISHING from proven acceptance, and an empty application ledger from possible manual publication elsewhere. This does not claim Telegram-client visual verification, operator attribution, or complete event history. No retry, send or mutation button is added.

Tests cover all message IDs, destination, schedule attempts, repeated reads with no new row, missing artifacts, bounds and the desktop/mobile UI with zero outgoing writes.
