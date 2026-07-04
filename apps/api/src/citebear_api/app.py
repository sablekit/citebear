from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from citebear_api.admin_login import router as admin_login_router
from citebear_api.chat import router as chat_router
from citebear_api.config import get_settings
from citebear_api.db import get_session
from citebear_api.documents import router as documents_router
from citebear_api.feedback import router as feedback_router
from citebear_api.problems import install_problem_handlers
from citebear_api.questions import router as questions_router
from citebear_api.stats import router as stats_router


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    get_settings()  # missing config fails the boot, not the request
    yield


app = FastAPI(title="CiteBear API", version="0.1.0", lifespan=lifespan)
install_problem_handlers(app)
app.include_router(chat_router)
app.include_router(documents_router)
app.include_router(feedback_router)
app.include_router(admin_login_router)
app.include_router(questions_router)
app.include_router(stats_router)


@app.get("/healthz")
async def healthz(session: Annotated[AsyncSession, Depends(get_session)]) -> dict[str, str]:
    """Liveness probe with database connectivity check."""
    await session.execute(text("SELECT 1"))
    return {"status": "ok"}
