from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel


class CalendarEvent(BaseModel):
    """A calendar event from Google Calendar."""
    id: str
    summary: str
    description: Optional[str] = None
    start: datetime
    end: datetime
    all_day: bool = False
    location: Optional[str] = None
    calendar_id: str
    calendar_name: Optional[str] = None


class CalendarEventsResponse(BaseModel):
    """Response containing list of calendar events."""
    events: List[CalendarEvent]
    count: int
