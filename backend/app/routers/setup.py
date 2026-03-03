"""
Setup router — handles the one-time per-semester course setup flow.

Flow:
  1. GET  /setup/courses              → list Canvas courses + saved selection state
  2. POST /setup/courses/select       → save selected courses + import dated Canvas tasks
  3. GET  /setup/undated              → undated Canvas assignments, clustered by type
  4. POST /setup/undated/confirm      → confirm which types are real → save as Tasks
  5. POST /setup/courses/{id}/extract → LLM-extract tasks from pasted content (preview)
  6. POST /setup/courses/{id}/tasks/confirm → save confirmed extracted tasks
"""
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.course import Course
from app.models.task import Task, TaskSource, TaskStatus
from app.models.user import User
from app.services.canvas_service import fetch_courses, fetch_assignments, fetch_undated_assignments
from app.services.clustering_service import cluster_undated_assignments
from app.services.extraction_service import extract_tasks_from_content
from app.services.estimation_service import _rule_based_estimate
from app.services.user_service import get_user_by_id

router = APIRouter(prefix="/setup", tags=["setup"])


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
# Request / Response schemas
# ---------------------------------------------------------------------------

class CourseWithStatus(BaseModel):
    canvas_course_id: int
    name: str
    code: Optional[str]
    term: Optional[str]
    selected: bool          # True if user has already selected this course
    setup_complete: bool    # True if this course's setup is done
    internal_id: Optional[str]  # Our DB UUID, once selected


class CourseSelectRequest(BaseModel):
    canvas_course_ids: List[int]


class ManualCourseRequest(BaseModel):
    name: str
    code: Optional[str] = None
    term: Optional[str] = None


class UndatedCluster(BaseModel):
    type_label: str
    representative: str
    count: int
    examples: List[str]
    assignment_ids: List[int]
    course_name: str


class UndatedConfirmRequest(BaseModel):
    # Map of canvas_course_id -> list of assignment_ids to include
    confirmed: dict[str, List[int]]


class ExtractRequest(BaseModel):
    content: str   # Pasted syllabus / course content


class ExtractedTask(BaseModel):
    title: str
    type: str
    due_date: Optional[str]
    confidence: float


class ConfirmExtractedRequest(BaseModel):
    tasks: List[ExtractedTask]   # Only the tasks the user confirmed


# ---------------------------------------------------------------------------
# 1. GET /setup/courses
# ---------------------------------------------------------------------------

@router.get("/courses")
async def list_courses(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Fetch all active Canvas courses + saved manual courses + their current setup state.
    Returns each course with selected/setup_complete flags.
    """
    canvas_courses = []
    if user.canvas_url and user.canvas_token:
        try:
            canvas_courses = await fetch_courses(user.canvas_url, user.canvas_token)
        except ValueError:
            pass  # Continue even if Canvas fetch fails

    # Load ALL saved Course records for this user (Canvas + manual)
    result = await db.execute(
        select(Course).where(Course.user_id == user.id)
    )
    saved_courses = {c.canvas_course_id: c for c in result.scalars().all()}

    courses = []

    # Add Canvas courses
    for c in canvas_courses:
        saved = saved_courses.get(c.id)
        courses.append(CourseWithStatus(
            canvas_course_id=c.id,
            name=c.name,
            code=c.code,
            term=c.term,
            selected=saved is not None,
            setup_complete=saved.setup_complete if saved else False,
            internal_id=str(saved.id) if saved else None,
        ))

    # Add manual courses (negative canvas_course_id)
    for cid, saved in saved_courses.items():
        if cid < 0:  # Manual courses have negative IDs
            courses.append(CourseWithStatus(
                canvas_course_id=cid,
                name=saved.name,
                code=saved.code,
                term=saved.term,
                selected=True,
                setup_complete=saved.setup_complete,
                internal_id=str(saved.id),
            ))

    return {"courses": [c.model_dump() for c in courses], "count": len(courses)}


# ---------------------------------------------------------------------------
# 2. POST /setup/courses/select
# ---------------------------------------------------------------------------

@router.post("/courses/select")
async def select_courses(
    request: CourseSelectRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Save the user's selected courses and import their dated Canvas tasks.
    Idempotent — re-selecting an already-saved course won't duplicate it.
    """
    if not user.canvas_url or not user.canvas_token:
        raise HTTPException(status_code=400, detail="Canvas not connected")

    if not request.canvas_course_ids:
        raise HTTPException(status_code=400, detail="No courses selected")

    # Fetch Canvas courses to get names
    try:
        canvas_courses = await fetch_courses(user.canvas_url, user.canvas_token)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    canvas_course_map = {c.id: c for c in canvas_courses}

    # Load existing saved courses
    result = await db.execute(
        select(Course).where(Course.user_id == user.id)
    )
    existing = {c.canvas_course_id: c for c in result.scalars().all()}

    created_courses = []
    for cid in request.canvas_course_ids:
        if cid in existing:
            continue  # Already saved
        canvas_c = canvas_course_map.get(cid)
        if not canvas_c:
            continue  # Not a valid Canvas course for this user
        course = Course(
            user_id=user.id,
            canvas_course_id=cid,
            name=canvas_c.name,
            code=canvas_c.code,
            term=canvas_c.term,
            setup_complete=False,
        )
        db.add(course)
        created_courses.append(cid)

    await db.flush()  # Get IDs before importing tasks

    # Import dated Canvas tasks for all selected courses
    selected_canvas_courses = [
        canvas_course_map[cid]
        for cid in request.canvas_course_ids
        if cid in canvas_course_map
    ]

    try:
        assignments = await fetch_assignments(
            user.canvas_url,
            user.canvas_token,
            courses=selected_canvas_courses,
        )
    except Exception:
        assignments = []

    # Reload courses to get internal IDs
    result = await db.execute(
        select(Course).where(Course.user_id == user.id)
    )
    course_id_map = {c.canvas_course_id: c.id for c in result.scalars().all()}

    tasks_created = 0
    for assignment in assignments:
        # Skip if already exists
        existing_task = await db.execute(
            select(Task)
            .where(Task.user_id == user.id)
            .where(Task.canvas_assignment_id == assignment.id)
        )
        if existing_task.scalar_one_or_none():
            continue

        estimated_minutes, reasoning = _rule_based_estimate(
            assignment.points_possible,
            assignment.submission_types,
        )

        task = Task(
            user_id=user.id,
            course_id=course_id_map.get(assignment.course_id),
            canvas_assignment_id=assignment.id,
            canvas_course_id=assignment.course_id,
            name=assignment.name,
            course_name=assignment.course_name,
            description=assignment.description,
            due_at=assignment.due_at,
            points_possible=assignment.points_possible,
            submission_types=assignment.submission_types,
            estimated_minutes=estimated_minutes,
            estimation_reasoning=reasoning,
            source=TaskSource.CANVAS,
            status=TaskStatus.PENDING,
        )
        db.add(task)
        tasks_created += 1

    await db.commit()

    return {
        "courses_created": len(created_courses),
        "tasks_imported": tasks_created,
        "message": f"Saved {len(created_courses)} new courses and imported {tasks_created} dated tasks from Canvas",
    }


# ---------------------------------------------------------------------------
# 2b. POST /setup/courses/create-manual
# ---------------------------------------------------------------------------

@router.post("/courses/create-manual")
async def create_manual_course(
    request: ManualCourseRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a manual (non-Canvas) course with a unique negative ID."""
    # Find the lowest negative ID already used for this user's manual courses
    result = await db.execute(
        select(Course)
        .where(Course.user_id == user.id)
        .where(Course.canvas_course_id < 0)
        .order_by(Course.canvas_course_id)
    )
    existing_manual = result.scalars().all()
    if existing_manual:
        next_id = existing_manual[0].canvas_course_id - 1
    else:
        next_id = -1

    course = Course(
        user_id=user.id,
        canvas_course_id=next_id,  # Use negative ID as a unique identifier
        name=request.name,
        code=request.code,
        term=request.term,
        setup_complete=False,
    )
    db.add(course)
    await db.commit()
    await db.refresh(course)

    return {
        "id": str(course.id),
        "canvas_course_id": next_id,
        "name": course.name,
        "code": course.code,
        "term": course.term,
        "message": f"Created course: {course.name}",
    }


# ---------------------------------------------------------------------------
# 3. GET /setup/undated
# ---------------------------------------------------------------------------

@router.get("/undated")
async def get_undated_clusters(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Fetch undated Canvas assignments for all selected courses,
    then cluster them by naming pattern using GPT-4o-mini.
    Returns one representative per cluster for the user to confirm.
    """
    if not user.canvas_url or not user.canvas_token:
        raise HTTPException(status_code=400, detail="Canvas not connected")

    # Get selected courses
    result = await db.execute(
        select(Course).where(Course.user_id == user.id)
    )
    saved_courses = result.scalars().all()
    if not saved_courses:
        raise HTTPException(status_code=400, detail="No courses selected yet. Complete course selection first.")

    canvas_course_ids = [c.canvas_course_id for c in saved_courses if c.canvas_course_id]
    course_name_map = {c.canvas_course_id: c.name for c in saved_courses}

    try:
        undated = await fetch_undated_assignments(
            user.canvas_url,
            user.canvas_token,
            canvas_course_ids,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not undated:
        return {"clusters": [], "total_undated": 0}

    # Group by course and cluster each course separately
    by_course: dict[int, list] = {}
    for a in undated:
        by_course.setdefault(a.course_id, []).append({
            "id": a.id,
            "name": a.name,
            "course_name": a.course_name,
        })

    all_clusters = []
    for course_canvas_id, assignments in by_course.items():
        clusters = await cluster_undated_assignments(assignments)
        for c in clusters:
            c["course_name"] = course_name_map.get(course_canvas_id, "Unknown")
            c["canvas_course_id"] = course_canvas_id
        all_clusters.extend(clusters)

    return {
        "clusters": all_clusters,
        "total_undated": len(undated),
    }


# ---------------------------------------------------------------------------
# 4. POST /setup/undated/confirm
# ---------------------------------------------------------------------------

@router.post("/undated/confirm")
async def confirm_undated(
    request: UndatedConfirmRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    User confirms which undated assignment types are real tasks.
    Creates Task records for each confirmed assignment_id, grouped under the cluster label.
    confirmed: { "canvas_course_id": [assignment_id, ...], ... }
    """
    if not user.canvas_url or not user.canvas_token:
        raise HTTPException(status_code=400, detail="Canvas not connected")

    if not request.confirmed:
        return {"tasks_created": 0}

    # Flatten all confirmed assignment IDs
    all_confirmed_ids: set[int] = set()
    for ids in request.confirmed.values():
        all_confirmed_ids.update(ids)

    # Fetch the undated assignments to get their details
    result = await db.execute(
        select(Course).where(Course.user_id == user.id)
    )
    saved_courses = result.scalars().all()
    canvas_course_ids = [c.canvas_course_id for c in saved_courses if c.canvas_course_id]
    course_id_map = {c.canvas_course_id: c.id for c in saved_courses}
    course_name_map = {c.canvas_course_id: c.name for c in saved_courses}

    try:
        undated = await fetch_undated_assignments(
            user.canvas_url,
            user.canvas_token,
            canvas_course_ids,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    tasks_created = 0
    for assignment in undated:
        if assignment.id not in all_confirmed_ids:
            continue

        # Skip if already exists
        existing = await db.execute(
            select(Task)
            .where(Task.user_id == user.id)
            .where(Task.canvas_assignment_id == assignment.id)
        )
        if existing.scalar_one_or_none():
            continue

        estimated_minutes, reasoning = _rule_based_estimate(
            assignment.points_possible,
            assignment.submission_types,
        )

        task = Task(
            user_id=user.id,
            course_id=course_id_map.get(assignment.course_id),
            canvas_assignment_id=assignment.id,
            canvas_course_id=assignment.course_id,
            name=assignment.name,
            course_name=course_name_map.get(assignment.course_id, assignment.course_name),
            description=assignment.description,
            due_at=None,  # Undated by definition
            points_possible=assignment.points_possible,
            submission_types=assignment.submission_types,
            estimated_minutes=estimated_minutes,
            estimation_reasoning=reasoning,
            source=TaskSource.CANVAS,
            status=TaskStatus.PENDING,
        )
        db.add(task)
        tasks_created += 1

    await db.commit()

    return {
        "tasks_created": tasks_created,
        "message": f"Added {tasks_created} undated tasks to your task list",
    }


# ---------------------------------------------------------------------------
# 5. POST /setup/courses/{canvas_course_id}/extract
# ---------------------------------------------------------------------------

@router.post("/courses/{canvas_course_id}/extract")
async def extract_from_content(
    canvas_course_id: int,
    request: ExtractRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    LLM-extracts tasks from pasted course content.
    Returns a preview with confidence scores — nothing is saved yet.
    """
    if not request.content.strip():
        raise HTTPException(status_code=400, detail="Content cannot be empty")

    # Look up the course
    result = await db.execute(
        select(Course)
        .where(Course.user_id == user.id)
        .where(Course.canvas_course_id == canvas_course_id)
    )
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found. Select it first.")

    # Save the pasted content for reference
    course.supplemental_content = request.content
    await db.commit()

    # Extract tasks via LLM
    extracted = await extract_tasks_from_content(
        content=request.content,
        course_name=course.name,
    )

    return {
        "course_name": course.name,
        "extracted": extracted,
        "count": len(extracted),
    }


# ---------------------------------------------------------------------------
# 6. POST /setup/courses/{canvas_course_id}/tasks/confirm
# ---------------------------------------------------------------------------

@router.post("/courses/{canvas_course_id}/tasks/confirm")
async def confirm_extracted_tasks(
    canvas_course_id: int,
    request: ConfirmExtractedRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Saves the user-confirmed extracted tasks to the database.
    Marks the course setup as complete.
    """
    # Look up the course
    result = await db.execute(
        select(Course)
        .where(Course.user_id == user.id)
        .where(Course.canvas_course_id == canvas_course_id)
    )
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    tasks_created = 0
    for item in request.tasks:
        due_at = None
        if item.due_date:
            try:
                due_at = datetime.fromisoformat(item.due_date).replace(tzinfo=timezone.utc)
            except ValueError:
                due_at = None

        task = Task(
            user_id=user.id,
            course_id=course.id,
            canvas_assignment_id=None,
            canvas_course_id=canvas_course_id,
            name=item.title,
            course_name=course.name,
            due_at=due_at,
            submission_types=[],
            source=TaskSource.EXTRACTED,
            confidence=item.confidence,
            status=TaskStatus.PENDING,
        )
        db.add(task)
        tasks_created += 1

    # Mark this course's setup as complete
    course.setup_complete = True
    await db.commit()

    return {
        "tasks_created": tasks_created,
        "course": course.name,
        "setup_complete": True,
        "message": f"Saved {tasks_created} tasks for {course.name}",
    }
