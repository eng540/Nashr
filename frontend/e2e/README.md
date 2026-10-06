# Browser E2E

The browser suite exercises the actual FastAPI application through Vite's development proxy.

The critical publishing test waits for a real POST /schedules response and asserts HTTP 201 plus the request payload. It does not mock the scheduling API.

CI provisions PostgreSQL, applies Alembic migrations, seeds one approved post, starts FastAPI and Vite, then runs Chromium.

The workspace-boundary test passes selected_post_ids through URL state; no DOM bridge or global browser state is used.
