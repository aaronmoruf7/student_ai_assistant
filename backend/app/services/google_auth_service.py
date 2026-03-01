import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User


async def refresh_google_token(db: AsyncSession, user: User) -> str:
    """
    Refresh the user's Google access token using their refresh token.
    Updates the database with the new access token.
    Returns the new access token.
    """
    if not user.google_refresh_token:
        raise ValueError("No refresh token available for user")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "refresh_token": user.google_refresh_token,
                "grant_type": "refresh_token",
            },
        )

        if response.status_code != 200:
            raise ValueError(f"Failed to refresh token: {response.text}")

        tokens = response.json()
        new_access_token = tokens["access_token"]

        # Update user's access token in database
        user.google_access_token = new_access_token
        await db.commit()

        return new_access_token
