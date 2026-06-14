from fastapi import APIRouter

from app.api.routes import login, private, repositories, sessions, users, utils
from app.core.config import settings

api_router = APIRouter()
api_router.include_router(login.router)
api_router.include_router(users.router)
api_router.include_router(utils.router)
api_router.include_router(sessions.router)
api_router.include_router(repositories.router)

if settings.ENVIRONMENT == "local":
    api_router.include_router(private.router)
