import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Boolean, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column
import enum

from app.db.database import Base


class EventType(str, enum.Enum):
    CLASS = "class"
    PERSONAL = "personal"
    WORK = "work"
    OTHER = "other"


class Event(Base):
    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)

    # Google Calendar source
    google_event_id: Mapped[str] = mapped_column(String(255), index=True)
    calendar_id: Mapped[str] = mapped_column(String(255), default="primary")

    # Event details
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    all_day: Mapped[bool] = mapped_column(Boolean, default=False)

    # Classification (can be inferred or user-set)
    event_type: Mapped[EventType] = mapped_column(
        Enum(EventType),
        default=EventType.OTHER,
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
