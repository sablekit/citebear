from fastapi import FastAPI

app = FastAPI(title="CiteBear API", version="0.1.0")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness probe. DB connectivity check lands with the schema in Milestone 1."""
    return {"status": "ok"}
