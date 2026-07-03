"""Golden retrieval set (SPEC §9).

Each pair is ``(question, expected)``: asking ``question`` must surface a chunk
whose content contains ``expected`` in the reranked top-5. The corpus at M3 is
CiteBear's own self-owned Markdown (SPEC.md, README.md, AGENTS.md); it expands
to the full preloaded library at M6.

The set deliberately mixes exact-term questions (which lean on keyword search —
`X-Internal-Key`, `feat/kebab-case`, `text-embedding-3-small`) with paraphrase
questions (which lean on vector search), so a regression in either retrieval arm
shows up here.
"""

# (question, expected substring in the target chunk)
GOLDEN: list[tuple[str, str]] = [
    (
        "How are the vector and keyword result lists combined into one ranking?",
        "Reciprocal Rank Fusion",
    ),
    ("What is the latency target for the first token of an answer?", "first token in < 3s"),
    ("What is the default embedding model?", "text-embedding-3-small"),
    ("Does the system read scanned PDFs with OCR?", "OCR for scanned PDFs"),
    ("How does the Next.js proxy authenticate to the Python API?", "X-Internal-Key"),
    (
        "What can happen to a document if a serverless instance is recycled mid-ingestion?",
        "stranding documents",
    ),
    (
        "What kind of connection string does DATABASE_URL hold in production?",
        "Neon pooled connection string",
    ),
    ("What is the sanctioned fallback host if Fluid Compute struggles?", "sanctioned fallback"),
    (
        "Why does the pipeline orchestrate retrieval with plain functions instead of LCEL chains?",
        "component layer",
    ),
    ("What is the branch naming convention for this repo?", "feat/kebab-case"),
    ("Who is the maintainer of CiteBear?", "Henry Jia"),
    ("In what order does the streaming protocol send its events?", "event: sources"),
    ("When does the assistant refuse to answer based on the rerank score?", "threshold 4"),
    ("Which documents are in the preloaded library?", "Calibre User Manual"),
    ("How does CiteBear guard against retrieval regressions?", "Golden retrieval set"),
]
