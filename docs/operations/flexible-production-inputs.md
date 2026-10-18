# Flexible production inputs

## Supported request modes

The Content Factory supports three explicit modes through the existing Production Jobs path:

- **Product**: run a published Product with its immutable, pinned component manifest.
- **Product + task instructions**: run the same published Product and append request-scoped instructions for this job only.
- **Custom**: run without a Product, using the user's task instructions and an explicitly selected published compatible recipe.

Each mode can use either selected Library material(s) or direct text. Direct text is stored as a normal Nashr Source and Knowledge Unit with the existing lineage model; it is marked with MIME type `application/vnd.nashr.inline-text` so it does not appear as an ordinary library upload.

## Boundaries

- Product-backed runs use the recipe, prompt, identity, output contract, and policy pinned by the published Product version. Request instructions do not mutate that Product version or replace its pinned constraints.
- Custom mode requires task instructions and rejects a Product selection.
- Productless production currently accepts only published recipes whose stages are all `produce_post`, with the `TELEGRAM_POST` output contract. Other output types remain Product-backed until a compatible recipe and contract are explicitly supported.
- The selected recipe and other resolved components are captured in the job's resolved context. Execution uses that saved context when the job starts or resumes.
- Task instructions are persisted on the Production Claim and appended to the pinned editorial prompt when the job executes. They are not a frontend-only note.
- Multiple selected materials currently follow source/library order. A separate user-defined reordering control is not included in this change.
- Idempotency replay is checked before direct-text Source/Knowledge Unit rows are created, preventing duplicate lineage rows for a replayed request.
- The production job still enters the existing review flow. This feature does not approve content or publish to Telegram automatically.

## Verification

The GitHub Actions `test` workflow covers backend tests, frontend type checking and unit tests, production build, and browser E2E for direct-text custom production and product-backed production with additional task instructions. Treat the latest run on the PR head SHA as the evidence for current status; a passing run on an earlier commit does not validate later code changes.

No Railway deployment or external Telegram publication is part of implementing or testing this feature.
