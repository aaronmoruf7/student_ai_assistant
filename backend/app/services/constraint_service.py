from datetime import time
from typing import List
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.constraint import Constraint, ConstraintType


async def get_user_constraints(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> List[Constraint]:
    """Get all active constraints for a user."""
    result = await db.execute(
        select(Constraint)
        .where(Constraint.user_id == user_id)
        .where(Constraint.is_active == True)
    )
    return list(result.scalars().all())


async def create_default_constraints(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> List[Constraint]:
    """
    Create default constraints for a new user.
    - Sleep: 11pm - 7am
    - Lunch: 12pm - 1pm
    - Dinner: 6pm - 7pm
    - Max study: 6 hours/day
    """
    defaults = [
        Constraint(
            user_id=user_id,
            constraint_type=ConstraintType.SLEEP,
            name="Sleep",
            days_of_week=[0, 1, 2, 3, 4, 5, 6],
            start_time=time(23, 0),  # 11pm
            end_time=time(7, 0),     # 7am
        ),
        Constraint(
            user_id=user_id,
            constraint_type=ConstraintType.MEAL,
            name="Lunch",
            days_of_week=[0, 1, 2, 3, 4, 5, 6],
            start_time=time(12, 0),  # 12pm
            end_time=time(13, 0),    # 1pm
        ),
        Constraint(
            user_id=user_id,
            constraint_type=ConstraintType.MEAL,
            name="Dinner",
            days_of_week=[0, 1, 2, 3, 4, 5, 6],
            start_time=time(18, 0),  # 6pm
            end_time=time(19, 0),    # 7pm
        ),
        Constraint(
            user_id=user_id,
            constraint_type=ConstraintType.MAX_HOURS_PER_DAY,
            name="Max daily study",
            max_minutes=360,  # 6 hours
        ),
    ]

    for constraint in defaults:
        db.add(constraint)

    await db.commit()

    # Refresh to get IDs
    for constraint in defaults:
        await db.refresh(constraint)

    return defaults


async def has_constraints(db: AsyncSession, user_id: uuid.UUID) -> bool:
    """Check if user already has constraints set up."""
    result = await db.execute(
        select(Constraint.id).where(Constraint.user_id == user_id).limit(1)
    )
    return result.scalar_one_or_none() is not None
