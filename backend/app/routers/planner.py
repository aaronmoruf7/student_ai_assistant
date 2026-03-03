from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.user import User
from app.services.user_service import get_user_by_id
from app.services.planner_service import generate_weekly_plan, get_weekly_plan
from app.services.calendar_write_service import sync_all_workblocks_to_calendar
from app.services.google_auth_service import refresh_google_token


class ImportEvent(BaseModel):
    title: str
    start: str          # ISO 8601, local time, no timezone suffix
    end: str            # ISO 8601, local time, no timezone suffix
    description: Optional[str] = ""


class ImportPlanRequest(BaseModel):
    events: List[ImportEvent]

router = APIRouter(prefix="/planner", tags=["planner"])


async def get_current_user(
    user_id: str = Query(..., description="User ID"),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post("/generate")
async def generate_plan(
    weeks: int = Query(default=1, ge=1, le=4),
    block_minutes: int = Query(default=60, ge=30, le=120),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a study plan for the next N weeks.

    Cleans up old planned WorkBlocks and their Google Calendar events first,
    then creates a new LLM-based plan and syncs it to Google Calendar.
    """
    result = await generate_weekly_plan(
        db=db,
        user_id=user.id,
        weeks=weeks,
        block_minutes=block_minutes,
        user=user,
    )

    # Always sync to Google Calendar after generating
    calendar_synced = 0
    if result["blocks_created"] > 0:
        try:
            calendar_synced = await sync_all_workblocks_to_calendar(db, user)
        except Exception as e:
            print(f"Calendar sync failed after planning: {e}")

    return {
        **result,
        "calendar_events_created": calendar_synced,
    }


@router.get("/blocks")
async def get_plan_blocks(
    weeks: int = Query(default=1, ge=1, le=4),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current WorkBlocks for the next N weeks."""
    blocks = await get_weekly_plan(db, user.id, weeks)
    return {"blocks": blocks, "count": len(blocks)}


@router.post("/import")
async def import_plan_events(
    request: ImportPlanRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Import LLM-generated plan events directly into Google Calendar.
    Times are treated as local time (no UTC conversion) so GCal uses
    the calendar's own timezone setting.
    """
    if not user.google_access_token:
        raise HTTPException(status_code=400, detail="Google Calendar not connected")

    created = 0
    errors = []

    async with httpx.AsyncClient() as client:
        access_token = user.google_access_token

        for ev in request.events:
            event_data = {
                "summary": ev.title,
                "description": ev.description or "Imported via Student AI Assistant",
                # No timeZone field → GCal uses the calendar's default timezone
                "start": {"dateTime": ev.start},
                "end": {"dateTime": ev.end},
                "colorId": "9",
            }

            response = await client.post(
                "https://www.googleapis.com/calendar/v3/calendars/primary/events",
                headers={"Authorization": f"Bearer {access_token}"},
                json=event_data,
            )

            if response.status_code == 401:
                access_token = await refresh_google_token(db, user)
                response = await client.post(
                    "https://www.googleapis.com/calendar/v3/calendars/primary/events",
                    headers={"Authorization": f"Bearer {access_token}"},
                    json=event_data,
                )

            if response.status_code in (200, 201):
                created += 1
            else:
                errors.append({"title": ev.title, "error": response.text})

    return {"created": created, "errors": errors}


@router.post("/sync-to-calendar")
async def sync_plan_to_calendar(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Push any unsynced WorkBlocks to Google Calendar."""
    count = await sync_all_workblocks_to_calendar(db, user)
    return {
        "events_created": count,
        "message": f"Created {count} events in Google Calendar",
    }
