# Native Telegram Quiz payload

Nashr's typed quiz payload is represented by `app.domain.quizzes.QuizPayload`:
- `question`: required, 1–300 characters.
- `options`: 2–12 non-empty options, each at most 100 characters.
- `correct_option_id`: required zero-based index into `options`; never inferred from prose. The adapter sends Telegram's `correct_option_id` integer field.
- `explanation`: optional, at most 200 characters.
- `source_reference`: optional provenance for review; it is not sent to Telegram.

The Telegram adapter maps the payload to Bot API `sendPoll` with `type=quiz`.
A network timeout after Telegram has accepted a poll can leave the outcome ambiguous: retrying may create a duplicate poll because the Bot API does not provide a client-supplied idempotency key for `sendPoll`. The existing publication ledger can record known successful message IDs but cannot prove non-delivery after an ambiguous timeout.

## Review and publication API

1. Generate a QUIZ Artifact with a product recipe stage using `produce_quiz_artifact` and a pinned QUIZ inline output contract.
2. Review and approve it through the existing generic artifact review API: `POST /api/artifacts/{artifact_id}/approve`.
3. Create a durable Telegram draft with `POST /api/artifacts/{artifact_id}/telegram-draft`.
4. Publish it using the existing `POST /publications/{publication_id}/publish` endpoint, passing the approved question as `content`.
5. To schedule it instead, use `POST /api/artifacts/{artifact_id}/schedule` with `name`, `timezone`, and timezone-aware `scheduled_at`, then activate the returned schedule through the existing schedule API.

The schedule path rechecks approval immediately before publication. No tests call Telegram's live API.
