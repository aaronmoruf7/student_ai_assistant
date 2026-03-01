import uuid
from datetime import datetime, timezone
from typing import List, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task, TaskStatus
from app.models.event import Event, EventType
from app.models.user import User
from app.services.canvas_service import fetch_courses, fetch_assignments
from app.services.calendar_service import fetch_calendar_events
from app.services.estimation_service import estimate_task_duration, _rule_based_estimate
from app.schemas.canvas import CanvasAssignment
from app.schemas.calendar import CalendarEvent


async def sync_canvas_tasks(
    db: AsyncSession,
    user: User,
    use_llm: bool = False,
) -> Tuple[int, int]:
    """
    Sync assignments from Canvas to Tasks table.
    Returns (created_count, updated_count).

    use_llm: If True, uses GPT-4o-mini for estimation (costs tokens).
             If False (default), uses free rule-based estimation.
    """
    if not user.canvas_url or not user.canvas_token:
        raise ValueError("Canvas not connected")

    # Fetch assignments from Canvas
    assignments = await fetch_assignments(user.canvas_url, user.canvas_token)

    created = 0
    updated = 0

    for assignment in assignments:
        # Check if task already exists
        result = await db.execute(
            select(Task)
            .where(Task.user_id == user.id)
            .where(Task.canvas_assignment_id == assignment.id)
        )
        existing_task = result.scalar_one_or_none()

        if existing_task:
            # Update existing task (but preserve user estimates and status)
            existing_task.name = assignment.name
            existing_task.course_name = assignment.course_name
            existing_task.description = assignment.description
            existing_task.due_at = assignment.due_at
            existing_task.points_possible = assignment.points_possible
            existing_task.submission_types = assignment.submission_types
            updated += 1
        else:
            # Estimate effort for new task
            if use_llm:
                estimated_minutes, reasoning = await estimate_task_duration(
                    name=assignment.name,
                    course_name=assignment.course_name,
                    description=assignment.description,
                    points_possible=assignment.points_possible,
                    submission_types=assignment.submission_types,
                )
            else:
                estimated_minutes, reasoning = _rule_based_estimate(
                    assignment.points_possible,
                    assignment.submission_types,
                )

            # Create new task
            task = Task(
                user_id=user.id,
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
                status=TaskStatus.PENDING,
            )
            db.add(task)
            created += 1

    await db.commit()
    return created, updated


async def sync_calendar_events(
    db: AsyncSession,
    user: User,
    weeks: int = 4,
) -> Tuple[int, int]:
    """
    Sync events from Google Calendar to Events table.
    Returns (created_count, updated_count).
    """
    # Fetch events from Google Calendar
    calendar_events = await fetch_calendar_events(db, user, weeks)

    created = 0
    updated = 0

    for cal_event in calendar_events:
        # Check if event already exists
        result = await db.execute(
            select(Event)
            .where(Event.user_id == user.id)
            .where(Event.google_event_id == cal_event.id)
        )
        existing_event = result.scalar_one_or_none()

        # Infer event type from title
        event_type = _infer_event_type(cal_event.summary)

        if existing_event:
            # Update existing event
            existing_event.title = cal_event.summary
            existing_event.description = cal_event.description
            existing_event.location = cal_event.location
            existing_event.start = cal_event.start
            existing_event.end = cal_event.end
            existing_event.all_day = cal_event.all_day
            existing_event.event_type = event_type
            updated += 1
        else:
            # Create new event
            event = Event(
                user_id=user.id,
                google_event_id=cal_event.id,
                calendar_id=cal_event.calendar_id,
                title=cal_event.summary,
                description=cal_event.description,
                location=cal_event.location,
                start=cal_event.start,
                end=cal_event.end,
                all_day=cal_event.all_day,
                event_type=event_type,
            )
            db.add(event)
            created += 1

    await db.commit()
    return created, updated


def _infer_event_type(title: str) -> EventType:
    """Infer event type from title keywords."""
    title_lower = title.lower()

    # Class indicators
    class_keywords = [
        "lecture", "class", "seminar", "lab", "section", "recitation",
        "cs50", "cs ", "math", "econ", "psych", "bio", "chem", "phys",
        "office hours", "oh"
    ]
    if any(kw in title_lower for kw in class_keywords):
        return EventType.CLASS

    # Work indicators
    work_keywords = ["work", "job", "shift", "meeting"]
    if any(kw in title_lower for kw in work_keywords):
        return EventType.WORK

    # Personal indicators
    personal_keywords = ["gym", "workout", "lunch", "dinner", "coffee", "hangout", "party"]
    if any(kw in title_lower for kw in personal_keywords):
        return EventType.PERSONAL

    return EventType.OTHER


async def get_user_tasks(
    db: AsyncSession,
    user_id: uuid.UUID,
    include_completed: bool = False,
) -> List[Task]:
    """Get all tasks for a user."""
    query = select(Task).where(Task.user_id == user_id)

    if not include_completed:
        query = query.where(Task.status != TaskStatus.COMPLETED)

    query = query.order_by(Task.due_at)

    result = await db.execute(query)
    return list(result.scalars().all())


async def get_user_events(
    db: AsyncSession,
    user_id: uuid.UUID,
    from_date: datetime = None,
    to_date: datetime = None,
) -> List[Event]:
    """Get all events for a user within a date range."""
    query = select(Event).where(Event.user_id == user_id)

    if from_date:
        query = query.where(Event.start >= from_date)
    if to_date:
        query = query.where(Event.end <= to_date)

    query = query.order_by(Event.start)

    result = await db.execute(query)
    return list(result.scalars().all())
