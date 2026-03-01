from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.schemas.user import GoogleAuthRequest, UserResponse
from app.services.user_service import create_or_update_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/google", response_model=UserResponse)
async def google_auth(
    auth_data: GoogleAuthRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Handle Google OAuth callback from frontend.
    Creates or updates user with Google tokens.
    """
    user = await create_or_update_user(db, auth_data)

    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        has_canvas=user.canvas_token is not None,
    )
