## What & why

<!-- One or two sentences. Link the issue if there is one. -->

## Checklist

- [ ] Conventional-commit title and small, single-purpose commits
- [ ] `pnpm lint:web && pnpm typecheck:web && pnpm build:web` pass (web changes)
- [ ] `ruff check`, `ruff format --check`, `pyright`, `pytest` pass (api changes)
- [ ] New dependencies justified below (or none added)
- [ ] Spec updated first if this overturns a design decision
