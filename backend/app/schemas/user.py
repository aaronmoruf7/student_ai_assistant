from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr


class GoogleAuthRequest(BaseModel):
    """Request from frontend after Google OAuth completes."""
    google_id: str
    email: EmailStr
    name: str
    access_token: str
    refresh_token: Optional[str] = None


class UserResponse(BaseModel):
    """User data returned to frontend."""
    id: UUID
    email: str
    name: str
    has_canvas: bool

    class Config:
        from_attributes = True
