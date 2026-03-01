import json
from typing import Optional, Tuple

from openai import AsyncOpenAI

from app.config import settings


async def estimate_task_duration(
    name: str,
    course_name: str,
    description: Optional[str],
    points_possible: Optional[float],
    submission_types: list[str],
) -> Tuple[int, str]:
    """
    Use GPT-4o-mini to estimate how long a task will take.
    Returns (estimated_minutes, reasoning).
    Falls back to rule-based estimation if LLM fails.
    """
    if not settings.openai_api_key:
        return _rule_based_estimate(points_possible, submission_types)

    try:
        client = AsyncOpenAI(api_key=settings.openai_api_key)

        prompt = f"""You are helping a college student estimate how long an assignment will take.

Assignment: {name}
Course: {course_name}
Points: {points_possible or 'Not specified'}
Type: {', '.join(submission_types) if submission_types else 'Not specified'}
Description: {description[:500] if description else 'No description'}

Based on this information, estimate how many minutes this assignment will take to complete.
Consider:
- More points usually means more work
- Essays/papers take longer than quizzes
- Problem sets vary based on course difficulty

Respond with JSON only:
{{"minutes": <number>, "reasoning": "<brief 1-sentence explanation>"}}
"""

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=150,
        )

        content = response.choices[0].message.content.strip()

        # Parse JSON response
        # Handle potential markdown code blocks
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]

        data = json.loads(content)
        minutes = int(data.get("minutes", 60))
        reasoning = data.get("reasoning", "Estimated by AI")

        # Sanity check: clamp between 15 minutes and 10 hours
        minutes = max(15, min(minutes, 600))

        return minutes, reasoning

    except Exception as e:
        # Fall back to rule-based estimation
        print(f"LLM estimation failed: {e}")
        return _rule_based_estimate(points_possible, submission_types)


def _rule_based_estimate(
    points_possible: Optional[float],
    submission_types: list[str],
) -> Tuple[int, str]:
    """
    Simple rule-based estimation as fallback.
    """
    # Base estimate from points
    if points_possible:
        if points_possible <= 10:
            base_minutes = 30
        elif points_possible <= 25:
            base_minutes = 60
        elif points_possible <= 50:
            base_minutes = 90
        elif points_possible <= 100:
            base_minutes = 150
        else:
            base_minutes = 180
    else:
        base_minutes = 60  # Default 1 hour

    # Adjust based on submission type
    submission_types_lower = [s.lower() for s in submission_types]

    if any("quiz" in s or "test" in s for s in submission_types_lower):
        base_minutes = int(base_minutes * 0.7)  # Quizzes are usually faster
    elif any("essay" in s or "paper" in s or "written" in s for s in submission_types_lower):
        base_minutes = int(base_minutes * 1.5)  # Writing takes longer
    elif any("discussion" in s for s in submission_types_lower):
        base_minutes = max(30, int(base_minutes * 0.5))  # Discussions are quick

    reasoning = f"Rule-based: {points_possible or 'unknown'} points, {submission_types[0] if submission_types else 'unknown'} type"

    return base_minutes, reasoning
