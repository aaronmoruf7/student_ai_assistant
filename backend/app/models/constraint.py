import uuid
from datetime import datetime, time
from typing import Optional, List

from sqlalchemy import String, DateTime, Time, Integer, Boolean, ForeignKey, JSON, Enum
from sqlalchemy.orm import Mapped, mapped_column
import enum

from app.db.database import Base


class ConstraintType(str, enum.Enum):
    SLEEP = "sleep"  # e.g., 11pm - 7am no scheduling
    MEAL = "meal"  # e.g., 12pm - 1pm lunch
    MAX_HOURS_PER_DAY = "max_hours_per_day"  # e.g., max 6 hours of study
    BLOCKED_TIME = "blocked_time"  # custom blocked periods


class Constraint(Base):
    __tablename__ = "constraints"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)

    # Constraint definition
    constraint_type: Mapped[ConstraintType] = mapped_column(Enum(ConstraintType))
    name: Mapped[str] = mapped_column(String(255))  # e.g., "Sleep", "Lunch break"

    # Time-based constraints (for sleep, meal, blocked_time)
    # Days: 0=Monday, 6=Sunday
    days_of_week: Mapped[Optional[List[int]]] = mapped_column(
        JSON, nullable=True, default=lambda: [0, 1, 2, 3, 4, 5, 6]
    )
    start_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    end_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)

    # For max_hours_per_day constraint
    max_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Active toggle
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
