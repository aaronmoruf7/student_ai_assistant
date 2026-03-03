"""
Extracts structured tasks from pasted syllabus/course content using GPT-4o-mini.
Returns a list of tasks with title, type, due_date, and confidence score.
"""
import json
from datetime import datetime
from typing import Optional

from openai import AsyncOpenAI

from app.config import settings

client = AsyncOpenAI(api_key=settings.openai_api_key)

SYSTEM_PROMPT = """You are an expert at reading academic syllabi and course content and extracting assignment deadlines.

Given pasted course content (syllabus, schedule, assignment list, etc.), extract every assignment, quiz, exam, project, or deliverable that a student needs to complete.

Return a JSON array. Each item must have:
- "title": string — clear name of the task (e.g. "Midterm Exam", "Problem Set 3", "Lab Report 2")
- "type": string — category (e.g. "Exam", "Quiz", "Essay", "Problem Set", "Lab", "Project", "Reflection", "Reading", "Homework")
- "due_date": string or null — ISO 8601 date (YYYY-MM-DD) if found, null if no date given
- "confidence": number — 0.0 to 1.0, how confident you are this is a real graded task with the correct date
  - 1.0 = explicit name + explicit date
  - 0.7-0.9 = clear task, date is implied or approximate
  - 0.4-0.6 = task exists but details are unclear
  - below 0.4 = very uncertain

Rules:
- Only include graded or required tasks (skip optional readings, course policies, general info)
- Do not invent tasks that are not in the content
- If you see recurring tasks (e.g. "weekly quiz every Monday"), list each one individually if dates are known, or one representative entry if dates are not
- Prefer specificity — "Essay 2: Climate Policy" is better than "Essay"

Return ONLY the JSON array, no explanation."""


async def extract_tasks_from_content(
    content: str,
    course_name: str,
    current_year: int = None,
) -> list[dict]:
    """
    Extract structured tasks from pasted course content.

    Args:
        content: Raw pasted text (syllabus, schedule, etc.)
        course_name: Name of the course (for context)
        current_year: Current year for date parsing context

    Returns:
        List of dicts with keys: title, type, due_date, confidence
    """
    if current_year is None:
        current_year = datetime.utcnow().year

    user_prompt = f"""Course: {course_name}
Current year: {current_year}

--- PASTED CONTENT ---
{content[:8000]}
--- END CONTENT ---

Extract all assignments and deadlines from the above content."""

    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content

    try:
        parsed = json.loads(raw)
        # Handle both {"tasks": [...]} and bare [...]
        if isinstance(parsed, dict):
            tasks = parsed.get("tasks") or parsed.get("assignments") or []
            # If still a dict, try first list value
            if not isinstance(tasks, list):
                tasks = next((v for v in parsed.values() if isinstance(v, list)), [])
        else:
            tasks = parsed
    except (json.JSONDecodeError, ValueError):
        return []

    # Normalize and validate each task
    result = []
    for item in tasks:
        if not isinstance(item, dict) or not item.get("title"):
            continue

        result.append({
            "title": str(item.get("title", "")).strip(),
            "type": str(item.get("type", "Assignment")).strip(),
            "due_date": _normalize_date(item.get("due_date")),
            "confidence": _clamp(float(item.get("confidence", 0.5))),
        })

    return result


def _normalize_date(value) -> Optional[str]:
    """Normalize a date value to ISO string (YYYY-MM-DD) or None."""
    if not value or value == "null":
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        # Already ISO format
        if len(value) >= 10 and value[4] == "-":
            return value[:10]
    return None


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
