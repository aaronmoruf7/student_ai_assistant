"""
Clusters undated Canvas assignment names into representative types using GPT-4o-mini.
e.g. ["Lecture 1 Quiz", "Lecture 2 Quiz", "Lecture 13 Quiz"] → one group: "Lecture Quiz"
"""
import json

from openai import AsyncOpenAI

from app.config import settings

client = AsyncOpenAI(api_key=settings.openai_api_key)

SYSTEM_PROMPT = """You are an expert at recognizing patterns in academic assignment names.

Given a list of assignment names (all from the same course), group them into types based on naming patterns.
Assignments like "Lecture 1 Quiz", "Lecture 2 Quiz", "Lecture 13 Quiz" all belong to the same type: "Lecture Quiz".
Assignments like "Reflection 1 (NOT AI)", "Reflection 2 (NOT AI)" belong to type: "Reflection".

Return a JSON array of groups. Each group must have:
- "type_label": string — a clean, short name for this type (e.g. "Lecture Quiz", "Weekly Reflection", "AI Assignment")
- "representative": string — one example assignment name from the list
- "count": number — how many assignments fall into this group
- "examples": array of strings — up to 3 example names from the list
- "assignment_ids": array of numbers — the Canvas assignment IDs (integers) that belong to this group

Rules:
- Each assignment must belong to exactly one group
- Prefer short, human-readable type labels
- If an assignment doesn't fit any pattern, put it in its own group
- Do not invent groups that have no assignments

Return ONLY the JSON array, no explanation."""


async def cluster_undated_assignments(
    assignments: list[dict],
) -> list[dict]:
    """
    Cluster undated assignment names into representative types.

    Args:
        assignments: List of dicts with keys: id (int), name (str), course_name (str)

    Returns:
        List of cluster dicts with keys:
            type_label, representative, count, examples, assignment_ids
    """
    if not assignments:
        return []

    # Format assignment list for the prompt
    items = "\n".join(
        f"- ID {a['id']}: {a['name']}" for a in assignments
    )

    user_prompt = f"""Course: {assignments[0].get('course_name', 'Unknown')}

Undated assignments to cluster:
{items}

Group these into types based on naming patterns."""

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
        if isinstance(parsed, dict):
            clusters = parsed.get("groups") or parsed.get("clusters") or []
            if not isinstance(clusters, list):
                clusters = next((v for v in parsed.values() if isinstance(v, list)), [])
        else:
            clusters = parsed
    except (json.JSONDecodeError, ValueError):
        return _fallback_clusters(assignments)

    # Validate and normalize
    result = []
    for group in clusters:
        if not isinstance(group, dict) or not group.get("type_label"):
            continue
        result.append({
            "type_label": str(group.get("type_label", "")).strip(),
            "representative": str(group.get("representative", "")).strip(),
            "count": int(group.get("count", 0)),
            "examples": list(group.get("examples", []))[:3],
            "assignment_ids": [int(i) for i in group.get("assignment_ids", []) if str(i).isdigit()],
        })

    return result if result else _fallback_clusters(assignments)


def _fallback_clusters(assignments: list[dict]) -> list[dict]:
    """If LLM fails, return each assignment as its own group."""
    return [
        {
            "type_label": a["name"],
            "representative": a["name"],
            "count": 1,
            "examples": [a["name"]],
            "assignment_ids": [a["id"]],
        }
        for a in assignments
    ]


async def cluster_tasks_for_estimation(
    tasks: list[dict],
) -> list[dict]:
    """
    Cluster task names into types for estimation purposes.
    Accepts tasks with string/UUID IDs by mapping them to temp integers internally.

    Args:
        tasks: List of dicts with keys: id (str/UUID), name (str), course_name (str)

    Returns:
        List of cluster dicts with keys:
            type_label, representative, count, examples, task_ids (list of original string IDs)
    """
    if not tasks:
        return []

    # Map UUID ids → sequential ints for the LLM, keep reverse map
    idx_to_id = {i: str(t["id"]) for i, t in enumerate(tasks)}
    int_assignments = [
        {"id": i, "name": t["name"], "course_name": t.get("course_name", "")}
        for i, t in enumerate(tasks)
    ]

    clusters = await cluster_undated_assignments(int_assignments)

    # Translate integer assignment_ids back to original string UUIDs
    result = []
    for cluster in clusters:
        original_ids = [
            idx_to_id[idx]
            for idx in cluster.get("assignment_ids", [])
            if idx in idx_to_id
        ]
        result.append({
            "type_label": cluster["type_label"],
            "representative": cluster["representative"],
            "count": len(original_ids),
            "examples": cluster["examples"],
            "task_ids": original_ids,
        })

    return result
