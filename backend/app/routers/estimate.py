"""
Estimate router — type-based bulk estimation of task effort.

Flow:
  GET  /estimate  → per course, return task types (clustered by name pattern).
                    On first visit, runs LLM clustering and saves task_type_label
                    to each task. On return visits, reads saved labels.
  POST /estimate  → apply hours-per-type, writing user_estimated_minutes to all
                    matching tasks.
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.course import Course
from app.models.task import Task
from app.models.user import User
from app.services.clustering_service import cluster_tasks_for_estimation
from app.services.user_service import get_user_by_id

router = APIRouter(prefix="/estimate", tags=["estimate"])


# ---------------------------------------------------------------------------
# Shared dependency
# ---------------------------------------------------------------------------

async def get_current_user(
    user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class TaskTypeGroup(BaseModel):
    type_label: str
    representative: str
    count: int
    examples: list[str]


class CourseEstimateGroup(BaseModel):
    course_id: str
    course_name: str
    types: list[TaskTypeGroup]


class EstimateEntry(BaseModel):
    course_id: str
    type_label: str
    minutes: int


class ApplyEstimatesRequest(BaseModel):
    estimates: list[EstimateEntry]


# ---------------------------------------------------------------------------
# GET /estimate
# ---------------------------------------------------------------------------

@router.get("")
async def get_estimate_groups(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns task types per course for estimation.

    First visit: runs LLM clustering on unlabelled tasks, saves task_type_label to DB.
    Return visit: reads saved labels directly — no re-clustering.
    """
    # Load all user courses
    courses_result = await db.execute(
        select(Course).where(Course.user_id == user.id)
    )
    courses = courses_result.scalars().all()
    if not courses:
        return {"courses": []}

    course_map = {c.id: c for c in courses}

    # Load all tasks for this user that belong to a course
    tasks_result = await db.execute(
        select(Task)
        .where(Task.user_id == user.id)
        .where(Task.course_id.is_not(None))
        .order_by(Task.course_id, Task.name)
    )
    all_tasks = tasks_result.scalars().all()

    # Group tasks by course
    by_course: dict[uuid.UUID, list[Task]] = {}
    for task in all_tasks:
        by_course.setdefault(task.course_id, []).append(task)

    response_courses = []
    needs_commit = False

    for course_id, tasks in by_course.items():
        course = course_map.get(course_id)
        if not course:
            continue

        # Separate labelled vs unlabelled tasks
        unlabelled = [t for t in tasks if not t.task_type_label]

        if unlabelled:
            # Run clustering on unlabelled tasks only
            task_dicts = [
                {"id": str(t.id), "name": t.name, "course_name": course.name}
                for t in unlabelled
            ]
            clusters = await cluster_tasks_for_estimation(task_dicts)

            # Save the label back to each task
            id_to_label = {}
            for cluster in clusters:
                for tid in cluster["task_ids"]:
                    id_to_label[tid] = cluster["type_label"]

            for task in unlabelled:
                label = id_to_label.get(str(task.id))
                if label:
                    task.task_type_label = label
                    needs_commit = True

        # Now group ALL tasks for this course by label
        label_groups: dict[str, list[Task]] = {}
        for task in tasks:
            label = task.task_type_label or "Other"
            label_groups.setdefault(label, []).append(task)

        type_groups = []
        for label, group_tasks in label_groups.items():
            type_groups.append(TaskTypeGroup(
                type_label=label,
                representative=group_tasks[0].name,
                count=len(group_tasks),
                examples=[t.name for t in group_tasks[:3]],
            ))

        response_courses.append(CourseEstimateGroup(
            course_id=str(course_id),
            course_name=course.name,
            types=type_groups,
        ))

    if needs_commit:
        await db.commit()

    return {"courses": [c.model_dump() for c in response_courses]}


# ---------------------------------------------------------------------------
# POST /estimate
# ---------------------------------------------------------------------------

@router.post("")
async def apply_estimates(
    request: ApplyEstimatesRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Applies hours-per-type to all matching tasks.
    Overwrites user_estimated_minutes on every task in that course+type.
    """
    total_updated = 0

    for entry in request.estimates:
        if entry.minutes <= 0:
            continue

        try:
            course_uuid = uuid.UUID(entry.course_id)
        except ValueError:
            continue

        result = await db.execute(
            select(Task)
            .where(Task.user_id == user.id)
            .where(Task.course_id == course_uuid)
            .where(Task.task_type_label == entry.type_label)
        )
        tasks = result.scalars().all()

        for task in tasks:
            task.user_estimated_minutes = entry.minutes
            total_updated += 1

    await db.commit()

    return {
        "tasks_updated": total_updated,
        "message": f"Applied estimates to {total_updated} tasks",
    }
