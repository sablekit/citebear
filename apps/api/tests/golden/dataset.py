"""Golden retrieval set (SPEC §9).

Each pair is ``(question, expected)``: asking ``question`` must surface a chunk
whose content contains ``expected`` in the reranked top-5.

Two corpora, each with its own workflow job (SPEC §9):

* ``GOLDEN`` — CiteBear's own self-owned Markdown (SPEC.md, README.md,
  AGENTS.md). Hermetic and cheap, so it gates every PR to main.
* ``GOLDEN_LIBRARY`` — the preloaded library (Calibre / Debian / NIST). These
  are large external PDFs, so this set runs only on the manual library job.

Both sets deliberately mix exact-term questions (which lean on keyword search —
`X-Internal-Key`, `/etc/apt/sources.list`, `eight characters`) with paraphrase
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

# Golden pairs over the preloaded library (SPEC §11): Calibre User Manual,
# The Debian Administrator's Handbook, NIST SP 800-63B-4. Same exact/paraphrase
# mix, over real third-party content the reranker must still surface.
GOLDEN_LIBRARY: list[tuple[str, str]] = [
    ("What is calibre?", "e-book library manager"),
    (
        "Can a book be converted from one e-book format to another?",
        "converted from a number of formats",
    ),
    (
        "What does the calibre graphical user interface provide access to?",
        "library management and e-book format conversion",
    ),
    ("What is the base command for handling Debian packages?", "dpkg is the base command"),
    ("Which file lists the package sources APT uses?", "/etc/apt/sources.list"),
    ("What does APT stand for?", "Advanced Package Tool"),
    ("What is a multi-factor authenticator?", "more than one distinct authentication factor"),
    ("What is the minimum length NIST requires for a memorized secret?", "eight characters"),
    (
        "Who is a subscriber in NIST's digital identity model?",
        "enrolled in the CSP identity service",
    ),
]
