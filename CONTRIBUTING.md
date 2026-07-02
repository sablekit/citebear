# Contributing to CiteBear

Thanks for your interest! Bug reports, fixes, and improvements are welcome.

## Setup

Prerequisites: Node 24+, pnpm 10+, Python 3.12+, [uv](https://docs.astral.sh/uv/).

```bash
# web
pnpm install
pnpm dev:web

# api
cd apps/api
uv sync
uv run uvicorn citebear_api.app:app --reload
```

A local Postgres (docker compose) ships with the retrieval pipeline work.

## Before you open a PR

Run the same checks CI runs:

```bash
pnpm lint:web && pnpm typecheck:web && pnpm build:web
cd apps/api && uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest
```

- Use [Conventional Commits](https://www.conventionalcommits.org/) and keep
  commits small and single-purpose.
- New dependencies need a one-sentence justification in the PR description.
- See [AGENTS.md](AGENTS.md) for the full set of project conventions.

## Pull requests

Target `main`. CI must be green before review. PRs are merged with a merge
commit to preserve the commit story.
