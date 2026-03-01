from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.user import User
from app.services.user_service import get_user_by_id
from app.services.workload_service import calculate_workload_ramps

router = APIRouter(prefix="/workload", tags=["workload"])


async def get_current_user(
    user_id: str = Query(..., description="User ID"),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/ramps")
async def get_workload_ramps(
    weeks: int = Query(default=4, ge=2, le=8, description="Number of weeks to show"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get workload ramps for the next N weeks.

    Shows work vs available time per week with load labels:
    - 🟢 Light: < 50% utilization
    - 🟡 Medium: 50-75%
    - 🔴 Heavy: 75-100%
    - ⚫ Overloaded: > 100%
    """
    ramps = await calculate_workload_ramps(db, user.id, weeks)

    return {
        "weeks": ramps,
        "summary": [r["summary"] for r in ramps],
    }
