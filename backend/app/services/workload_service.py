import uuid
from datetime import datetime, timedelta, time, timezone
from typing import List, Dict, Tuple
from enum import Enum

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task, TaskStatus
from app.models.event import Event
from app.models.constraint import Constraint, ConstraintType


class LoadLevel(str, Enum):
    LIGHT = "light"
    MEDIUM = "medium"
    HEAVY = "heavy"
    OVERLOADED = "overloaded"


def get_load_level(utilization: float) -> LoadLevel:
    """Determine load level from utilization percentage."""
    if utilization < 0.5:
        return LoadLevel.LIGHT
    elif utilization < 0.75:
        return LoadLevel.MEDIUM
    elif utilization <= 1.0:
        return LoadLevel.HEAVY
    else:
        return LoadLevel.OVERLOADED


def get_load_emoji(level: LoadLevel) -> str:
    """Get emoji for load level."""
    return {
        LoadLevel.LIGHT: "🟢",
        LoadLevel.MEDIUM: "🟡",
        LoadLevel.HEAVY: "🔴",
        LoadLevel.OVERLOADED: "⚫",
    }[level]


async def calculate_workload_ramps(
    db: AsyncSession,
    user_id: uuid.UUID,
    weeks: int = 4,
) -> List[Dict]:
    """
    Calculate weekly workload ramps for the next N weeks.

    Returns list of week summaries with:
    - week_start, week_end
    - total_work_minutes (from tasks due that week)
    - available_minutes (from calendar - events - constraints)
    - utilization (work / available)
    - load_level (light/medium/heavy/overloaded)
    """
    now = datetime.now(timezone.utc)

    # Get start of current week (Monday)
    days_since_monday = now.weekday()
    week_start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days_since_monday)

    # Fetch all data we need
    tasks = await _get_upcoming_tasks(db, user_id, weeks)
    events = await _get_upcoming_events(db, user_id, weeks)
    constraints = await _get_active_constraints(db, user_id)

    # Calculate for each week
    results = []
    for i in range(weeks):
        ws = week_start + timedelta(weeks=i)
        we = ws + timedelta(days=7)

        # Work due this week
        week_tasks = [t for t in tasks if ws <= t.due_at < we]
        work_minutes = sum(t.effective_minutes or 60 for t in week_tasks)  # default 60 if no estimate

        # Available time this week
        week_events = [e for e in events if _event_overlaps_week(e, ws, we)]
        available_minutes = _calculate_available_minutes(ws, we, week_events, constraints)

        # Utilization
        if available_minutes > 0:
            utilization = work_minutes / available_minutes
        else:
            utilization = float('inf') if work_minutes > 0 else 0

        load_level = get_load_level(utilization)

        results.append({
            "week_start": ws.isoformat(),
            "week_end": we.isoformat(),
            "week_label": f"Week of {ws.strftime('%b %d')}",
            "tasks_due": len(week_tasks),
            "work_minutes": work_minutes,
            "work_hours": round(work_minutes / 60, 1),
            "available_minutes": available_minutes,
            "available_hours": round(available_minutes / 60, 1),
            "utilization": round(utilization, 2),
            "load_level": load_level.value,
            "emoji": get_load_emoji(load_level),
            "summary": f"{get_load_emoji(load_level)} {load_level.value.title()} ({round(work_minutes/60, 1)} hrs work / {round(available_minutes/60, 1)} hrs available)",
        })

    return results


async def _get_upcoming_tasks(
    db: AsyncSession,
    user_id: uuid.UUID,
    weeks: int,
) -> List[Task]:
    """Get tasks due in the next N weeks."""
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


async def _get_upcoming_events(
    db: AsyncSession,
    user_id: uuid.UUID,
    weeks: int,
) -> List[Event]:
    """Get events in the next N weeks."""
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


async def _get_active_constraints(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> List[Constraint]:
    """Get active constraints for user."""
    result = await db.execute(
        select(Constraint)
        .where(Constraint.user_id == user_id)
        .where(Constraint.is_active == True)
    )
    return list(result.scalars().all())


def _event_overlaps_week(event: Event, week_start: datetime, week_end: datetime) -> bool:
    """Check if event overlaps with the given week."""
    return event.start < week_end and event.end > week_start


def _calculate_available_minutes(
    week_start: datetime,
    week_end: datetime,
    events: List[Event],
    constraints: List[Constraint],
) -> int:
    """
    Calculate available study minutes in a week.

    Starts with total waking hours, subtracts:
    - Sleep time (from constraints)
    - Meal times (from constraints)
    - Calendar events
    - Respects max_hours_per_day constraint
    """
    # Base: 7 days * 24 hours = 168 hours
    total_minutes = 7 * 24 * 60

    # Subtract sleep (assume 8 hours/day if no constraint)
    sleep_constraint = next(
        (c for c in constraints if c.constraint_type == ConstraintType.SLEEP),
        None
    )
    if sleep_constraint and sleep_constraint.start_time and sleep_constraint.end_time:
        sleep_hours = _hours_between(sleep_constraint.start_time, sleep_constraint.end_time)
    else:
        sleep_hours = 8
    total_minutes -= 7 * sleep_hours * 60

    # Subtract meals
    meal_constraints = [c for c in constraints if c.constraint_type == ConstraintType.MEAL]
    for meal in meal_constraints:
        if meal.start_time and meal.end_time:
            meal_hours = _hours_between(meal.start_time, meal.end_time)
            days_active = len(meal.days_of_week) if meal.days_of_week else 7
            total_minutes -= days_active * meal_hours * 60

    # Subtract calendar events (non-all-day)
    for event in events:
        if not event.all_day:
            # Clamp event to week boundaries
            start = max(event.start, week_start)
            end = min(event.end, week_end)
            if end > start:
                event_minutes = (end - start).total_seconds() / 60
                total_minutes -= event_minutes

    # Apply max hours per day limit
    max_hours_constraint = next(
        (c for c in constraints if c.constraint_type == ConstraintType.MAX_HOURS_PER_DAY),
        None
    )
    if max_hours_constraint and max_hours_constraint.max_minutes:
        max_weekly = max_hours_constraint.max_minutes * 7
        total_minutes = min(total_minutes, max_weekly)

    return max(0, int(total_minutes))


def _hours_between(start: time, end: time) -> float:
    """Calculate hours between two times (handles overnight spans)."""
    start_minutes = start.hour * 60 + start.minute
    end_minutes = end.hour * 60 + end.minute

    if end_minutes > start_minutes:
        # Same day (e.g., 12:00 to 13:00)
        return (end_minutes - start_minutes) / 60
    else:
        # Overnight (e.g., 23:00 to 07:00)
        return (24 * 60 - start_minutes + end_minutes) / 60
