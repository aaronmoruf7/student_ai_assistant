from datetime import datetime, timezone
from typing import List, Tuple

import httpx

from app.schemas.canvas import CanvasCourse, CanvasAssignment


def _build_base_url(canvas_url: str) -> str:
    """Build the Canvas API base URL from the user's Canvas domain."""
    # Remove protocol if provided
    url = canvas_url.replace("https://", "").replace("http://", "")
    # Remove trailing slash
    url = url.rstrip("/")
    return f"https://{url}/api/v1"


async def verify_canvas_token(canvas_url: str, token: str) -> bool:
    """Verify that the Canvas token is valid by fetching user info."""
    base_url = _build_base_url(canvas_url)

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{base_url}/users/self",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10.0,
        )
        return response.status_code == 200


async def fetch_courses(canvas_url: str, token: str) -> List[CanvasCourse]:
    """Fetch active courses from Canvas."""
    base_url = _build_base_url(canvas_url)
    courses = []

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{base_url}/courses",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "enrollment_state": "active",
                "include[]": ["term", "total_scores"],
                "per_page": 100,
            },
            timeout=10.0,
        )

        if response.status_code != 200:
            raise ValueError(f"Failed to fetch courses: {response.text}")

        for course in response.json():
            # Skip courses without a name (access restricted)
            if not course.get("name"):
                continue

            term_name = None
            if course.get("term"):
                term_name = course["term"].get("name")

            courses.append(
                CanvasCourse(
                    id=course["id"],
                    name=course["name"],
                    code=course.get("course_code", ""),
                    term=term_name,
                    start_at=_parse_datetime(course.get("start_at")),
                    end_at=_parse_datetime(course.get("end_at")),
                )
            )

    return courses


async def fetch_assignments(
    canvas_url: str,
    token: str,
    courses: List[CanvasCourse] = None,
) -> List[CanvasAssignment]:
    """
    Fetch upcoming dated assignments from Canvas (due in the future).
    If courses not provided, fetches them first.
    """
    base_url = _build_base_url(canvas_url)

    if courses is None:
        courses = await fetch_courses(canvas_url, token)

    course_map = {c.id: c.name for c in courses}
    assignments = []
    now = datetime.now(timezone.utc)

    async with httpx.AsyncClient() as client:
        for course in courses:
            response = await client.get(
                f"{base_url}/courses/{course.id}/assignments",
                headers={"Authorization": f"Bearer {token}"},
                params={
                    "per_page": 100,
                    "order_by": "due_at",
                },
                timeout=10.0,
            )

            if response.status_code != 200:
                continue

            for assignment in response.json():
                due_at = _parse_datetime(assignment.get("due_at"))

                # Skip assignments without due dates or already past
                if not due_at or due_at < now:
                    continue

                assignments.append(
                    CanvasAssignment(
                        id=assignment["id"],
                        course_id=course.id,
                        course_name=course_map.get(course.id, "Unknown"),
                        name=assignment["name"],
                        description=_clean_html(assignment.get("description")),
                        due_at=due_at,
                        points_possible=assignment.get("points_possible"),
                        submission_types=assignment.get("submission_types", []),
                        has_submitted=assignment.get("has_submitted_submissions", False),
                    )
                )

    assignments.sort(key=lambda a: a.due_at)
    return assignments


async def fetch_undated_assignments(
    canvas_url: str,
    token: str,
    canvas_course_ids: List[int],
) -> List[CanvasAssignment]:
    """
    Fetch assignments with no due date for the given course IDs.
    Used during setup to identify undated assignments for clustering.
    """
    base_url = _build_base_url(canvas_url)
    courses = await fetch_courses(canvas_url, token)
    course_map = {c.id: c.name for c in courses}

    # Filter to only the requested courses
    selected_courses = [c for c in courses if c.id in canvas_course_ids]

    undated = []

    async with httpx.AsyncClient() as client:
        for course in selected_courses:
            response = await client.get(
                f"{base_url}/courses/{course.id}/assignments",
                headers={"Authorization": f"Bearer {token}"},
                params={"per_page": 100},
                timeout=10.0,
            )

            if response.status_code != 200:
                continue

            for assignment in response.json():
                due_at = _parse_datetime(assignment.get("due_at"))

                # Only undated assignments
                if due_at is not None:
                    continue

                undated.append(
                    CanvasAssignment(
                        id=assignment["id"],
                        course_id=course.id,
                        course_name=course_map.get(course.id, "Unknown"),
                        name=assignment["name"],
                        description=_clean_html(assignment.get("description")),
                        due_at=None,
                        points_possible=assignment.get("points_possible"),
                        submission_types=assignment.get("submission_types", []),
                        has_submitted=assignment.get("has_submitted_submissions", False),
                    )
                )

    return undated


def _parse_datetime(value: str) -> datetime:
    """Parse ISO datetime string from Canvas."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _clean_html(html: str) -> str:
    """Basic HTML tag removal for descriptions."""
    if not html:
        return None
    # Very basic cleaning - just remove tags
    import re
    clean = re.sub(r"<[^>]+>", "", html)
    # Collapse whitespace
    clean = re.sub(r"\s+", " ", clean).strip()
    # Truncate if too long
    if len(clean) > 500:
        clean = clean[:500] + "..."
    return clean
