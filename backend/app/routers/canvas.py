from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.user import User
from app.schemas.canvas import (
    CanvasConnectRequest,
    CanvasCoursesResponse,
    CanvasAssignmentsResponse,
)
from app.schemas.user import UserResponse
from app.services.canvas_service import (
    verify_canvas_token,
    fetch_courses,
    fetch_assignments,
)
from app.services.user_service import get_user_by_id

router = APIRouter(prefix="/canvas", tags=["canvas"])


async def get_current_user(
    user_id: str = Query(..., description="User ID"),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Dependency to get the current user from user_id query param."""
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post("/connect", response_model=UserResponse)
async def connect_canvas(
    request: CanvasConnectRequest,
    user_id: str = Query(..., description="User ID"),
    db: AsyncSession = Depends(get_db),
):
    """
    Connect a Canvas account to the user's profile.
    Verifies the token is valid before saving.
    """
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Verify the token works
    is_valid = await verify_canvas_token(request.canvas_url, request.canvas_token)
    if not is_valid:
        raise HTTPException(
            status_code=400,
            detail="Invalid Canvas URL or token. Please check your credentials.",
        )

    # Save Canvas credentials
    user.canvas_url = request.canvas_url
    user.canvas_token = request.canvas_token
    await db.commit()
    await db.refresh(user)

    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        has_canvas=True,
    )


@router.delete("/disconnect", response_model=UserResponse)
async def disconnect_canvas(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Disconnect Canvas account from user's profile."""
    user.canvas_url = None
    user.canvas_token = None
    await db.commit()
    await db.refresh(user)

    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        has_canvas=False,
    )


@router.get("/courses", response_model=CanvasCoursesResponse)
async def get_courses(
    user: User = Depends(get_current_user),
):
    """Fetch courses from Canvas."""
    if not user.canvas_url or not user.canvas_token:
        raise HTTPException(status_code=400, detail="Canvas not connected")

    try:
        courses = await fetch_courses(user.canvas_url, user.canvas_token)
        return CanvasCoursesResponse(courses=courses, count=len(courses))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/assignments", response_model=CanvasAssignmentsResponse)
async def get_assignments(
    user: User = Depends(get_current_user),
):
    """Fetch upcoming assignments from Canvas."""
    if not user.canvas_url or not user.canvas_token:
        raise HTTPException(status_code=400, detail="Canvas not connected")

    try:
        assignments = await fetch_assignments(user.canvas_url, user.canvas_token)
        return CanvasAssignmentsResponse(assignments=assignments, count=len(assignments))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
