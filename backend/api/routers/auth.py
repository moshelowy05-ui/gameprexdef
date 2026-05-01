from fastapi import APIRouter, HTTPException, Response, Request
from pydantic import BaseModel
from passlib.context import CryptContext
import uuid

from shared.config import settings

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# In-memory user store for Phase 0 — replace with DB in Phase 1
_USERS: dict[str, dict] = {
    "nca": {
        "username": "nca",
        "hashed_password": pwd_context.hash("gameprex2024"),
        "role": "NCA",
        "display_name": "National Command Authority",
    }
}
_SESSIONS: dict[str, str] = {}  # session_token -> username


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    username: str
    display_name: str
    role: str


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest, response: Response) -> LoginResponse:
    user = _USERS.get(req.username)
    if not user or not pwd_context.verify(req.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = str(uuid.uuid4())
    _SESSIONS[token] = req.username

    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_max_age,
        httponly=True,
        samesite="lax",
    )
    return LoginResponse(
        username=user["username"],
        display_name=user["display_name"],
        role=user["role"],
    )


@router.post("/logout")
async def logout(request: Request, response: Response) -> dict:
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        _SESSIONS.pop(token, None)
    response.delete_cookie(settings.session_cookie_name)
    return {"status": "logged_out"}


@router.get("/me", response_model=LoginResponse)
async def me(request: Request) -> LoginResponse:
    token = request.cookies.get(settings.session_cookie_name)
    if not token or token not in _SESSIONS:
        raise HTTPException(status_code=401, detail="Not authenticated")
    username = _SESSIONS[token]
    user = _USERS[username]
    return LoginResponse(
        username=user["username"],
        display_name=user["display_name"],
        role=user["role"],
    )
