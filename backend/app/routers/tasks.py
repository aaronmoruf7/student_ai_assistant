"""
Tasks router — CRUD for the persistent task table.

Endpoints:
  GET    /tasks              → list all tasks for user, grouped by course
  POST   /tasks              → create a manual task
  PATCH  /tasks/{task_id}   → update name, due_at, user_estimated_minutes, status
  DELETE /tasks/{task_id}   → delete a task
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.course import Course
from app.models.task import Task, TaskSource, TaskStatus
from app.models.user import User
from app.models.workblock import WorkBlock
from app.services.user_service import get_user_by_id

router = APIRouter(prefix="/tasks", tags=["tasks"])


# ---------------------------------------------------------------------------
# Shared dependency
# ---------------------------------------------------------------------------

async def get_current_user(
    user_id: str = Query(..., description="User ID"),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class TaskResponse(BaseModel):
    id: str
    name: str
    course_name: str
    course_id: Optional[str]
    due_at: Optional[str]
    source: str
    estimated_minutes: Optional[int]
    user_estimated_minutes: Optional[int]
    status: str
    confidence: Optional[float]

    class Config:
        from_attributes = True


class CreateTaskRequest(BaseModel):
    name: str
    course_id: str                      # internal UUID of the Course
    due_at: Optional[str] = None        # ISO string or null
    user_estimated_minutes: Optional[int] = None


class UpdateTaskRequest(BaseModel):
    name: Optional[str] = None
    due_at: Optional[str] = None        # ISO string, empty string = clear it, null = no-op
    user_estimated_minutes: Optional[int] = None
    completed_minutes: Optional[int] = None
    status: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _task_to_dict(task: Task) -> dict:
    return {
        "id": str(task.id),
        "name": task.name,
        "course_name": task.course_name,
        "course_id": str(task.course_id) if task.course_id else None,
        "due_at": task.due_at.isoformat() if task.due_at else None,
        "source": task.source.value,
        "estimated_minutes": task.estimated_minutes,
        "user_estimated_minutes": task.user_estimated_minutes,
        "completed_minutes": task.completed_minutes or 0,
        "remaining_minutes": task.remaining_minutes,
        "status": task.status.value,
        "confidence": task.confidence,
    }


def _parse_due_at(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid due_at format: {value}")


# ---------------------------------------------------------------------------
# GET /tasks
# ---------------------------------------------------------------------------

@router.get("")
async def list_tasks(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns all tasks for the user, grouped by course.
    """
    result = await db.execute(
        select(Task)
        .where(Task.user_id == user.id)
        .order_by(Task.course_name, Task.due_at.asc().nulls_last())
    )
    tasks = result.scalars().all()

    # Group by course_name
    groups: dict[str, list] = {}
    for task in tasks:
        groups.setdefault(task.course_name, []).append(_task_to_dict(task))

    return {
        "groups": [
            {"course_name": course, "tasks": task_list}
            for course, task_list in groups.items()
        ],
        "total": len(tasks),
    }


# ---------------------------------------------------------------------------
# POST /tasks
# ---------------------------------------------------------------------------

@router.post("")
async def create_task(
    request: CreateTaskRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a manual task.
    """
    # Verify the course belongs to this user
    course_uuid = uuid.UUID(request.course_id)
    result = await db.execute(
        select(Course)
        .where(Course.id == course_uuid)
        .where(Course.user_id == user.id)
    )
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    task = Task(
        user_id=user.id,
        course_id=course.id,
        name=request.name,
        course_name=course.name,
        due_at=_parse_due_at(request.due_at),
        user_estimated_minutes=request.user_estimated_minutes,
        submission_types=[],
        source=TaskSource.MANUAL,
        status=TaskStatus.PENDING,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    return _task_to_dict(task)


# ---------------------------------------------------------------------------
# PATCH /tasks/{task_id}
# ---------------------------------------------------------------------------

@router.patch("/{task_id}")
async def update_task(
    task_id: str,
    request: UpdateTaskRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update name, due_at, user_estimated_minutes, or status.
    Only provided fields are changed.
    """
    result = await db.execute(
        select(Task)
        .where(Task.id == uuid.UUID(task_id))
        .where(Task.user_id == user.id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if request.name is not None:
        task.name = request.name

    # due_at: empty string clears it, a real value sets it, None = no change
    if request.due_at is not None:
        task.due_at = None if request.due_at == "" else _parse_due_at(request.due_at)

    if request.user_estimated_minutes is not None:
        task.user_estimated_minutes = request.user_estimated_minutes

    if request.completed_minutes is not None:
        task.completed_minutes = max(0, request.completed_minutes)

    if request.status is not None:
        try:
            task.status = TaskStatus(request.status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {request.status}")

    task.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(task)

    return _task_to_dict(task)


# ---------------------------------------------------------------------------
# DELETE /tasks/{task_id}
# ---------------------------------------------------------------------------

@router.delete("/{task_id}")
async def delete_task(
    task_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Task)
        .where(Task.id == uuid.UUID(task_id))
        .where(Task.user_id == user.id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Delete associated work blocks first to avoid FK violation
    blocks_result = await db.execute(
        select(WorkBlock).where(WorkBlock.task_id == task.id)
    )
    for block in blocks_result.scalars().all():
        await db.delete(block)

    await db.delete(task)
    await db.commit()

    return {"deleted": task_id}
