"""HTTP API package; the aggregate router is re-exported as one import surface."""

from app.api.main import api_router

__all__ = ["api_router"]
