from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Cookie, Depends, HTTPException, Response, status
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database import get_db
from app.models import User

password_hash = PasswordHash.recommended()
settings = get_settings()

def create_session(response: Response, user: User) -> None:
    token = jwt.encode({"sub": str(user.id), "exp": datetime.now(UTC) + timedelta(days=7)}, settings.session_secret, algorithm="HS256")
    response.set_cookie("edutool_session", token, httponly=True, samesite="lax", secure=settings.cookie_secure, max_age=604800)

def current_user(edutool_session: str | None = Cookie(default=None), db: Session = Depends(get_db)) -> User:
    error = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    if not edutool_session:
        raise error
    try:
        user_id = int(jwt.decode(edutool_session, settings.session_secret, algorithms=["HS256"])["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise error
    user = db.get(User, user_id)
    if not user:
        raise error
    return user