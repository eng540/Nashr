# Native Telegram Quiz payload

Nashr's typed quiz payload is represented by `app.domain.quizzes.QuizPayload`:
- `question`: required, 1–300 characters.
- `options`: 2–12 non-empty options, each at most 100 characters.
- `correct_option_ids` (a one-element list for a single-answer quiz): required zero-based index into `options`; never inferred from prose.
- `explanation`: optional, at most 200 characters.
- `source_reference`: optional provenance for review; it is not sent to Telegram.

The Telegram adapter maps the payload to Bot API `sendPoll` with `type=quiz`.
A network timeout after Telegram has accepted a poll can leave the outcome ambiguous: retrying may create a duplicate poll because the Bot API does not provide a client-supplied idempotency key for `sendPoll`. The existing publication ledger can record known successful message IDs but cannot prove non-delivery after an ambiguous timeout.
