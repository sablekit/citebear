# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-07-06

First public release. Source-cited document Q&A and a support bot over a
document library, live at [citebear.com](https://citebear.com).

### Added

- **Streaming chat** — token-by-token answers over Server-Sent Events, with
  citation chips surfaced before the first word is written.
- **Citations to the exact page** — every answer traces each claim to a source
  document and section; clicking a `[n]` marker opens the highlighted passage,
  page-deep-linked to the original, with its authors and license. A
  post-generation check drops any marker that doesn't map to a retrieved chunk.
- **Hybrid retrieval** — parallel semantic (pgvector cosine) and keyword
  (Postgres full-text) search, fused with reciprocal rank fusion (`k = 60`).
- **Listwise reranking** — a single LLM rerank call scores the fused candidates
  together and selects the top results; its scores also drive answer confidence.
- **Grounded-only answers** — the model answers from retrieved context or
  refuses; sub-threshold retrieval refuses without calling the generator, and
  the middle band answers with a low-confidence flag in the UI.
- **Multi-turn condensing** — follow-up questions are rewritten to a standalone
  query for retrieval; the first turn skips the extra call.
- **Self-serve ingestion** — upload PDF / DOCX / Markdown; structure-preserving
  chunking keeps a page range and section trail on every chunk. Caps and
  deterministic input errors are rejected before any row is written.
- **Admin surface** — password-gated document management (upload, status,
  delete with cascade), a paginated question log with feedback, and aggregate
  stats (questions, 👍/👎, refusal rate).
- **Feedback** — 👍/👎 on every finished answer, one idempotent row per message.
- **Rate limiting** — public chat is limited per hashed client IP; admin login
  throttles failed attempts, both without an external store.
- **Provider-agnostic models** — chat, embedding, and rerank models are
  `provider/model` strings through a gateway; no code change to switch provider.
- **Preloaded library** — a small, license-clean library (Calibre manual, the
  Debian Administrator's Handbook, NIST SP 800-63B-4) so visitors can ask real
  questions with no upload, each source attributed in the UI.
- **Golden test set** — question→expected-source pairs gate the retrieval
  pipeline in CI.

[1.0.0]: https://github.com/sablekit/citebear/releases/tag/v1.0.0
