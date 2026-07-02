import asyncio
import hashlib
import time
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

app = FastAPI(title="CiteBear API", version="0.1.0")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness probe. DB connectivity check lands with the schema in Milestone 1."""
    return {"status": "ok"}


@app.get("/_internal/synthetic-load")
def synthetic_load(seconds: int = 60) -> StreamingResponse:
    """TEMPORARY Milestone-0 gate — remove after the Fluid-vs-Railway decision.

    Approximates worst-case ingestion: short CPU bursts (parsing-like) between
    I/O waits (embedding-API-like), streaming a heartbeat so the connection
    stays alive and platform buffering would be visible.
    """
    capped = min(max(seconds, 1), 290)

    async def run() -> AsyncIterator[bytes]:
        start = time.monotonic()
        cpu_total = 0.0
        tick = 0
        while time.monotonic() - start < capped:
            t0 = time.monotonic()
            while time.monotonic() - t0 < 0.2:
                _ = hashlib.sha256(b"citebear" * 1000).hexdigest()
            cpu_total += time.monotonic() - t0
            await asyncio.sleep(0.8)
            tick += 1
            if tick % 10 == 0:
                yield f"tick {tick} elapsed={time.monotonic() - start:.0f}s\n".encode()
        yield (
            f"done requested={capped}s elapsed={time.monotonic() - start:.1f}s "
            f"cpu={cpu_total:.1f}s\n"
        ).encode()

    return StreamingResponse(run(), media_type="text/plain")
