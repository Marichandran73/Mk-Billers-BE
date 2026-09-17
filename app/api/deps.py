from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from starlette.requests import Request
from sqlalchemy.orm import Session, joinedload

from app.core.security import decode_token
from app.database.connection import get_db
from app.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    try:
        payload = decode_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from exc
    email = str(payload.get("sub"))
    company_id = int(payload.get("company_id", 0))
    user = (
        db.query(User)
        .options(joinedload(User.company))
        .filter(User.email == email, User.company_id == company_id)
        .first()
    )
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if not user.is_active and request.method.upper() != "GET":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User access is inactive for write actions. Contact support.",
        )
    return user


def require_active_admin_company(user: User = Depends(get_current_user)) -> User:
    if user.role.upper() == "ADMIN" and not user.company.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to create user or report",
        )
    return user


def require_admin_or_super(user: User = Depends(get_current_user)) -> User:
    role = user.role.upper()
    if role == "STAFF":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to perform this action",
        )
    if role == "ADMIN" and not user.company.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to create user or report",
        )
    return user
