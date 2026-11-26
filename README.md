# Nashr | ناشر

منصة عربية لإدارة مصادر المحتوى وبنك المنشورات والمراجعة والتجهيز لكل منصة والجدولة وسجل التنفيذ.

Nashr is an Arabic-language content factory and publishing workflow. It brings source material, a content bank, human review, platform-specific copy, scheduling and publishing history into one application.

## Status and scope

Early, active development. The repository contains platform adapters and workflow checks, not a promise that every account is connected or every content type can be published everywhere. Live access depends on platform permissions, account eligibility and completed setup. Preparation, approval, platform readiness and actual publication are separate states.

Existing content can be reviewed and prepared without AI generation. Optional generation requires configured providers and may cost money. Approval of an original does not mean publication to every platform: target selection, exclusions and per-platform blockers still apply.

## What is implemented in the code

- A content bank for generated, imported and manually added material, with editing and human review.
- Platform-specific text and media preparation, while keeping originals separate.
- Telegram, Instagram and Facebook publishing paths for supported content types, with account connections, permission/readiness checks, a queue, calendar views and execution history. Support varies by platform and content type.
- Versioned production products and component manifests, source lineage, saved execution context and retry safeguards.
- Optional source-based generation and production history.

These are code capabilities. This README does not report current account connectivity or a completed live publishing test.

## Stack

- Python 3.12+, FastAPI, async SQLAlchemy, Alembic and PostgreSQL
- React and TypeScript frontend
- pytest backend tests, frontend unit tests and Playwright browser tests
- Railway deployment configuration

## Local development

Use a disposable local PostgreSQL database. Copy `.env.example` to your local environment and review its settings before starting anything. Never commit credentials or production exports.

```sh
python -m pip install -e ".[test]"
# Set DATABASE_URL to your local PostgreSQL database first.
alembic upgrade head
pytest tests/unit -q
pytest tests/integration -q
```

Integration tests require the local database and applied migrations. Tests marked `gemini` make real provider requests and require separate configuration; do not enable them casually.

```sh
npm --prefix frontend install
npm --prefix frontend run typecheck
npm --prefix frontend test
npm --prefix frontend run build
python -m uvicorn app.main:app --reload
```

The complete browser-test setup, including database seeding and the local server, is in `.github/workflows/test.yml`. Use isolated test data. Do not point development or browser tests at production accounts or a production database.

## Operations and recovery

- [Documentation index](docs/README.md)
- [Recovery preparation and isolated drill](docs/operations/recovery-preparation.md)

The recovery drill uses disposable loopback databases and synthetic files. It is not evidence of a durable production backup or a verified live restore.

## License

No project license has been selected yet. This repository being visible does not itself grant an open-source license. A license decision is separate from documentation and development work.
