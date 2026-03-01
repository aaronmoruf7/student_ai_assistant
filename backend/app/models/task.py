import uuid
from datetime import datetime
from typing import Optional, List

from sqlalchemy import String, DateTime, Integer, Float, ForeignKey, JSON, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.db.database import Base


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)

    # Canvas source data
    canvas_assignment_id: Mapped[int] = mapped_column(Integer, index=True)
    canvas_course_id: Mapped[int] = mapped_column(Integer)

    # Task details
    name: Mapped[str] = mapped_column(String(500))
    course_name: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    points_possible: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    submission_types: Mapped[List[str]] = mapped_column(JSON, default=list)

    # Effort estimation
    estimated_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # LLM/rule-based
    user_estimated_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # User override
    estimation_reasoning: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)  # LLM explanation

    # Status
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus),
        default=TaskStatus.PENDING,
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    @property
    def effective_minutes(self) -> Optional[int]:
        """Returns user estimate if set, otherwise LLM estimate."""
        return self.user_estimated_minutes or self.estimated_minutes
