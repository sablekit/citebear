# v1.0.0 — release notes draft

> Draft for the GitHub Release body. **Do not tag from here** — cut the signed
> `v1.0.0` tag after eyeballing production, then paste this in and adjust the
> date in `CHANGELOG.md` to the tag day.

---

**CiteBear** is a source-cited RAG chatbot that answers questions over a document
library, cites every claim back to the exact page, and says *"I don't know"*
instead of guessing.

**Try it live → [citebear.com](https://citebear.com)**

## Highlights

- **Citations to the exact page.** Click a `[n]` marker and the exact source
  passage opens, highlighted and page-deep-linked, with its authors and license.
- **Hybrid retrieval + reranking.** Parallel semantic (pgvector) and keyword
  (Postgres full-text) search, fused with reciprocal rank fusion, then a
  listwise LLM rerank.
- **Grounded-only.** Sub-threshold retrieval refuses without calling the model;
  low-confidence answers are flagged, never dressed up.
- **Self-serve ingestion.** Upload PDF / DOCX / Markdown with
  structure-preserving chunking that keeps page ranges and the section trail.
- **Admin surface.** Document management, a question log, and 👍/👎 feedback
  stats.
- **Provider-agnostic.** Swap Claude / GPT / others via `provider/model` strings
  through a gateway — no code change.

## Preloaded library

The public instance ships a small, license-clean library so you can ask real
questions with no upload:

- Calibre User Manual — Kovid Goyal (GPL-3.0-only)
- The Debian Administrator's Handbook — Raphaël Hertzog & Roland Mas
  (GPL-2.0-or-later OR CC-BY-SA-3.0)
- NIST SP 800-63B-4: Digital Identity Guidelines — NIST (public domain)

## Stack

Next.js (App Router, TypeScript, Tailwind) · FastAPI + LangChain (Python 3.12) ·
Neon Postgres with pgvector + full-text · Vercel Blob · models via an
OpenAI-compatible gateway. See the [README](../README.md) for the architecture
and design notes, and [`docs/SPEC.md`](SPEC.md) for the full design.

**Full changelog:** [`CHANGELOG.md`](../CHANGELOG.md)
