# Frontend Architecture

Status: PR #47 / Frontend Foundation

## Responsibilities

The React application owns presentation, browser navigation, local UI state, and server-state orchestration. It does not own domain rules or database behavior.

The boundary is:

Browser → React/TypeScript → shared API client → FastAPI → Application → Domain → Infrastructure/Adapters

## Structure

- app/: application shell and routing.
- features/: workspace-specific UI and feature behavior.
- shared/api/: the only HTTP boundary used by feature code.
- shared/components/: presentation primitives shared by workspaces.
- shared/types/: API response/input contracts.
- shared/utils/: pure browser utilities.

Publishing and Post Bank are independent features. They may share API contracts and URL identifiers, but neither imports DOM/state from the other.

## Workspaces

- /posts/workspace: Post Bank and editorial review.
- /publishing: approved-post selection, eligibility, scheduling.

Cross-workspace handoff uses selected_post_ids in URL state. There is no global DOM bridge and no window-level selection object.

## State

TanStack Query owns server state, loading/error/refetch/cache/mutation lifecycle.

React local state owns transient UI state such as selection, form values, and open panels.

Redux, Zustand, and a second state framework are intentionally not introduced.

## API boundary

Feature components call postsApi and schedulesApi. The API client owns fetch, JSON decoding, and HTTP error normalization.

No new backend endpoints were added by this PR.

## Legacy HTML policy

The existing Python HTML workspaces remain available as compatibility fallbacks when a frontend production bundle is not present.

New frontend behavior must not be added to NASHR_*_HTML strings.

The compiled React bundle is served by FastAPI for /publishing and /posts/workspace when frontend/dist exists. /console and the Library/Book Map/Materials/Discovery surfaces remain legacy and are outside this migration.

## Production/development

Development uses FastAPI on port 8000 and Vite on port 5173 with Vite proxying API paths.

Railway keeps the existing service and builds the frontend during the existing application build. FastAPI serves the compiled React shell/assets; no second production service is introduced in this PR.

## Testing

- Backend unit/integration tests remain unchanged in domain behavior.
- Frontend unit coverage protects the selection contract.
- Playwright runs Chromium against FastAPI through Vite.
- The scheduling E2E waits for the actual POST /schedules response and asserts HTTP 201 and request payload.
- The workspace E2E verifies Content Factory → Publishing through selected_post_ids, not DOM coupling.

## Migration strategy

This is a progressive migration. Legacy Console remains operational. Publishing and Post Bank are the first React workspaces. Library, Book Map, Materials, Discovery, and other legacy pages are not rewritten here.

## Explicit non-goals

No Identity, Recipe, Artifact schema, Product domain, authentication redesign, microservices, queue infrastructure, or scheduling/review/domain rewrite belongs to this PR.
