from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.schemas.user import GoogleAuthRequest, UserResponse
from app.services.user_service import create_or_update_user, get_user_by_id


class SavePreferencesRequest(BaseModel):
    ai_preferences: str

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


@router.get("/profile")
async def get_user_profile(
    user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Return basic user profile including saved AI preferences."""
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "name": user.name,
        "email": user.email,
        "ai_preferences": user.ai_preferences,
    }


@router.patch("/profile")
async def save_user_preferences(
    request: SavePreferencesRequest,
    user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Save AI preferences text for the user."""
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.ai_preferences = request.ai_preferences.strip()
    user.updated_at = datetime.utcnow()
    await db.commit()
    return {"saved": True}
