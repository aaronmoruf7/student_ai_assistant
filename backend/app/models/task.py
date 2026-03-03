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


class TaskSource(str, enum.Enum):
    CANVAS = "canvas"       # Synced directly from Canvas
    EXTRACTED = "extracted" # LLM-extracted from pasted syllabus/content
    MANUAL = "manual"       # User-added manually


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)

    # Course FK (links to our Course record)
    course_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("courses.id"), nullable=True, index=True
    )

    # Canvas source data (nullable — extracted/manual tasks won't have these)
    canvas_assignment_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    canvas_course_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Task details
    name: Mapped[str] = mapped_column(String(500))
    course_name: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    points_possible: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    submission_types: Mapped[List[str]] = mapped_column(JSON, default=list)

    # Source tracking
    source: Mapped[TaskSource] = mapped_column(
        Enum(TaskSource, values_callable=lambda x: [e.value for e in x]),
        default=TaskSource.CANVAS,
    )

    # Confidence score for LLM-extracted tasks (0.0–1.0)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # For undated Canvas assignments: the cluster label (e.g. "Lecture Quiz")
    task_type_label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Effort estimation
    estimated_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    user_estimated_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    estimation_reasoning: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    # Partial completion tracking
    completed_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)

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

    @property
    def remaining_minutes(self) -> Optional[int]:
        """Effective estimate minus however much is already done."""
        total = self.effective_minutes
        if total is None:
            return None
        done = self.completed_minutes or 0
        return max(0, total - done)
