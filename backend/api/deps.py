from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_db
from shared.config import settings
from .routers.auth import _SESSIONS, _USERS


async def require_auth(request: Request) -> dict:
    token = request.cookies.get(settings.session_cookie_name)
    if not token or token not in _SESSIONS:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return _USERS[_SESSIONS[token]]


async def get_session(db: AsyncSession = Depends(get_db)) -> AsyncSession:
    return db
