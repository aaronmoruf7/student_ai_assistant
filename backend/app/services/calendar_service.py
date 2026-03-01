from datetime import datetime, timedelta
from typing import List

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.schemas.calendar import CalendarEvent
from app.services.google_auth_service import refresh_google_token


async def fetch_calendar_events(
    db: AsyncSession,
    user: User,
    weeks: int = 4,
) -> List[CalendarEvent]:
    """
    Fetch calendar events for the next N weeks from Google Calendar.
    Handles token refresh if needed.
    """
    access_token = user.google_access_token
    if not access_token:
        raise ValueError("User has no Google access token")

    # Time range
    now = datetime.utcnow()
    time_min = now.isoformat() + "Z"
    time_max = (now + timedelta(weeks=weeks)).isoformat() + "Z"

    events = await _fetch_events_with_retry(
        db=db,
        user=user,
        access_token=access_token,
        time_min=time_min,
        time_max=time_max,
    )

    return events


async def _fetch_events_with_retry(
    db: AsyncSession,
    user: User,
    access_token: str,
    time_min: str,
    time_max: str,
) -> List[CalendarEvent]:
    """Fetch events, retrying once with a refreshed token if needed."""

    async with httpx.AsyncClient() as client:
        response = await _call_calendar_api(
            client=client,
            access_token=access_token,
            time_min=time_min,
            time_max=time_max,
        )

        # If unauthorized, try refreshing the token
        if response.status_code == 401:
            access_token = await refresh_google_token(db, user)
            response = await _call_calendar_api(
                client=client,
                access_token=access_token,
                time_min=time_min,
                time_max=time_max,
            )

        if response.status_code != 200:
            raise ValueError(f"Failed to fetch calendar events: {response.text}")

        data = response.json()
        return _parse_events(data.get("items", []), calendar_id="primary")


async def _call_calendar_api(
    client: httpx.AsyncClient,
    access_token: str,
    time_min: str,
    time_max: str,
) -> httpx.Response:
    """Make the actual API call to Google Calendar."""
    return await client.get(
        "https://www.googleapis.com/calendar/v3/calendars/primary/events",
        headers={"Authorization": f"Bearer {access_token}"},
        params={
            "timeMin": time_min,
            "timeMax": time_max,
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": 250,
        },
    )


def _parse_events(items: list, calendar_id: str) -> List[CalendarEvent]:
    """Parse Google Calendar API response into CalendarEvent objects."""
    events = []

    for item in items:
        # Skip cancelled events
        if item.get("status") == "cancelled":
            continue

        start_data = item.get("start", {})
        end_data = item.get("end", {})

        # Handle all-day events vs timed events
        if "date" in start_data:
            # All-day event
            start = datetime.fromisoformat(start_data["date"])
            end = datetime.fromisoformat(end_data["date"])
            all_day = True
        else:
            # Timed event
            start = datetime.fromisoformat(
                start_data.get("dateTime", "").replace("Z", "+00:00")
            )
            end = datetime.fromisoformat(
                end_data.get("dateTime", "").replace("Z", "+00:00")
            )
            all_day = False

        events.append(
            CalendarEvent(
                id=item.get("id", ""),
                summary=item.get("summary", "(No title)"),
                description=item.get("description"),
                start=start,
                end=end,
                all_day=all_day,
                location=item.get("location"),
                calendar_id=calendar_id,
            )
        )

    return events
