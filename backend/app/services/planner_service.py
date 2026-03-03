"""
Planner service — LLM-based weekly study plan generation.

Flow:
  1. Collect google_event_ids from existing planned WorkBlocks
  2. Delete those Google Calendar events (no duplicates on replan)
  3. Delete old planned WorkBlocks from DB
  4. Build available time slots (respecting sleep, meals, blocked_time, calendar events)
  5. Call LLM to assign tasks to slots
  6. Validate LLM output against actual slots
  7. Save new WorkBlocks to DB

Falls back to greedy allocation if the LLM call fails.
"""
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.constraint import Constraint, ConstraintType
from app.models.event import Event
from app.models.task import Task, TaskStatus
from app.models.workblock import WorkBlock, WorkBlockStatus
from app.services.calendar_write_service import delete_calendar_event

client = AsyncOpenAI(api_key=settings.openai_api_key)

DEFAULT_BLOCK_MINUTES = 60
MIN_SLOT_MINUTES = 30
MAX_BLOCK_MINUTES = 90

SYSTEM_PROMPT = """You are a smart academic study planner.

Given a student's pending tasks and their available free time slots, create a realistic weekly study schedule.

You will receive:
- Tasks: name, course, due date, hours remaining, unique ID
- Available time slots: already cleared of sleep, meals, blocked time, and calendar events

Rules:
- Each block must fit EXACTLY within one available slot (start >= slot start, end <= slot end)
- Blocks should be 30–90 minutes long (prefer 60 min; use shorter blocks for tasks due very soon)
- Prioritize tasks with earlier due dates
- Spread multi-hour tasks across multiple days when possible — avoid back-to-back marathons
- Leave breathing room — scheduling 70% of available time realistically beats cramming 100%
- It is fine to leave some tasks unscheduled if there is not enough time

Return ONLY a JSON object:
{"blocks": [{"task_id": "...", "task_name": "...", "start": "2026-03-02T09:00:00Z", "end": "2026-03-02T10:00:00Z"}]}"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def generate_weekly_plan(
    db: AsyncSession,
    user_id: uuid.UUID,
    weeks: int = 1,
    block_minutes: int = DEFAULT_BLOCK_MINUTES,
    user: Any = None,  # User model — needed for Google Calendar cleanup
) -> Dict:
    """
    Generate a weekly study plan using LLM-based scheduling.
    Cleans up existing Google Calendar events before replanning to prevent duplicates.
    """
    now = datetime.now(timezone.utc)
    plan_end = now + timedelta(weeks=weeks)

    # 1. Clean up old plan (DB + Google Calendar)
    await _cleanup_plan(db, user, user_id, now, plan_end)

    # 2. Fetch inputs
    tasks = await _get_pending_tasks(db, user_id, weeks + 2)
    tasks = [t for t in tasks if (t.remaining_minutes or 0) > 0]

    if not tasks:
        await db.commit()
        return {"blocks_created": 0, "blocks": [], "tasks_scheduled": 0}

    events = await _get_events(db, user_id, weeks + 2)
    constraints = await _get_constraints(db, user_id)

    # 3. Build available slots
    slots = _build_available_slots(now, plan_end, events, constraints)

    # 4. Plan (LLM with greedy fallback)
    try:
        raw_blocks = await _llm_plan(tasks, slots, now, weeks, constraints)
    except Exception as e:
        print(f"LLM planner failed, falling back to greedy: {e}")
        raw_blocks = _greedy_plan(tasks, slots, block_minutes)

    # 5. Validate + create WorkBlocks
    task_map = {str(t.id): t for t in tasks}
    blocks_created = []

    for block in raw_blocks:
        task = task_map.get(str(block.get("task_id", "")))
        if not task:
            continue

        start = block.get("start")
        end = block.get("end")
        if not start or not end or start >= end:
            continue

        duration = (end - start).total_seconds() / 60
        if duration < MIN_SLOT_MINUTES:
            continue

        if not _fits_in_slots(start, end, slots):
            continue

        wb = WorkBlock(
            user_id=user_id,
            task_id=task.id,
            title=f"Study: {task.name[:50]}",
            start=start,
            end=end,
            status=WorkBlockStatus.PLANNED,
        )
        db.add(wb)
        blocks_created.append({
            "task_name": task.name,
            "course": task.course_name,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "duration_minutes": int(duration),
        })

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


# ---------------------------------------------------------------------------
# Calendar cleanup
# ---------------------------------------------------------------------------

async def _cleanup_plan(
    db: AsyncSession,
    user: Any,
    user_id: uuid.UUID,
    now: datetime,
    plan_end: datetime,
) -> None:
    """
    Delete existing planned WorkBlocks and their Google Calendar events.
    This prevents duplicates when replanning.
    """
    result = await db.execute(
        select(WorkBlock)
        .where(WorkBlock.user_id == user_id)
        .where(WorkBlock.status == WorkBlockStatus.PLANNED)
        .where(WorkBlock.start >= now)
        .where(WorkBlock.start < plan_end)
    )
    existing = result.scalars().all()

    # Delete Google Calendar events first
    if user:
        for wb in existing:
            if wb.google_event_id:
                try:
                    await delete_calendar_event(db, user, wb.google_event_id)
                except Exception as e:
                    print(f"Failed to delete calendar event {wb.google_event_id}: {e}")

    # Delete WorkBlocks from DB
    for wb in existing:
        await db.delete(wb)

    # Flush so the deletes are visible before we insert new blocks
    await db.flush()


# ---------------------------------------------------------------------------
# LLM planner
# ---------------------------------------------------------------------------

async def _llm_plan(
    tasks: List[Task],
    slots: List[Tuple[datetime, datetime]],
    now: datetime,
    weeks: int,
    constraints: List[Constraint],
) -> List[Dict]:
    """
    Call GPT-4o-mini to assign tasks to available time slots.
    Returns a list of {task_id, start, end} dicts.
    """
    # Format tasks (cap at 25)
    task_lines = []
    for t in tasks[:25]:
        remaining_h = (t.remaining_minutes or 60) / 60
        due_str = t.due_at.strftime("%a %b %d at %I:%M %p UTC") if t.due_at else "no due date"
        task_lines.append(
            f'- ID:{t.id} | "{t.name}" ({t.course_name}) | due {due_str} | {remaining_h:.1f}h remaining'
        )

    # Format slots (cap at 40)
    slot_lines = []
    for s, e in slots[:40]:
        duration_h = (e - s).total_seconds() / 3600
        slot_lines.append(
            f'- {s.strftime("%a %b %d")} | {s.strftime("%H:%M")}Z–{e.strftime("%H:%M")}Z ({duration_h:.1f}h free)'
        )

    # Extract max_hours_per_day constraint if set
    max_constraint = next(
        (c for c in constraints if c.constraint_type == ConstraintType.MAX_HOURS_PER_DAY and c.is_active),
        None,
    )
    max_note = (
        f"\nIMPORTANT: The student has a max study limit of {max_constraint.max_minutes / 60:.1f} hours per day. "
        "Do not exceed this across all blocks on a single day."
        if max_constraint
        else ""
    )

    user_prompt = f"""Today: {now.strftime("%A, %B %d, %Y %H:%M UTC")}
Planning window: next {weeks} week(s){max_note}

TASKS TO SCHEDULE (sorted by due date):
{chr(10).join(task_lines) or "No tasks."}

AVAILABLE TIME SLOTS:
{chr(10).join(slot_lines) or "No free slots."}

Assign tasks to slots and return the study schedule as JSON."""

    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content
    parsed = json.loads(raw)
    raw_blocks = parsed.get("blocks", [])

    # Parse and return
    result = []
    for block in raw_blocks:
        try:
            start_str = block["start"].replace("Z", "+00:00")
            end_str = block["end"].replace("Z", "+00:00")
            start = datetime.fromisoformat(start_str)
            end = datetime.fromisoformat(end_str)
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
            result.append({
                "task_id": str(block.get("task_id", "")),
                "start": start,
                "end": end,
            })
        except (KeyError, ValueError):
            continue

    return result


# ---------------------------------------------------------------------------
# Greedy fallback
# ---------------------------------------------------------------------------

def _greedy_plan(
    tasks: List[Task],
    slots: List[Tuple[datetime, datetime]],
    block_minutes: int,
) -> List[Dict]:
    """Simple greedy planner — fills earliest slots first. Used as LLM fallback."""
    # Work on a copy so we don't mutate the original
    slots = list(slots)
    slot_index = 0
    result = []

    for task in tasks:
        remaining = task.remaining_minutes or 60

        while remaining > 0 and slot_index < len(slots):
            slot_start, slot_end = slots[slot_index]
            slot_duration = (slot_end - slot_start).total_seconds() / 60

            if slot_duration < MIN_SLOT_MINUTES:
                slot_index += 1
                continue

            block_duration = min(block_minutes, remaining, slot_duration)
            block_end = slot_start + timedelta(minutes=block_duration)

            result.append({
                "task_id": str(task.id),
                "start": slot_start,
                "end": block_end,
            })

            remaining -= block_duration
            new_start = block_end
            if new_start < slot_end:
                slots[slot_index] = (new_start, slot_end)
            else:
                slot_index += 1

    return result


# ---------------------------------------------------------------------------
# Slot validation
# ---------------------------------------------------------------------------

def _fits_in_slots(
    start: datetime,
    end: datetime,
    slots: List[Tuple[datetime, datetime]],
    tolerance_minutes: int = 5,
) -> bool:
    """Return True if (start, end) fits within at least one available slot."""
    tol = timedelta(minutes=tolerance_minutes)
    for slot_start, slot_end in slots:
        if start >= slot_start - tol and end <= slot_end + tol:
            return True
    return False


# ---------------------------------------------------------------------------
# Slot building
# ---------------------------------------------------------------------------

def _build_available_slots(
    start: datetime,
    end: datetime,
    events: List[Event],
    constraints: List[Constraint],
) -> List[Tuple[datetime, datetime]]:
    """
    Build free time slots between start and end.

    Removes: sleep (with weekday/weekend support), meals, blocked_time, calendar events.
    """
    slots = []
    current_day = start.replace(hour=0, minute=0, second=0, microsecond=0)

    meals = [c for c in constraints if c.constraint_type == ConstraintType.MEAL and c.is_active]
    blocked = [c for c in constraints if c.constraint_type == ConstraintType.BLOCKED_TIME and c.is_active]
    sleep_constraints = [c for c in constraints if c.constraint_type == ConstraintType.SLEEP and c.is_active]

    while current_day < end:
        day_of_week = current_day.weekday()

        # Find the sleep constraint that applies to this day
        sleep = next(
            (c for c in sleep_constraints if not c.days_of_week or day_of_week in c.days_of_week),
            None,
        )

        # Default wake/sleep times
        if sleep and sleep.start_time and sleep.end_time:
            day_start = current_day.replace(
                hour=sleep.end_time.hour, minute=sleep.end_time.minute
            )
            day_end = current_day.replace(
                hour=sleep.start_time.hour, minute=sleep.start_time.minute
            )
        else:
            day_start = current_day.replace(hour=7, minute=0)
            day_end = current_day.replace(hour=23, minute=0)

        day_start = day_start.replace(tzinfo=timezone.utc)
        day_end = day_end.replace(tzinfo=timezone.utc)

        # Don't schedule in the past
        if day_start < start:
            day_start = start

        if day_end > day_start:
            day_slots = [(day_start, day_end)]

            # Remove meals
            for meal in meals:
                if meal.days_of_week and day_of_week not in meal.days_of_week:
                    continue
                if meal.start_time and meal.end_time:
                    ms = current_day.replace(
                        hour=meal.start_time.hour, minute=meal.start_time.minute, tzinfo=timezone.utc
                    )
                    me = current_day.replace(
                        hour=meal.end_time.hour, minute=meal.end_time.minute, tzinfo=timezone.utc
                    )
                    day_slots = _subtract_interval(day_slots, ms, me)

            # Remove blocked_time constraints
            for block in blocked:
                if block.days_of_week and day_of_week not in block.days_of_week:
                    continue
                if block.start_time and block.end_time:
                    bs = current_day.replace(
                        hour=block.start_time.hour, minute=block.start_time.minute, tzinfo=timezone.utc
                    )
                    be = current_day.replace(
                        hour=block.end_time.hour, minute=block.end_time.minute, tzinfo=timezone.utc
                    )
                    day_slots = _subtract_interval(day_slots, bs, be)

            # Remove calendar events
            day_events = [e for e in events if _overlaps(e.start, e.end, day_start, day_end)]
            for event in day_events:
                if not event.all_day:
                    day_slots = _subtract_interval(day_slots, event.start, event.end)

            slots.extend(day_slots)

        current_day += timedelta(days=1)

    return [(s, e) for s, e in slots if (e - s).total_seconds() >= MIN_SLOT_MINUTES * 60]


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

async def _get_pending_tasks(db: AsyncSession, user_id: uuid.UUID, weeks: int) -> List[Task]:
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


async def _get_events(db: AsyncSession, user_id: uuid.UUID, weeks: int) -> List[Event]:
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


async def _get_constraints(db: AsyncSession, user_id: uuid.UUID) -> List[Constraint]:
    result = await db.execute(
        select(Constraint)
        .where(Constraint.user_id == user_id)
        .where(Constraint.is_active == True)
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Interval helpers
# ---------------------------------------------------------------------------

def _subtract_interval(
    slots: List[Tuple[datetime, datetime]],
    remove_start: datetime,
    remove_end: datetime,
) -> List[Tuple[datetime, datetime]]:
    result = []
    for slot_start, slot_end in slots:
        if remove_end <= slot_start or remove_start >= slot_end:
            result.append((slot_start, slot_end))
        elif remove_start <= slot_start and remove_end >= slot_end:
            pass  # Fully consumed
        elif remove_start > slot_start and remove_end < slot_end:
            result.append((slot_start, remove_start))
            result.append((remove_end, slot_end))
        elif remove_start <= slot_start:
            result.append((remove_end, slot_end))
        else:
            result.append((slot_start, remove_start))
    return result


def _overlaps(start1: datetime, end1: datetime, start2: datetime, end2: datetime) -> bool:
    return start1 < end2 and end1 > start2
