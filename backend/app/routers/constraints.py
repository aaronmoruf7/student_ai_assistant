"""
Constraints router — CRUD for user schedule constraints.

Constraints define the base layer of who the user is:
  - Sleep schedule (weekday vs weekend)
  - Protected time (meals, gym, recurring commitments)
  - Max study hours per day
"""
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.constraint import Constraint, ConstraintType
from app.models.user import User
from app.services.user_service import get_user_by_id

router = APIRouter(prefix="/constraints", tags=["constraints"])


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

class ConstraintOut(BaseModel):
    id: str
    constraint_type: str
    name: str
    days_of_week: Optional[list[int]]
    start_time: Optional[str]   # "HH:MM"
    end_time: Optional[str]     # "HH:MM"
    max_minutes: Optional[int]
    is_active: bool


class UpsertConstraintRequest(BaseModel):
    constraint_type: str
    name: str
    days_of_week: Optional[list[int]] = None
    start_time: Optional[str] = None    # "HH:MM"
    end_time: Optional[str] = None      # "HH:MM"
    max_minutes: Optional[int] = None
    is_active: bool = True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_out(c: Constraint) -> dict:
    return {
        "id": str(c.id),
        "constraint_type": c.constraint_type.value,
        "name": c.name,
        "days_of_week": c.days_of_week,
        "start_time": c.start_time.strftime("%H:%M") if c.start_time else None,
        "end_time": c.end_time.strftime("%H:%M") if c.end_time else None,
        "max_minutes": c.max_minutes,
        "is_active": c.is_active,
    }


def _parse_time(value: Optional[str]):
    if not value:
        return None
    from datetime import time
    try:
        h, m = value.split(":")
        return time(int(h), int(m))
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid time format: {value}. Use HH:MM.")


# ---------------------------------------------------------------------------
# GET /constraints
# ---------------------------------------------------------------------------

@router.get("")
async def list_constraints(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Constraint).where(Constraint.user_id == user.id).order_by(Constraint.created_at)
    )
    return {"constraints": [_to_out(c) for c in result.scalars().all()]}


# ---------------------------------------------------------------------------
# POST /constraints
# ---------------------------------------------------------------------------

@router.post("")
async def create_constraint(
    request: UpsertConstraintRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        ctype = ConstraintType(request.constraint_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid constraint_type: {request.constraint_type}")

    constraint = Constraint(
        user_id=user.id,
        constraint_type=ctype,
        name=request.name,
        days_of_week=request.days_of_week,
        start_time=_parse_time(request.start_time),
        end_time=_parse_time(request.end_time),
        max_minutes=request.max_minutes,
        is_active=request.is_active,
    )
    db.add(constraint)
    await db.commit()
    await db.refresh(constraint)
    return _to_out(constraint)


# ---------------------------------------------------------------------------
# PATCH /constraints/{constraint_id}
# ---------------------------------------------------------------------------

@router.patch("/{constraint_id}")
async def update_constraint(
    constraint_id: str,
    request: UpsertConstraintRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Constraint)
        .where(Constraint.id == uuid.UUID(constraint_id))
        .where(Constraint.user_id == user.id)
    )
    constraint = result.scalar_one_or_none()
    if not constraint:
        raise HTTPException(status_code=404, detail="Constraint not found")

    try:
        constraint.constraint_type = ConstraintType(request.constraint_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid constraint_type: {request.constraint_type}")

    constraint.name = request.name
    constraint.days_of_week = request.days_of_week
    constraint.start_time = _parse_time(request.start_time)
    constraint.end_time = _parse_time(request.end_time)
    constraint.max_minutes = request.max_minutes
    constraint.is_active = request.is_active
    constraint.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(constraint)
    return _to_out(constraint)


# ---------------------------------------------------------------------------
# DELETE /constraints/{constraint_id}
# ---------------------------------------------------------------------------

@router.delete("/{constraint_id}")
async def delete_constraint(
    constraint_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Constraint)
        .where(Constraint.id == uuid.UUID(constraint_id))
        .where(Constraint.user_id == user.id)
    )
    constraint = result.scalar_one_or_none()
    if not constraint:
        raise HTTPException(status_code=404, detail="Constraint not found")

    await db.delete(constraint)
    await db.commit()
    return {"deleted": constraint_id}
