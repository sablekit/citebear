# CiteBear 🐻

> A source-cited RAG chatbot that never makes things up.

CiteBear answers questions over your documents with **citations to the exact
page**, streams like ChatGPT, and says *"I don't know"* instead of guessing.

**Live demo:** [citebear.com](https://citebear.com) *(coming soon)*

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

## License

[MIT](LICENSE)
