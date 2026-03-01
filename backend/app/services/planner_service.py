import uuid
from datetime import datetime, timedelta, time, timezone
from typing import List, Dict, Optional, Tuple

from sqlalchemy import select, and_, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task, TaskStatus
from app.models.event import Event
from app.models.workblock import WorkBlock, WorkBlockStatus
from app.models.constraint import Constraint, ConstraintType


# Default settings
DEFAULT_BLOCK_MINUTES = 60
BUFFER_DAYS_BEFORE_DUE = 1
MIN_SLOT_MINUTES = 30


async def generate_weekly_plan(
    db: AsyncSession,
    user_id: uuid.UUID,
    weeks: int = 1,
    block_minutes: int = DEFAULT_BLOCK_MINUTES,
) -> Dict:
    """
    Generate a weekly study plan by allocating WorkBlocks.

    1. Get pending tasks sorted by due date
    2. Find available time slots
    3. Allocate blocks for each task
    4. Save WorkBlocks to database

    Returns summary of created blocks.
    """
    now = datetime.now(timezone.utc)
    plan_end = now + timedelta(weeks=weeks)

    # Clear existing planned (not completed/skipped) blocks for this period
    await db.execute(
        delete(WorkBlock)
        .where(WorkBlock.user_id == user_id)
        .where(WorkBlock.status == WorkBlockStatus.PLANNED)
        .where(WorkBlock.start >= now)
        .where(WorkBlock.start < plan_end)
    )

    # Get tasks
    tasks = await _get_pending_tasks(db, user_id, weeks + 2)  # Look ahead for pull-forward

    # Get events and constraints
    events = await _get_events(db, user_id, weeks + 2)
    constraints = await _get_constraints(db, user_id)

    # Build available slots
    slots = _build_available_slots(now, plan_end, events, constraints)

    # Allocate tasks to slots
    blocks_created = []
    slot_index = 0

    for task in tasks:
        if task.status == TaskStatus.COMPLETED:
            continue

        remaining_minutes = task.effective_minutes or 60
        task_deadline = task.due_at - timedelta(days=BUFFER_DAYS_BEFORE_DUE)

        while remaining_minutes > 0 and slot_index < len(slots):
            slot_start, slot_end = slots[slot_index]

            # Skip slots after the task deadline (unless we're pulling forward)
            # For now, we just use earliest available slots
            if slot_start >= task_deadline:
                # Task can't be fully scheduled before deadline
                # Continue anyway (pull forward logic)
                pass

            slot_duration = (slot_end - slot_start).total_seconds() / 60

            if slot_duration < MIN_SLOT_MINUTES:
                slot_index += 1
                continue

            # Determine block size
            block_duration = min(block_minutes, remaining_minutes, slot_duration)

            # Create work block
            block = WorkBlock(
                user_id=user_id,
                task_id=task.id,
                title=f"Study: {task.name[:50]}",
                start=slot_start,
                end=slot_start + timedelta(minutes=block_duration),
                status=WorkBlockStatus.PLANNED,
            )
            db.add(block)
            blocks_created.append({
                "task_name": task.name,
                "course": task.course_name,
                "start": slot_start.isoformat(),
                "end": (slot_start + timedelta(minutes=block_duration)).isoformat(),
                "duration_minutes": block_duration,
            })

            remaining_minutes -= block_duration

            # Update slot (consume used time)
            new_slot_start = slot_start + timedelta(minutes=block_duration)
            if new_slot_start < slot_end:
                slots[slot_index] = (new_slot_start, slot_end)
            else:
                slot_index += 1

    await db.commit()

    return {
        "blocks_created": len(blocks_created),
        "blocks": blocks_created,
        "tasks_scheduled": len(set(b["task_name"] for b in blocks_created)),
    }


async def get_weekly_plan(
    db: AsyncSession,
    user_id: uuid.UUID,
    weeks: int = 1,
) -> List[Dict]:
    """Get existing WorkBlocks for the next N weeks."""
    now = datetime.now(timezone.utc)
    end = now + timedelta(weeks=weeks)

    result = await db.execute(
        select(WorkBlock)
        .where(WorkBlock.user_id == user_id)
        .where(WorkBlock.start >= now)
        .where(WorkBlock.start < end)
        .order_by(WorkBlock.start)
    )
    blocks = result.scalars().all()

    return [
        {
            "id": str(b.id),
            "task_id": str(b.task_id) if b.task_id else None,
            "title": b.title,
            "start": b.start.isoformat(),
            "end": b.end.isoformat(),
            "duration_minutes": b.duration_minutes,
            "status": b.status.value,
            "google_event_id": b.google_event_id,
        }
        for b in blocks
    ]


async def _get_pending_tasks(
    db: AsyncSession,
    user_id: uuid.UUID,
    weeks: int,
) -> List[Task]:
    """Get pending tasks sorted by due date."""
    now = datetime.now(timezone.utc)
    end = now + timedelta(weeks=weeks)

    result = await db.execute(
        select(Task)
        .where(Task.user_id == user_id)
        .where(Task.status != TaskStatus.COMPLETED)
        .where(Task.due_at >= now)
        .where(Task.due_at < end)
        .order_by(Task.due_at)
    )
    return list(result.scalars().all())


async def _get_events(
    db: AsyncSession,
    user_id: uuid.UUID,
    weeks: int,
) -> List[Event]:
    """Get calendar events."""
    now = datetime.now(timezone.utc)
    end = now + timedelta(weeks=weeks)

    result = await db.execute(
        select(Event)
        .where(Event.user_id == user_id)
        .where(Event.end >= now)
        .where(Event.start < end)
        .order_by(Event.start)
    )
    return list(result.scalars().all())


async def _get_constraints(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> List[Constraint]:
    """Get active constraints."""
    result = await db.execute(
        select(Constraint)
        .where(Constraint.user_id == user_id)
        .where(Constraint.is_active == True)
    )
    return list(result.scalars().all())


def _build_available_slots(
    start: datetime,
    end: datetime,
    events: List[Event],
    constraints: List[Constraint],
) -> List[Tuple[datetime, datetime]]:
    """
    Build list of available time slots.

    Starts with full days, then removes:
    - Sleep hours
    - Meal times
    - Calendar events
    """
    slots = []

    # Get constraint times
    sleep = next((c for c in constraints if c.constraint_type == ConstraintType.SLEEP), None)
    meals = [c for c in constraints if c.constraint_type == ConstraintType.MEAL]

    # Process day by day
    current_day = start.replace(hour=0, minute=0, second=0, microsecond=0)

    while current_day < end:
        day_of_week = current_day.weekday()

        # Start with full day
        day_start = current_day.replace(hour=7, minute=0)  # Default wake time
        day_end = current_day.replace(hour=23, minute=0)   # Default sleep time

        # Apply sleep constraint
        if sleep and sleep.start_time and sleep.end_time:
            # Wake time
            day_start = current_day.replace(
                hour=sleep.end_time.hour,
                minute=sleep.end_time.minute,
            )
            # Sleep time
            day_end = current_day.replace(
                hour=sleep.start_time.hour,
                minute=sleep.start_time.minute,
            )

        # Make timezone aware
        day_start = day_start.replace(tzinfo=timezone.utc)
        day_end = day_end.replace(tzinfo=timezone.utc)

        # Skip if day_start is before 'start' parameter
        if day_start < start:
            day_start = start

        if day_end > day_start:
            day_slots = [(day_start, day_end)]

            # Remove meal times
            for meal in meals:
                if meal.days_of_week and day_of_week not in meal.days_of_week:
                    continue
                if meal.start_time and meal.end_time:
                    meal_start = current_day.replace(
                        hour=meal.start_time.hour,
                        minute=meal.start_time.minute,
                        tzinfo=timezone.utc,
                    )
                    meal_end = current_day.replace(
                        hour=meal.end_time.hour,
                        minute=meal.end_time.minute,
                        tzinfo=timezone.utc,
                    )
                    day_slots = _subtract_interval(day_slots, meal_start, meal_end)

            # Remove calendar events
            day_events = [e for e in events if _overlaps(e.start, e.end, day_start, day_end)]
            for event in day_events:
                if not event.all_day:
                    day_slots = _subtract_interval(day_slots, event.start, event.end)

            slots.extend(day_slots)

        current_day += timedelta(days=1)

    # Filter out tiny slots
    slots = [(s, e) for s, e in slots if (e - s).total_seconds() >= MIN_SLOT_MINUTES * 60]

    return slots


def _subtract_interval(
    slots: List[Tuple[datetime, datetime]],
    remove_start: datetime,
    remove_end: datetime,
) -> List[Tuple[datetime, datetime]]:
    """Remove an interval from a list of slots."""
    result = []
    for slot_start, slot_end in slots:
        if remove_end <= slot_start or remove_start >= slot_end:
            # No overlap
            result.append((slot_start, slot_end))
        elif remove_start <= slot_start and remove_end >= slot_end:
            # Completely covered - remove slot
            pass
        elif remove_start > slot_start and remove_end < slot_end:
            # Splits the slot
            result.append((slot_start, remove_start))
            result.append((remove_end, slot_end))
        elif remove_start <= slot_start:
            # Cuts from start
            result.append((remove_end, slot_end))
        else:
            # Cuts from end
            result.append((slot_start, remove_start))
    return result


def _overlaps(start1: datetime, end1: datetime, start2: datetime, end2: datetime) -> bool:
    """Check if two intervals overlap."""
    return start1 < end2 and end1 > start2
