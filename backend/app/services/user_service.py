from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.schemas.user import GoogleAuthRequest


async def get_user_by_google_id(db: AsyncSession, google_id: str) -> Optional[User]:
    """Find a user by their Google ID."""
    result = await db.execute(
        select(User).where(User.google_id == google_id)
    )
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: str) -> Optional[User]:
    """Find a user by their ID."""
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    return result.scalar_one_or_none()


async def create_or_update_user(db: AsyncSession, auth_data: GoogleAuthRequest) -> User:
    """Create a new user or update existing user with fresh tokens."""
    user = await get_user_by_google_id(db, auth_data.google_id)

    if user:
        # Update existing user's tokens
        user.email = auth_data.email
        user.name = auth_data.name
        user.google_access_token = auth_data.access_token
        if auth_data.refresh_token:
            user.google_refresh_token = auth_data.refresh_token
    else:
        # Create new user
        user = User(
            email=auth_data.email,
            name=auth_data.name,
            google_id=auth_data.google_id,
            google_access_token=auth_data.access_token,
            google_refresh_token=auth_data.refresh_token,
        )
        db.add(user)

    await db.commit()
    await db.refresh(user)
    return user
