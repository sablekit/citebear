# CiteBear v1 Specification

> A source-cited RAG chatbot that never makes things up.

**Status:** Draft for review
**Scope:** v1 (~2 weeks). Anything not listed under [Goals](#goals) is out of scope.

---

## 1. Overview

CiteBear is an open-source, source-cited document Q&A system. Users upload
documents (PDF / DOCX / Markdown), then ask questions in a streaming chat UI.
Every answer cites the exact source document and page/section, with clickable
citations that open the highlighted source passage. When the retrieved context
does not support an answer, CiteBear says "I don't know" instead of guessing.

Two personas:

- **Visitor** — chats with the preloaded library on the public instance. No login.
- **Admin** — uploads/manages documents, reviews the question log and feedback
  stats. Protected by a single admin password (no user accounts in v1).

## 2. Goals

1. **Streaming chat** — token-by-token answers, "ChatGPT feel".
2. **Citations** — every factual claim in an answer traces to document +
   page/section; citations are clickable and open the source passage highlighted.
3. **Ingestion pipeline** — PDF/DOCX/MD upload → structure-preserving chunking
   with metadata → embeddings → Postgres.
4. **Hybrid retrieval** — vector similarity + keyword full-text search, fused,
   then reranked.
5. **Grounded-only answers** — refuses when evidence is weak; low-confidence
   answers are visibly flagged in the UI.
6. **Admin page** — document upload/management, question log, 👍/👎 feedback stats.
7. **Provider-agnostic models** — chat and embedding models are `provider/model`
   strings behind an OpenAI-compatible gateway (**Vercel AI Gateway** by
   default; OpenRouter or self-hosted LiteLLM are a two-env-var swap).
   Switching Claude ↔ GPT is a config change.

### Non-goals (v1)

- Multi-tenancy / workspaces
- User accounts, OAuth, RBAC (admin password only)
- OCR for scanned PDFs (phase 2)
- Telegram / Slack channels (phase 2)
- Billing / pro tier (phase 3)
- Conversation memory across sessions (each chat session is independent;
  multi-turn within a session IS supported)

## 3. Architecture

```
┌─────────────────────────────┐        ┌──────────────────────────────┐
│  apps/web  (Vercel)         │        │  apps/api  (Vercel Fluid /   │
│  Next.js App Router, TS     │  HTTP  │  Railway fallback)           │
│  Tailwind, Vercel AI SDK    │ ─────► │  FastAPI + LangChain (Py)    │
│  chat UI · citations panel  │  SSE   │  ingestion · retrieval ·     │
│  admin UI                   │ ◄───── │  generation · feedback API   │
└─────────────────────────────┘        └──────────┬───────────────────┘
                                                  │
                            ┌─────────────────────┼─────────────────────┐
                            ▼                     ▼                     ▼
                  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐
                  │ Neon Postgres    │  │ Vercel AI Gateway│  │ Vercel Blob  │
                  │ + pgvector       │  │ chat + embedding │  │ (originals)  │
                  │ + full-text (FTS)│  │ models           │  │              │
                  └──────────────────┘  └──────────────────┘  └──────────────┘
```

- **Monorepo**, single git repo: `apps/web` + `apps/api`, shared nothing at the
  code level (API contract is the boundary; documented in this spec).
- The Next.js app never talks to the database or model providers directly —
  all RAG logic lives in the Python API. Web is presentation + streaming proxy.
- Original uploaded files go to Vercel Blob so the citation viewer can link to
  the source document. Parsed text/chunks live in Postgres.

### Deployment risk note

FastAPI on Vercel Fluid Compute is the primary target; **Railway is the
sanctioned fallback** if cold starts, request duration limits, or Python
packaging cause friction. The single sharpest stressor is ingestion: parsing
and embedding a max-size document is a multi-minute request, and serverless
offers no safe fire-and-forget background work (see 5.1). Milestone 0
validates this with a synthetic long-request test before any feature work.

> **Validated 2026-07-02:** a 270 s streamed request (CPU bursts + I/O waits)
> completed on Fluid with progressive streaming and no timeout. Worst-case
> ingestion (~2–3 min) fits with margin. **Decision: Vercel; the Railway
> fallback is retired.**

## 4. Data model (Postgres + pgvector)

```sql
documents (
  id            uuid PK,
  title         text NOT NULL,
  filename      text NOT NULL,
  mime_type     text NOT NULL,            -- application/pdf, docx, text/markdown
  source_url    text NOT NULL,            -- URL of the original: Vercel Blob for uploads, canonical source link for the preloaded library
  status        text NOT NULL,            -- processing | ready | failed
  error         text,                     -- failure reason when status=failed
  page_count    int,
  created_at    timestamptz NOT NULL
)

chunks (
  id            uuid PK,
  document_id   uuid FK -> documents ON DELETE CASCADE,
  ordinal       int NOT NULL,             -- position within the document
  content       text NOT NULL,
  embedding     vector(1536) NOT NULL,
  fts           tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
  page_start    int,                      -- PDFs: 1-based page numbers
  page_end      int,
  section_path  text[],                   -- heading trail, e.g. {'Install','Linux'}
  token_count   int NOT NULL
)
-- indexes: HNSW on embedding (cosine), GIN on fts

messages (
  id            uuid PK,
  session_id    uuid NOT NULL,            -- client-generated; groups a chat tab, no sessions table in v1
  role          text NOT NULL,            -- user | assistant
  content       text NOT NULL,
  ip_hash       text,                     -- user rows only: hashed client IP, for rate limiting
  grounded      boolean,                  -- assistant only: false = refused
  confidence    text,                     -- assistant only: high | low
  model         text,                     -- assistant only: provider/model used
  latency_ms    int,
  created_at    timestamptz NOT NULL
)
-- indexes: (session_id, created_at); (ip_hash, created_at) for rate limiting

message_citations (
  message_id    uuid FK -> messages,
  marker        int NOT NULL,             -- [1], [2], ... as shown in the answer
  chunk_id      uuid FK -> chunks,
  score         real NOT NULL,            -- rerank score, kept for threshold tuning + admin display
  PRIMARY KEY (message_id, marker)
)

feedback (
  message_id    uuid PK FK -> messages,
  rating        smallint NOT NULL,        -- +1 | -1
  created_at    timestamptz NOT NULL
)
```

Embedding dimension is fixed at 1536 in v1 (works for `openai/text-embedding-3-small`
and comparable models). Changing embedding models requires re-ingestion; this is
acceptable and documented.

Schema migrations are managed with **Alembic** from day one.

Primary keys default to `uuidv7()` when Neon runs Postgres ≥ 18 (verified in
Milestone 0), else `gen_random_uuid()`. UUIDv7's timestamp prefix keeps B-tree
inserts append-only. External JSON is camelCase (pydantic alias generators);
SQL and Python stay snake_case.

## 5. RAG pipeline

### 5.1 Ingestion

```
browser ──(client upload, token from web app)──► Vercel Blob
   └─► register blob URL with API → API fetches file from Blob → parse
       → structure-preserving chunking → embed (batched)
       → insert chunks → status: ready
```

- **Upload path:** Vercel Functions cap request bodies at **4.5 MB** while
  documents go up to 20 MB — so files never pass through a function. The
  browser uploads directly to Vercel Blob after a token exchange with a
  Next.js route handler (`@vercel/blob` client uploads); the Python API
  receives only the blob URL and fetches the file from Blob.
- **Parsing:** `pdfminer.six` for PDF (page numbers, headings via font-size
  heuristics), `python-docx` for DOCX (heading styles), plain parsing for
  Markdown (heading levels). `pdfminer.six` (MIT) is chosen over `pymupdf`
  (AGPL, a poor fit for an MIT project) and over `pdfplumber` (which wraps
  pdfminer.six but also pulls pypdfium2 + Pillow, bloating the serverless
  bundle past its size limit for capabilities we don't use). No OCR —
  image-only PDFs fail with a clear error.
- **Chunking:** structure-first, not fixed-window. Split on heading boundaries,
  then recursively split oversized sections targeting **~400 tokens with
  ~15% overlap**, never crossing a heading boundary. Every chunk carries
  `page_start/page_end` and `section_path` — this metadata is what makes
  citations precise, and is a deliberate, documented design choice.
- **Embeddings** via AI Gateway, batched; model configured by env var.
- Ingestion executes **within the upload request**, writing `status` updates
  at each stage (the admin UI polls). A fire-and-forget background task is NOT
  safe on serverless — the instance may be recycled once the response is sent,
  stranding documents in `processing`. If a max-size document cannot finish
  within platform duration limits (validated in Milestone 0), that is the
  trigger to move the API to Railway (persistent process, real background
  tasks). Documents are capped at 20 MB / ~300 pages in v1.

### 5.2 Retrieval (hybrid + rerank)

1. **Vector search:** embed the query, cosine top-20 over `chunks.embedding`.
2. **Keyword search:** `websearch_to_tsquery` over `chunks.fts`, top-20 by
   `ts_rank`.
3. **Fusion:** Reciprocal Rank Fusion (k=60) merges both lists → top-12.
4. **Rerank:** listwise LLM rerank via the gateway (a small/cheap model scores
   query↔chunk relevance 0–10) → keep top-5 above score threshold.

Rationale (goes in README too): vector search misses exact identifiers, error
codes, and product names; keyword search misses paraphrase. RRF is
rank-based fusion — no score-scale gymnastics between cosine and ts_rank.
LLM rerank keeps v1 dependency-light (no separate rerank vendor) while staying
swappable behind an interface (`Reranker` protocol) for a cross-encoder later.

### 5.3 Generation & grounding

- Multi-turn: the last N turns of the session are included for conversational
  context; **retrieval runs on a standalone question** rewritten from the
  latest turn (condense step) when history exists.
- The generation prompt receives the top-5 chunks, each tagged `[n]` with its
  document title + page. Rules enforced by prompt + post-check:
  - Every factual sentence must carry at least one `[n]` citation marker.
  - Numbers, dates, and names may ONLY come from the provided chunks.
  - If the chunks don't answer the question → reply with a refusal template
    ("I don't know based on the provided documents") and `grounded=false`.
- **Confidence:** derived from rerank scores. Best score ≥ 7 → high; anything
  retrieved-but-weaker → low (UI shows a "low confidence" badge); nothing above
  threshold 4 → refuse without calling the generator.
- **Citation post-check:** after streaming completes, markers are validated
  against the actual chunk list; unknown markers are stripped and the message
  is flagged. Cited chunk ids are persisted to `message_citations`.

### 5.4 Streaming protocol

`POST /chat` responds with SSE. Event sequence:

```
event: sources   data: {"citations":[{"marker":1,"chunkId":"…","docTitle":"…","page":12,"sectionPath":["Install","Linux"],"sourceUrl":"…","snippet":"…"}], "confidence":"high"}
event: token     data: {"delta":"The install requires"}   (repeated)
event: done      data: {"messageId":"…","grounded":true}
event: error     data: {"type":"…","title":"…","status":500,"detail":"…"}
```

Each citation carries what the source panel renders: `marker` (the `[n]` shown
in the answer), `chunkId`, `docTitle`, `page`, `sectionPath` (heading trail),
`sourceUrl` (the original file — `#page=` appended for PDFs), and `snippet` (the
cited passage). `confidence` is `"high"` or `"low"`, derived from the rerank
scores (§5.3); on a below-threshold refusal the `sources` event carries no
citations.

`sources` is sent **before** tokens so the UI can render citation chips
immediately. The web app proxies this stream through a Next.js route handler
(keeps the API origin private, solves CORS) and adapts it to the Vercel AI SDK
data-stream protocol on the way through.

### 5.5 Latency budget

Target: **first token in < 3s** on the public instance. The critical path is
condense (LLM) → embed → search → rerank (LLM) → generate — three serial
model calls in the worst case. Mitigations are part of the design, not
afterthoughts:

- Vector and keyword searches run **in parallel**.
- The condense step is **skipped when the session has no history** — a
  visitor's first question always takes the fast path (one LLM call less).
- `RERANK_MODEL` defaults to the fastest cheap tier; reranking is a single
  listwise call, never per-chunk calls.
- The `sources` event fires as soon as reranking completes, before generation
  starts — the UI shows citation chips while the answer is still being written.

### 5.6 LangChain usage boundary

LangChain is used at the **component layer**: document loaders, text-splitter
base classes, the embeddings interface. Pipeline orchestration
(retrieve → fuse → rerank → generate) is plain, typed Python functions —
no LCEL chains. Rationale: heavy chain abstractions obscure control flow and
error handling in exactly the code a reader most needs to follow; explicit
orchestration is easier to test and easier to read. This trade-off is
documented in the README design notes.

## 6. API surface (FastAPI)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/chat` | public | Ask a question; SSE stream (5.4) |
| POST | `/feedback` | public | `{messageId, rating: 1\|-1}` |
| GET | `/documents` | public | List ready documents (chat picker shows sources available) |
| POST | `/admin/documents` | admin | Register an uploaded blob `{blobUrl, filename, title}`; ingests synchronously, returns the document row |
| GET | `/admin/documents` | admin | List documents in every status (drives the admin tab's status polling) |
| DELETE | `/admin/documents/{id}` | admin | Delete document + chunks (cascade) + the Blob original |
| GET | `/admin/questions` | admin | Paginated question log with feedback + grounded flag |
| GET | `/admin/stats` | admin | Totals: questions, 👍/👎, refusal rate, docs |
| GET | `/healthz` | public | Liveness + DB connectivity |

- **Errors:** every non-2xx response is RFC 9457 Problem Details
  (`application/problem+json`): `{type, title, status, detail}` plus
  extensions such as `retryAfter`. The SSE `error` event carries the same
  fields. No custom error envelopes.
- **`/chat` request body:** `{sessionId: uuid, message: string}`. The session
  id is generated client-side (one per chat tab); there is no server-side
  session object in v1 — it merely groups `messages` rows for multi-turn
  context and the question log.
- **Internal auth (web → api):** every request from the Next.js proxy carries
  `X-Internal-Key: <INTERNAL_API_KEY>` and the visitor's real IP in
  `X-Client-IP`. The API rejects requests without a valid key and only trusts
  `X-Client-IP` when the key is valid — without this, rate limiting would see
  the proxy's IP and throttle all visitors as one. The Python API is therefore
  effectively private.
- **Admin auth:** `Authorization: Bearer <ADMIN_PASSWORD>` checked by a FastAPI
  dependency. The web admin page stores the password in an httpOnly cookie via
  a Next.js route handler; the browser never calls the Python API directly.
- **Rate limit (public instance):** 20 chat requests / hour / IP, enforced in the
  API. Refusals still count. Counter state lives in Postgres — a count over
  `messages(ip_hash, created_at)` — because in-memory counters are useless
  across serverless instances; no Redis in v1.

## 7. Web app (Next.js)

Routes:

- `/` — chat. Streaming answers; citation chips `[1]` inline; a source panel
  slides open on citation click showing the chunk snippet, document title,
  page number, and a link to the original file (Blob URL + `#page=` for PDFs).
  Low-confidence badge on flagged answers; distinct refusal styling. 👍/👎 on
  every assistant message.
- `/admin` — password gate → tabs: **Documents** (drag-drop direct-to-Blob
  upload, status polling, delete), **Questions** (log with grounded/feedback columns),
  **Stats** (counts + refusal rate; simple cards, no charting library).

Stack: App Router, TypeScript strict, Tailwind, Vercel AI SDK (`useChat` with
a custom data-stream adapter for the `sources` event). No component library
in v1; hand-rolled UI means full control over styling with no dependency weight.

## 8. Configuration

| Env var | Where | Example |
|---|---|---|
| `DATABASE_URL` | api | Neon pooled connection string |
| `GATEWAY_BASE_URL` | api | OpenAI-compatible gateway endpoint (default: Vercel AI Gateway) |
| `GATEWAY_API_KEY` | api | gateway key |
| `INTERNAL_API_KEY` | api + web | shared secret for the web → api hop |
| `CHAT_MODEL` | api | `anthropic/claude-haiku-4-5` (current default) |
| `RERANK_MODEL` | api | `anthropic/claude-haiku-4-5` |
| `EMBEDDING_MODEL` | api | `openai/text-embedding-3-small` |
| `ADMIN_PASSWORD` | api + web | shared secret |
| `BLOB_READ_WRITE_TOKEN` | api + web | Vercel Blob (web issues client-upload tokens; api deletes blobs) |
| `API_URL` | web | Python API origin (server-side only) |

## 9. Testing

Focus: the retrieval pipeline is the product — test it like one.

- **Unit (pytest):** chunker (heading preservation, overlap, page attribution
  across boundaries), RRF fusion, citation post-check, confidence mapping.
- **Integration:** ingestion → retrieval round-trip against a real Postgres
  (docker-compose / Neon branch) with a small fixture document set.
- **Golden retrieval set:** ~15 question→expected-chunk pairs; asserts the
  expected chunk appears in top-5. Guards against chunking/retrieval
  regressions. At M3 the corpus is CiteBear's own self-owned Markdown (SPEC.md,
  README.md, AGENTS.md), which is what is ingestable before the upload pipeline
  (M4); it expands to the full preloaded library at M6. Runs as a
  **manually-triggered workflow and on PRs to main only** — it needs live model
  API keys and costs tokens, so it stays out of the every-push CI loop (unit
  tests cover every push).
- **Web:** type-checked strict; component tests only for citation-marker
  parsing/rendering logic.

## 10. Milestones

| # | Deliverable | Proves |
|---|---|---|
| 0 | Monorepo scaffold; hello-world web + api deployed; Neon provisioned; CI (lint, typecheck, pytest) | Deploy pipeline works; Fluid-vs-Railway decision made via a synthetic long-request test approximating worst-case ingestion |
| 1 | Vertical slice: hardcoded doc → chunks → vector-only retrieval → streamed grounded answer | End-to-end RAG loop live |
| 2 | Citations end-to-end: markers, sources event, source panel with highlight | The flagship feature |
| 3 | Hybrid retrieval + rerank + confidence/refusal; golden retrieval tests | Retrieval depth: exact terms + paraphrase, reranked and cited |
| 4 | Upload pipeline (PDF/DOCX/MD) + admin documents tab | Self-serve ingestion |
| 5 | Question log, feedback, stats; rate limiting; polish | Support-bot story complete |
| 6 | README case study (banner, architecture diagram, design notes, GIF), preloaded library shipped | Complete product: documented and self-hostable |

Each milestone lands as small conventional commits via PR — every commit stays
small, green, and bisectable.

## 11. Preloaded document library (decided 2026-07-02)

Compliance is a hard requirement: no NC/ND clauses anywhere, so the set stays
clean even if the product ever backs commercial work.

| Document | License | Genre it demonstrates |
|---|---|---|
| Calibre User Manual | GPL v3 | Product/support manual |
| The Debian Administrator's Handbook | GPL-2+ / CC BY-SA (dual) | Technical handbook |
| NIST SP 800-63B Digital Identity Guidelines | US-government work, public domain | Enterprise policy/compliance doc |

(Pro Git was considered and dropped: its CC BY-**NC**-SA license would become
ambiguous in commercial contexts.)

Compliance practices: the product UI and README show per-document attribution
(title, authors, license, link to the original); content is shown as
unmodified retrieved excerpts; the license text shipped with each document is
verified at ingestion time. CiteBear's own README/SPEC are also ingested as
Markdown sample content (self-owned, MIT).

## 12. Open questions

1. **Embedding model default** — `text-embedding-3-small` (1536d) is the safe
   default. Gateway embeddings support is confirmed (as of 2026-07 both Vercel
   AI Gateway and OpenRouter expose an embeddings API); the remaining question
   is only whether another model wins on the golden retrieval set.
2. **Chat model default for the public instance** — quality vs. token cost on a
   public, rate-limited endpoint. Interim default: `anthropic/claude-haiku-4-5`
   (cheap, fast); the final choice waits for the golden retrieval set
   (Milestone 3) to compare candidates on real questions.
