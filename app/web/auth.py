"""HTTP Basic Auth for the admin web panel (SPEC §11)."""

from __future__ import annotations

import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.core.config import settings
from app.db.models.user import User
from app.services.house_shop import is_admin
from app.web.storefront.deps import current_user

security = HTTPBasic(auto_error=False)


def require_admin(
    credentials: HTTPBasicCredentials | None = Depends(security),
    user: User | None = Depends(current_user),
) -> str:
    if is_admin(user) and user is not None and user.tg_id is not None:
        return str(user.tg_id)
    valid_user = credentials is not None and secrets.compare_digest(
        credentials.username, settings.admin_basic_auth_user
    )
    valid_pass = credentials is not None and secrets.compare_digest(
        credentials.password, settings.admin_basic_auth_password
    )
    if not (valid_user and valid_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username if credentials is not None else ""
