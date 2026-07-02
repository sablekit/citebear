# CiteBear 🐻

[![CI](https://github.com/sablekit/citebear/actions/workflows/ci.yml/badge.svg)](https://github.com/sablekit/citebear/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

> A source-cited RAG chatbot that never makes things up.

CiteBear answers questions over your documents with **citations to the exact
page**, streams like ChatGPT, and says *"I don't know"* instead of guessing.

**Try it live:** [citebear.com](https://citebear.com) *(coming soon)*

## Status

🚧 Under construction — Milestone 0 (scaffold & deploy pipeline).
See the [v1 specification](docs/SPEC.md) for the full design.

## Architecture (v1)

- `apps/web` — Next.js (App Router, TypeScript, Tailwind) chat UI with
  streaming answers and clickable citations
- `apps/api` — FastAPI + LangChain ingestion/retrieval pipeline: hybrid
  search (pgvector + Postgres full-text), reciprocal-rank fusion, LLM
  reranking, grounded-only generation
- Postgres + pgvector (Neon), Vercel Blob for originals, models via an
  OpenAI-compatible gateway (provider-agnostic)

## Development workflow

CiteBear is built spec-first with an AI-assisted workflow (Claude Code): the
[spec](docs/SPEC.md) precedes the code, every change lands as a reviewed,
signed, conventional commit, and the retrieval pipeline is gated by a golden
test set. The workflow itself is part of what this repository demonstrates.

## Maintainer

[Sablekit](https://github.com/sablekit) (Henry Jia)

## License

[MIT](LICENSE)
