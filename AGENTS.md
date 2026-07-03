# CiteBear — Agent & Contributor Context

Source-cited RAG chatbot: a Next.js web app and a FastAPI retrieval service in
a pnpm/uv monorepo.

## Layout

- `apps/web` — Next.js 16 (App Router, TypeScript strict, Tailwind). UI and
  streaming proxy only; it never talks to the database or model providers
  directly. Has its own `AGENTS.md` with Next.js 16-specific guidance.
- `apps/api` — FastAPI + LangChain (Python 3.12, uv). All RAG logic lives
  here: ingestion, hybrid retrieval, reranking, generation.
- `docs/SPEC.md` — the specification. It is a living document: when
  implementation overturns a spec decision, amend the spec first, then the code.

## Commands

Web (from the repo root):

```
pnpm install
pnpm dev:web | lint:web | typecheck:web | build:web
```

API (from `apps/api`):

```
uv sync
uv run pytest
uv run ruff check .  &&  uv run ruff format .
uv run pyright
uv run uvicorn citebear_api.app:app --reload
```

Keep `--reload` on Windows dev machines: uvicorn's reload mode selects the
selector event loop that async psycopg requires (the default proactor loop
fails on any DB call).

## Conventions

- **Git:** Conventional Commits (`feat:`/`fix:`/`docs:`/`chore:`); branches
  `feat/kebab-case`; PR titles in commit style. All changes land via PR with
  green CI. One commit = one logical unit — decide its scope and message
  before writing the code.
- **API JSON is camelCase** externally; Python and SQL stay snake_case
  (pydantic alias generators at the boundary).
- **Errors are RFC 9457 Problem Details** (`application/problem+json`)
  everywhere, including SSE error events. No custom error envelopes.
- **Postgres:** snake_case; plural table names, singular columns; foreign keys
  `<singular>_id`; `timestamptz` in UTC; primary keys `uuidv7()` (Postgres 18).
  Migrations via Alembic.
- **Config is env-only and validated at startup:** pydantic-settings (api),
  `@t3-oss/env-nextjs` (web). Missing config fails the boot, not the request.
- **Dependencies:** a new dependency needs a one-sentence justification in the
  PR description (why stdlib/existing deps don't suffice).
- **Logging red line:** secrets and full chunk contents never appear in logs.
- **Language:** all repo content and UI copy in English.
- **Quality gates:** ruff (lint + format) and pyright strict for Python;
  eslint and `tsc --noEmit` for TypeScript. CI runs all of them.
