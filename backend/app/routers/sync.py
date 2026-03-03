from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.user import User
from app.services.user_service import get_user_by_id
from sqlalchemy import select

from app.models.task import Task
from app.services.sync_service import (
    sync_canvas_tasks,
    sync_calendar_events,
    get_user_tasks,
    get_user_events,
)
from app.services.estimation_service import estimate_task_duration
from app.services.constraint_service import (
    get_user_constraints,
    create_default_constraints,
    has_constraints,
)

router = APIRouter(prefix="/sync", tags=["sync"])


class SyncResponse(BaseModel):
    created: int
    updated: int
    message: str


async def get_current_user(
    user_id: str = Query(..., description="User ID"),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post("/canvas", response_model=SyncResponse)
async def sync_canvas(
    use_llm: bool = Query(default=False, description="Use GPT-4o-mini for estimation (costs tokens)"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Sync assignments from Canvas to Tasks. Uses rule-based estimation by default."""
    try:
        created, updated = await sync_canvas_tasks(db, user, use_llm=use_llm)
        return SyncResponse(
            created=created,
            updated=updated,
            message=f"Synced Canvas: {created} new tasks, {updated} updated",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/calendar", response_model=SyncResponse)
async def sync_calendar(
    weeks: int = Query(default=4, ge=1, le=12),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Sync events from Google Calendar to Events."""
    try:
        created, updated = await sync_calendar_events(db, user, weeks)
        return SyncResponse(
            created=created,
            updated=updated,
            message=f"Synced Calendar: {created} new events, {updated} updated",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/all", response_model=dict)
async def sync_all(
    weeks: int = Query(default=4, ge=1, le=12),
    use_llm: bool = Query(default=False, description="Use GPT-4o-mini for estimation (costs tokens)"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Sync both Canvas and Calendar. Uses rule-based estimation by default."""
    results = {}

    # Sync Canvas if connected
    if user.canvas_url and user.canvas_token:
        try:
            canvas_created, canvas_updated = await sync_canvas_tasks(db, user, use_llm=use_llm)
            results["canvas"] = {
                "created": canvas_created,
                "updated": canvas_updated,
            }
        except Exception as e:
            results["canvas"] = {"error": str(e)}
    else:
        results["canvas"] = {"skipped": "Canvas not connected"}

    # Sync Calendar
    try:
        cal_created, cal_updated = await sync_calendar_events(db, user, weeks)
        results["calendar"] = {
            "created": cal_created,
            "updated": cal_updated,
        }
    except Exception as e:
        results["calendar"] = {"error": str(e)}

    # Ensure default constraints exist
    if not await has_constraints(db, user.id):
        await create_default_constraints(db, user.id)
        results["constraints"] = {"created": "default constraints"}

    return results


@router.get("/tasks")
async def list_tasks(
    include_completed: bool = Query(default=False),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all synced tasks for the user."""
    tasks = await get_user_tasks(db, user.id, include_completed)
    return {
        "tasks": [
            {
                "id": str(t.id),
                "name": t.name,
                "course_name": t.course_name,
                "due_at": t.due_at.isoformat() if t.due_at else None,
                "points_possible": t.points_possible,
                "estimated_minutes": t.effective_minutes,
                "user_estimated_minutes": t.user_estimated_minutes,
                "estimation_reasoning": t.estimation_reasoning,
                "status": t.status.value,
            }
            for t in tasks
        ],
        "count": len(tasks),
    }


@router.get("/events")
async def list_events(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all synced events for the user."""
    events = await get_user_events(db, user.id)
    return {
        "events": [
            {
                "id": str(e.id),
                "title": e.title,
                "start": e.start.isoformat(),
                "end": e.end.isoformat(),
                "all_day": e.all_day,
                "event_type": e.event_type.value,
            }
            for e in events
        ],
        "count": len(events),
    }


@router.get("/constraints")
async def list_constraints(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all constraints for the user."""
    # Create defaults if none exist
    if not await has_constraints(db, user.id):
        await create_default_constraints(db, user.id)

    constraints = await get_user_constraints(db, user.id)
    return {
        "constraints": [
            {
                "id": str(c.id),
                "type": c.constraint_type.value,
                "name": c.name,
                "days_of_week": c.days_of_week,
                "start_time": c.start_time.isoformat() if c.start_time else None,
                "end_time": c.end_time.isoformat() if c.end_time else None,
                "max_minutes": c.max_minutes,
                "is_active": c.is_active,
            }
            for c in constraints
        ],
        "count": len(constraints),
    }


@router.post("/tasks/{task_id}/estimate")
async def estimate_single_task(
    task_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Re-estimate a single task using GPT-4o-mini.
    Use this to test LLM estimation on specific tasks.
    """
    # Get the task
    result = await db.execute(
        select(Task)
        .where(Task.id == task_id)
        .where(Task.user_id == user.id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Get LLM estimate
    estimated_minutes, reasoning = await estimate_task_duration(
        name=task.name,
        course_name=task.course_name,
        description=task.description,
        points_possible=task.points_possible,
        submission_types=task.submission_types,
    )

    # Update task with new estimate
    task.estimated_minutes = estimated_minutes
    task.estimation_reasoning = reasoning
    await db.commit()

    return {
        "task_id": str(task.id),
        "name": task.name,
        "course_name": task.course_name,
        "points_possible": task.points_possible,
        "old_estimate": task.effective_minutes,
        "new_estimate": estimated_minutes,
        "reasoning": reasoning,
    }
