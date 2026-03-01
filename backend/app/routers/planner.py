from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.user import User
from app.services.user_service import get_user_by_id
from app.services.planner_service import generate_weekly_plan, get_weekly_plan
from app.services.calendar_write_service import sync_all_workblocks_to_calendar

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
    weeks: int = Query(default=1, ge=1, le=4, description="Weeks to plan"),
    block_minutes: int = Query(default=60, ge=30, le=120, description="Block size in minutes"),
    sync_to_calendar: bool = Query(default=False, description="Push blocks to Google Calendar"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a study plan for the next N weeks.

    Creates WorkBlocks for pending tasks and optionally syncs to Google Calendar.
    """
    # Generate the plan
    result = await generate_weekly_plan(db, user.id, weeks, block_minutes)

    # Optionally sync to calendar
    calendar_synced = 0
    if sync_to_calendar and result["blocks_created"] > 0:
        calendar_synced = await sync_all_workblocks_to_calendar(db, user)

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
    return {
        "blocks": blocks,
        "count": len(blocks),
    }


@router.post("/sync-to-calendar")
async def sync_plan_to_calendar(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Push all unsynced WorkBlocks to Google Calendar."""
    count = await sync_all_workblocks_to_calendar(db, user)
    return {
        "events_created": count,
        "message": f"Created {count} events in Google Calendar",
    }
