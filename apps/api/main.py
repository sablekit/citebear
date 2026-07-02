"""Vercel entrypoint - exposes the FastAPI app object."""

from citebear_api.app import app

__all__ = ["app"]
