import uuid
from datetime import datetime
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.workblock import WorkBlock
from app.services.google_auth_service import refresh_google_token


async def sync_workblock_to_calendar(
    db: AsyncSession,
    user: User,
    workblock: WorkBlock,
) -> str:
    """
    Create a Google Calendar event for a WorkBlock.
    Returns the Google event ID.
    """
    access_token = user.google_access_token
    if not access_token:
        raise ValueError("User has no Google access token")

    event_data = {
        "summary": workblock.title,
        "start": {
            "dateTime": workblock.start.isoformat(),
            "timeZone": "UTC",
        },
        "end": {
            "dateTime": workblock.end.isoformat(),
            "timeZone": "UTC",
        },
        "description": "Created by Student AI Assistant",
        "colorId": "9",  # Blue color
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            headers={"Authorization": f"Bearer {access_token}"},
            json=event_data,
        )

        # If unauthorized, refresh token and retry
        if response.status_code == 401:
            access_token = await refresh_google_token(db, user)
            response = await client.post(
                "https://www.googleapis.com/calendar/v3/calendars/primary/events",
                headers={"Authorization": f"Bearer {access_token}"},
                json=event_data,
            )

        if response.status_code not in (200, 201):
            raise ValueError(f"Failed to create calendar event: {response.text}")

        event = response.json()
        return event["id"]


async def sync_all_workblocks_to_calendar(
    db: AsyncSession,
    user: User,
) -> int:
    """
    Sync all unsycned WorkBlocks to Google Calendar.
    Returns count of events created.
    """
    # Get unsynced workblocks
    result = await db.execute(
        select(WorkBlock)
        .where(WorkBlock.user_id == user.id)
        .where(WorkBlock.google_event_id == None)
        .where(WorkBlock.start >= datetime.utcnow())
    )
    workblocks = result.scalars().all()

    count = 0
    for wb in workblocks:
        try:
            google_event_id = await sync_workblock_to_calendar(db, user, wb)
            wb.google_event_id = google_event_id
            count += 1
        except Exception as e:
            print(f"Failed to sync workblock {wb.id}: {e}")

    await db.commit()
    return count


async def delete_calendar_event(
    db: AsyncSession,
    user: User,
    google_event_id: str,
) -> bool:
    """Delete a Google Calendar event."""
    access_token = user.google_access_token
    if not access_token:
        return False

    async with httpx.AsyncClient() as client:
        response = await client.delete(
            f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{google_event_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        if response.status_code == 401:
            access_token = await refresh_google_token(db, user)
            response = await client.delete(
                f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{google_event_id}",
                headers={"Authorization": f"Bearer {access_token}"},
            )

        return response.status_code in (200, 204)
