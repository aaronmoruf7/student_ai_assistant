from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel


class CanvasConnectRequest(BaseModel):
    """Request to connect a Canvas account."""
    canvas_url: str  # e.g., "canvas.harvard.edu"
    canvas_token: str


class CanvasCourse(BaseModel):
    """A course from Canvas."""
    id: int
    name: str
    code: str
    term: Optional[str] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None


class CanvasAssignment(BaseModel):
    """An assignment from Canvas."""
    id: int
    course_id: int
    course_name: str
    name: str
    description: Optional[str] = None
    due_at: Optional[datetime] = None
    points_possible: Optional[float] = None
    submission_types: List[str] = []
    has_submitted: bool = False


class CanvasCoursesResponse(BaseModel):
    """Response containing list of courses."""
    courses: List[CanvasCourse]
    count: int


class CanvasAssignmentsResponse(BaseModel):
    """Response containing list of assignments."""
    assignments: List[CanvasAssignment]
    count: int
