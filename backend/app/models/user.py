import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    google_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)

    # Google OAuth tokens (for Calendar API)
    google_access_token: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    google_refresh_token: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # Canvas integration (user-provided)
    canvas_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    canvas_token: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # AI assistant
    ai_preferences: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    onboarding_complete: Mapped[bool] = mapped_column(Boolean, default=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
