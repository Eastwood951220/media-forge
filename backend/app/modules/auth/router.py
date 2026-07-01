import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.core.dependencies import get_db
from backend.app.core.security import create_access_token, verify_password
from backend.app.repositories.user import UserRepository
from backend.app.schemas.auth import LoginRequest, TokenResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user_repo = UserRepository(db)
    user = user_repo.get_by_username(request.username)

    if user is None or not verify_password(request.password, user.hashed_password):
        logger.warning("Failed login attempt for username: %s", request.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    access_token = create_access_token(data={"sub": user.username})

    logger.info("User logged in: %s", user.username)

    return TokenResponse(access_token=access_token)


@router.post("/logout")
def logout() -> dict[str, str]:
    # Stateless JWT — client discards token.
    return {"message": "Logged out"}
