from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.user import User
from app.schemas.calendar import CalendarEventsResponse
from app.services.calendar_service import fetch_calendar_events
from app.services.user_service import get_user_by_id

router = APIRouter(prefix="/calendar", tags=["calendar"])


async def get_current_user(
    user_id: str = Query(..., description="User ID"),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Dependency to get the current user from user_id query param."""
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/events", response_model=CalendarEventsResponse)
async def get_events(
    weeks: int = Query(default=4, ge=1, le=12, description="Number of weeks to fetch"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Fetch calendar events for the next N weeks.
    """
    try:
        events = await fetch_calendar_events(db, user, weeks)
        return CalendarEventsResponse(events=events, count=len(events))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
