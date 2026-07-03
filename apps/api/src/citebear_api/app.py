from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from citebear_api.config import get_settings
from citebear_api.db import get_session


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    get_settings()  # missing config fails the boot, not the request
    yield


app = FastAPI(title="CiteBear API", version="0.1.0", lifespan=lifespan)


@app.get("/healthz")
async def healthz(session: Annotated[AsyncSession, Depends(get_session)]) -> dict[str, str]:
    """Liveness probe with database connectivity check."""
    await session.execute(text("SELECT 1"))
    return {"status": "ok"}
