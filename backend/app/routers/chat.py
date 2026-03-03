"""
Chat router — AI planning assistant with full Google Calendar tool access.

The AI can read the user's tasks and calendar, create/edit/delete events,
schedule study blocks, save preferences, and generate full plans.

Onboarding: first session (onboarding_complete=False) → AI asks structured
questions, saves answers as constraints + ai_preferences, then generates
an initial plan.

Confirmation: destructive tools (delete, move) require the AI to ask the
user first. The system prompt enforces this. The frontend renders the AI's
confirmation request as a visual prompt.
"""
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from openai import AsyncOpenAI

from app.config import settings
from app.db import get_db
from app.models.constraint import Constraint, ConstraintType
from app.models.event import Event
from app.models.task import Task, TaskStatus
from app.models.user import User
from app.models.workblock import WorkBlock, WorkBlockStatus
from app.services.calendar_write_service import (
    create_google_event,
    update_google_event,
    delete_calendar_event,
    sync_workblock_to_calendar,
)
from app.services.planner_service import generate_weekly_plan
from app.services.user_service import get_user_by_id

router = APIRouter(prefix="/chat", tags=["chat"])
client = AsyncOpenAI(api_key=settings.openai_api_key)


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

class ChatMessage(BaseModel):
    role: str   # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


class ToolAction(BaseModel):
    tool: str
    label: str          # Human-readable description shown in the UI
    success: bool
    requires_confirm: bool = False   # True if this was a confirmation prompt


class ChatResponse(BaseModel):
    reply: str
    actions: list[ToolAction] = []
    onboarding_complete: bool


# ---------------------------------------------------------------------------
# Tool definitions (OpenAI function calling format)
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_week_overview",
            "description": "Get a summary of the user's tasks, calendar events, and study blocks for the coming week.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "How many days ahead to look (default 7)",
                        "default": 7,
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_tasks",
            "description": "Get the user's pending tasks with due dates and remaining hours.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_calendar_events",
            "description": "Get upcoming Google Calendar events.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Days ahead to look (default 7)",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_study_block",
            "description": "Create a study session on Google Calendar for a specific task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "UUID of the task"},
                    "title": {"type": "string", "description": "Title for the calendar event"},
                    "start": {"type": "string", "description": "ISO 8601 start datetime (UTC)"},
                    "end": {"type": "string", "description": "ISO 8601 end datetime (UTC)"},
                },
                "required": ["task_id", "title", "start", "end"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_study_block",
            "description": "Delete a study block from the calendar. ALWAYS ask the user for confirmation before calling this.",
            "parameters": {
                "type": "object",
                "properties": {
                    "block_id": {"type": "string", "description": "UUID of the WorkBlock"},
                },
                "required": ["block_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "move_study_block",
            "description": "Reschedule a study block to a new time. ALWAYS ask the user for confirmation before calling this.",
            "parameters": {
                "type": "object",
                "properties": {
                    "block_id": {"type": "string", "description": "UUID of the WorkBlock"},
                    "new_start": {"type": "string", "description": "New ISO 8601 start datetime (UTC)"},
                    "new_end": {"type": "string", "description": "New ISO 8601 end datetime (UTC)"},
                },
                "required": ["block_id", "new_start", "new_end"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_calendar_event",
            "description": "Create any event on the user's Google Calendar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "start": {"type": "string", "description": "ISO 8601 datetime (UTC)"},
                    "end": {"type": "string", "description": "ISO 8601 datetime (UTC)"},
                    "description": {"type": "string", "default": ""},
                },
                "required": ["title", "start", "end"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_calendar_event",
            "description": "Update the title or time of a Google Calendar event. ALWAYS confirm with the user before calling this.",
            "parameters": {
                "type": "object",
                "properties": {
                    "google_event_id": {"type": "string"},
                    "title": {"type": "string"},
                    "start": {"type": "string", "description": "ISO 8601 datetime (UTC)"},
                    "end": {"type": "string", "description": "ISO 8601 datetime (UTC)"},
                },
                "required": ["google_event_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_calendar_event_tool",
            "description": "Delete a Google Calendar event. ALWAYS confirm with the user before calling this.",
            "parameters": {
                "type": "object",
                "properties": {
                    "google_event_id": {"type": "string"},
                    "event_title": {"type": "string", "description": "Title of the event (for confirmation message)"},
                },
                "required": ["google_event_id", "event_title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_full_plan",
            "description": "Generate a complete weekly study plan and write it to Google Calendar. This clears existing study blocks and creates fresh ones.",
            "parameters": {
                "type": "object",
                "properties": {
                    "weeks": {"type": "integer", "description": "How many weeks to plan (1-4)", "default": 1},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_preference",
            "description": "Save a soft scheduling preference in natural language (e.g. 'prefers mornings', 'wants 30 min buffer after class').",
            "parameters": {
                "type": "object",
                "properties": {
                    "preference": {"type": "string", "description": "The preference to save"},
                },
                "required": ["preference"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_constraint",
            "description": "Save a structured schedule constraint (sleep, meal, blocked_time, or max_hours_per_day).",
            "parameters": {
                "type": "object",
                "properties": {
                    "constraint_type": {
                        "type": "string",
                        "enum": ["sleep", "meal", "blocked_time", "max_hours_per_day"],
                    },
                    "name": {"type": "string", "description": "Human label, e.g. 'Sleep', 'Lunch'"},
                    "start_time": {"type": "string", "description": "HH:MM (24h)"},
                    "end_time": {"type": "string", "description": "HH:MM (24h)"},
                    "days_of_week": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "0=Mon … 6=Sun. Omit for all days.",
                    },
                    "max_minutes": {
                        "type": "integer",
                        "description": "For max_hours_per_day: max study minutes per day",
                    },
                },
                "required": ["constraint_type", "name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "complete_onboarding",
            "description": "Mark the user's onboarding as complete after gathering all preferences.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


# ---------------------------------------------------------------------------
# System prompt builder
# ---------------------------------------------------------------------------

async def _build_system_prompt(db: AsyncSession, user: User) -> str:
    now = datetime.now(timezone.utc)
    today_str = now.strftime("%A, %B %d, %Y %H:%M UTC")

    # Load upcoming tasks
    tasks_result = await db.execute(
        select(Task)
        .where(Task.user_id == user.id)
        .where(Task.status != TaskStatus.COMPLETED)
        .where(Task.due_at >= now)
        .order_by(Task.due_at)
        .limit(20)
    )
    tasks = tasks_result.scalars().all()
    task_lines = [
        f"  - [{t.id}] \"{t.name}\" ({t.course_name}) due {t.due_at.strftime('%a %b %d')} | {(t.remaining_minutes or 0) / 60:.1f}h remaining"
        for t in tasks
    ] or ["  (no pending tasks)"]

    # Load upcoming calendar events (next 14 days)
    from datetime import timedelta
    end_window = now + timedelta(days=14)
    events_result = await db.execute(
        select(Event)
        .where(Event.user_id == user.id)
        .where(Event.start >= now)
        .where(Event.start < end_window)
        .order_by(Event.start)
        .limit(30)
    )
    events = events_result.scalars().all()
    event_lines = [
        f"  - [{e.google_event_id}] \"{e.title}\" {e.start.strftime('%a %b %d %H:%M')}–{e.end.strftime('%H:%M')} UTC"
        for e in events
    ] or ["  (no upcoming events)"]

    # Load existing study blocks
    blocks_result = await db.execute(
        select(WorkBlock)
        .where(WorkBlock.user_id == user.id)
        .where(WorkBlock.start >= now)
        .where(WorkBlock.start < end_window)
        .where(WorkBlock.status == WorkBlockStatus.PLANNED)
        .order_by(WorkBlock.start)
        .limit(20)
    )
    blocks = blocks_result.scalars().all()
    block_lines = [
        f"  - [{b.id}] \"{b.title}\" {b.start.strftime('%a %b %d %H:%M')}–{b.end.strftime('%H:%M')} UTC"
        for b in blocks
    ] or ["  (no study blocks scheduled)"]

    # Load constraints
    constraints_result = await db.execute(
        select(Constraint).where(Constraint.user_id == user.id).where(Constraint.is_active == True)
    )
    constraints = constraints_result.scalars().all()
    constraint_lines = [
        f"  - {c.name} ({c.constraint_type.value}): {c.start_time}–{c.end_time} on days {c.days_of_week}"
        for c in constraints
    ] or ["  (no constraints saved yet)"]

    preferences_section = (
        f"\nUSER PREFERENCES (from previous conversations):\n  {user.ai_preferences}"
        if user.ai_preferences
        else "\nUSER PREFERENCES: None saved yet."
    )

    onboarding_section = ""
    if not user.onboarding_complete:
        onboarding_section = """
ONBOARDING MODE: This is the user's first session. Your job is to learn their scheduling preferences.

Ask these questions naturally (not all at once — feel conversational):
1. Sleep schedule: what time do they go to sleep and wake up? Different on weekends?
2. Hard off-limits times: anything completely blocked (work, sports, family time)?
3. Study style: how long can they focus in one sitting? Morning, afternoon, or evening person?
4. Margin preferences: do they want buffer between classes and study sessions? How much?
5. Any recurring commitments not on their calendar?

After gathering answers:
- Call save_constraint for each structured time block (sleep, blocked_time)
- Call save_preference for soft preferences (study style, margin, time-of-day preference)
- Call complete_onboarding
- Offer to generate their first plan

Do NOT ask all questions at once. Be warm, conversational, and brief. Reference their actual calendar when relevant.
"""

    return f"""You are a smart, friendly AI planning assistant for a student. You have full access to their tasks, calendar, and scheduling preferences.

Today: {today_str}

PENDING TASKS:
{chr(10).join(task_lines)}

UPCOMING CALENDAR EVENTS (next 14 days):
{chr(10).join(event_lines)}

SCHEDULED STUDY BLOCKS:
{chr(10).join(block_lines)}

CONSTRAINTS:
{chr(10).join(constraint_lines)}
{preferences_section}
{onboarding_section}
TOOL RULES:
- For destructive actions (delete, move, update): ALWAYS describe what you're about to do and ask "Should I go ahead?" BEFORE calling the tool. Only call the tool after the user says yes.
- For additive actions (create study block, create event, generate plan): execute immediately and tell the user what you did.
- When you use a tool, briefly tell the user what happened in plain language.
- Keep responses concise and direct. You're a planning assistant, not a tutor.
- Reference specific tasks, events, and times from the data above — don't speak in generalities.
- All times are UTC. When talking to the user, you can say "UTC" or just state the time naturally.

OPENING MESSAGE (if this is the first message in the session):
{
    "Give a warm 1-2 sentence observation about their week based on the data above, then ask what they'd like to do. Be specific — mention a real task or event."
    if user.onboarding_complete
    else "Greet the user and explain that you'll ask a few quick questions to learn how they like to work, so you can plan their week properly."
}"""


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------

async def _execute_tool(
    tool_name: str,
    args: dict,
    db: AsyncSession,
    user: User,
) -> tuple[str, ToolAction]:
    """Execute a tool call and return (result_text, ToolAction)."""

    # ---- get_week_overview ----
    if tool_name == "get_week_overview":
        days = args.get("days", 7)
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        end = now + timedelta(days=days)

        tasks_r = await db.execute(
            select(Task).where(Task.user_id == user.id)
            .where(Task.status != TaskStatus.COMPLETED)
            .where(Task.due_at >= now).where(Task.due_at < end)
            .order_by(Task.due_at)
        )
        tasks = tasks_r.scalars().all()

        events_r = await db.execute(
            select(Event).where(Event.user_id == user.id)
            .where(Event.start >= now).where(Event.start < end)
            .order_by(Event.start)
        )
        events = events_r.scalars().all()

        summary = {
            "tasks_due": len(tasks),
            "tasks": [
                {"id": str(t.id), "name": t.name, "course": t.course_name,
                 "due": t.due_at.isoformat(), "remaining_hours": (t.remaining_minutes or 0) / 60}
                for t in tasks
            ],
            "events": [
                {"google_event_id": e.google_event_id, "title": e.title,
                 "start": e.start.isoformat(), "end": e.end.isoformat()}
                for e in events
            ],
        }
        return json.dumps(summary), ToolAction(tool="get_week_overview", label="Retrieved week overview", success=True)

    # ---- get_tasks ----
    elif tool_name == "get_tasks":
        now = datetime.now(timezone.utc)
        r = await db.execute(
            select(Task).where(Task.user_id == user.id)
            .where(Task.status != TaskStatus.COMPLETED)
            .where(Task.due_at >= now)
            .order_by(Task.due_at).limit(25)
        )
        tasks = r.scalars().all()
        data = [
            {"id": str(t.id), "name": t.name, "course": t.course_name,
             "due": t.due_at.isoformat() if t.due_at else None,
             "remaining_hours": (t.remaining_minutes or 0) / 60}
            for t in tasks
        ]
        return json.dumps(data), ToolAction(tool="get_tasks", label="Retrieved tasks", success=True)

    # ---- get_calendar_events ----
    elif tool_name == "get_calendar_events":
        from datetime import timedelta
        days = args.get("days", 7)
        now = datetime.now(timezone.utc)
        r = await db.execute(
            select(Event).where(Event.user_id == user.id)
            .where(Event.start >= now)
            .where(Event.start < now + timedelta(days=days))
            .order_by(Event.start).limit(30)
        )
        events = r.scalars().all()
        data = [
            {"google_event_id": e.google_event_id, "title": e.title,
             "start": e.start.isoformat(), "end": e.end.isoformat(), "all_day": e.all_day}
            for e in events
        ]
        return json.dumps(data), ToolAction(tool="get_calendar_events", label="Retrieved calendar events", success=True)

    # ---- create_study_block ----
    elif tool_name == "create_study_block":
        task_id = args["task_id"]
        start = _parse_dt(args["start"])
        end = _parse_dt(args["end"])
        title = args.get("title", "Study block")

        task_r = await db.execute(
            select(Task).where(Task.id == uuid.UUID(task_id)).where(Task.user_id == user.id)
        )
        task = task_r.scalar_one_or_none()
        if not task:
            return "Task not found.", ToolAction(tool="create_study_block", label="Task not found", success=False)

        wb = WorkBlock(
            user_id=user.id, task_id=task.id,
            title=title, start=start, end=end,
            status=WorkBlockStatus.PLANNED,
        )
        db.add(wb)
        await db.flush()

        try:
            gid = await sync_workblock_to_calendar(db, user, wb)
            wb.google_event_id = gid
        except Exception as e:
            print(f"Calendar sync failed: {e}")

        await db.commit()
        label = f"Created study block: {title} on {start.strftime('%a %b %d %H:%M')} UTC"
        return f"Study block created: {label}", ToolAction(tool="create_study_block", label=label, success=True)

    # ---- delete_study_block ----
    elif tool_name == "delete_study_block":
        block_id = args["block_id"]
        r = await db.execute(
            select(WorkBlock).where(WorkBlock.id == uuid.UUID(block_id))
            .where(WorkBlock.user_id == user.id)
        )
        wb = r.scalar_one_or_none()
        if not wb:
            return "Block not found.", ToolAction(tool="delete_study_block", label="Block not found", success=False)

        label = f"Deleted study block: {wb.title} on {wb.start.strftime('%a %b %d %H:%M')} UTC"
        if wb.google_event_id:
            await delete_calendar_event(db, user, wb.google_event_id)
        await db.delete(wb)
        await db.commit()
        return f"Deleted: {label}", ToolAction(tool="delete_study_block", label=label, success=True)

    # ---- move_study_block ----
    elif tool_name == "move_study_block":
        block_id = args["block_id"]
        new_start = _parse_dt(args["new_start"])
        new_end = _parse_dt(args["new_end"])

        r = await db.execute(
            select(WorkBlock).where(WorkBlock.id == uuid.UUID(block_id))
            .where(WorkBlock.user_id == user.id)
        )
        wb = r.scalar_one_or_none()
        if not wb:
            return "Block not found.", ToolAction(tool="move_study_block", label="Block not found", success=False)

        old_time = wb.start.strftime('%a %b %d %H:%M')
        label = f"Moved \"{wb.title}\" from {old_time} to {new_start.strftime('%a %b %d %H:%M')} UTC"

        if wb.google_event_id:
            await update_google_event(user, wb.google_event_id, start=new_start, end=new_end)

        wb.start = new_start
        wb.end = new_end
        await db.commit()
        return f"Moved: {label}", ToolAction(tool="move_study_block", label=label, success=True)

    # ---- create_calendar_event ----
    elif tool_name == "create_calendar_event":
        start = _parse_dt(args["start"])
        end = _parse_dt(args["end"])
        title = args["title"]
        description = args.get("description", "")

        gid = await create_google_event(user, title, start, end, description)
        label = f"Created event: \"{title}\" on {start.strftime('%a %b %d %H:%M')} UTC"
        return f"Event created (Google ID: {gid})", ToolAction(tool="create_calendar_event", label=label, success=True)

    # ---- update_calendar_event ----
    elif tool_name == "update_calendar_event":
        gid = args["google_event_id"]
        start = _parse_dt(args["start"]) if "start" in args else None
        end = _parse_dt(args["end"]) if "end" in args else None
        title = args.get("title")

        ok = await update_google_event(user, gid, title=title, start=start, end=end)
        label = f"Updated event {gid}"
        return ("Updated." if ok else "Update failed."), ToolAction(tool="update_calendar_event", label=label, success=ok)

    # ---- delete_calendar_event_tool ----
    elif tool_name == "delete_calendar_event_tool":
        gid = args["google_event_id"]
        event_title = args.get("event_title", gid)
        ok = await delete_calendar_event(db, user, gid)
        label = f"Deleted event: \"{event_title}\""
        return ("Deleted." if ok else "Delete failed."), ToolAction(tool="delete_calendar_event_tool", label=label, success=ok)

    # ---- generate_full_plan ----
    elif tool_name == "generate_full_plan":
        weeks = args.get("weeks", 1)
        from app.services.calendar_write_service import sync_all_workblocks_to_calendar
        result = await generate_weekly_plan(db=db, user_id=user.id, weeks=weeks, user=user)
        if result["blocks_created"] > 0:
            await sync_all_workblocks_to_calendar(db, user)
        label = f"Generated plan: {result['blocks_created']} study blocks across {result['tasks_scheduled']} tasks"
        return json.dumps(result), ToolAction(tool="generate_full_plan", label=label, success=True)

    # ---- save_preference ----
    elif tool_name == "save_preference":
        pref = args["preference"]
        existing = user.ai_preferences or ""
        user.ai_preferences = (existing + "\n" + pref).strip()
        await db.commit()
        return f"Saved preference: {pref}", ToolAction(tool="save_preference", label=f"Saved: {pref}", success=True)

    # ---- save_constraint ----
    elif tool_name == "save_constraint":
        from datetime import time as dtime

        def parse_time(s: Optional[str]):
            if not s:
                return None
            h, m = s.split(":")
            return dtime(int(h), int(m))

        ctype = ConstraintType(args["constraint_type"])
        constraint = Constraint(
            user_id=user.id,
            constraint_type=ctype,
            name=args["name"],
            start_time=parse_time(args.get("start_time")),
            end_time=parse_time(args.get("end_time")),
            days_of_week=args.get("days_of_week", [0, 1, 2, 3, 4, 5, 6]),
            max_minutes=args.get("max_minutes"),
            is_active=True,
        )
        db.add(constraint)
        await db.commit()
        label = f"Saved constraint: {args['name']} ({args['constraint_type']})"
        return label, ToolAction(tool="save_constraint", label=label, success=True)

    # ---- complete_onboarding ----
    elif tool_name == "complete_onboarding":
        user.onboarding_complete = True
        await db.commit()
        return "Onboarding complete.", ToolAction(tool="complete_onboarding", label="Onboarding complete", success=True)

    return f"Unknown tool: {tool_name}", ToolAction(tool=tool_name, label=f"Unknown tool: {tool_name}", success=False)


def _parse_dt(s: str) -> datetime:
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# POST /chat/message
# ---------------------------------------------------------------------------

@router.post("/message", response_model=ChatResponse)
async def chat_message(
    request: ChatRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    system_prompt = await _build_system_prompt(db, user)

    messages = [{"role": "system", "content": system_prompt}]
    for m in request.messages:
        messages.append({"role": m.role, "content": m.content})

    actions: list[ToolAction] = []

    # Agentic loop — keep going until the model stops calling tools
    MAX_ROUNDS = 6
    for _ in range(MAX_ROUNDS):
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.3,
        )

        msg = response.choices[0].message

        # No tool call — final text response
        if not msg.tool_calls:
            return ChatResponse(
                reply=msg.content or "",
                actions=actions,
                onboarding_complete=user.onboarding_complete,
            )

        # Execute each tool call
        messages.append(msg)  # Add assistant message with tool_calls

        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments)
            result_text, action = await _execute_tool(tc.function.name, args, db, user)
            actions.append(action)

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result_text,
            })

    # Safety: if we hit max rounds, return what we have
    return ChatResponse(
        reply="I've completed those actions. Let me know if you'd like anything else.",
        actions=actions,
        onboarding_complete=user.onboarding_complete,
    )


# ---------------------------------------------------------------------------
# GET /chat/status — onboarding state for the frontend
# ---------------------------------------------------------------------------

@router.get("/status")
async def chat_status(
    user: User = Depends(get_current_user),
):
    return {
        "onboarding_complete": user.onboarding_complete,
        "has_preferences": bool(user.ai_preferences),
    }
