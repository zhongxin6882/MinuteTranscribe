from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_manifest(path: str | Path = "evals/summary_manifest.json") -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def get_case_spec(case_id: str, manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    manifest = manifest or load_manifest()
    for case in manifest.get("cases", []):
        if case.get("case_id") == case_id:
            return case
    raise KeyError(f"Unknown case_id: {case_id}")


def evaluate_minutes(case_spec: dict[str, Any], minutes: dict[str, Any]) -> dict[str, Any]:
    findings: list[str] = []
    passed_checks = 0
    total_checks = 0

    allowed_meeting_types = case_spec.get("allowed_meeting_types") or []
    if allowed_meeting_types:
        total_checks += 1
        if str(minutes.get("meeting_type") or "") in allowed_meeting_types:
            passed_checks += 1
        else:
            findings.append(f"meeting_type mismatch: got {minutes.get('meeting_type')}, expected one of {allowed_meeting_types}")

    overview = _overview_text(minutes)
    topics = _topics_text(minutes)
    todos = _todo_text(minutes)

    for keyword in case_spec.get("required_overview") or []:
        total_checks += 1
        if keyword in overview:
            passed_checks += 1
        else:
            findings.append(f"missing overview keyword: {keyword}")

    for keyword in case_spec.get("required_topics") or []:
        total_checks += 1
        if keyword in topics:
            passed_checks += 1
        else:
            findings.append(f"missing topic keyword: {keyword}")

    for keyword in case_spec.get("required_todos") or []:
        total_checks += 1
        if keyword in todos:
            passed_checks += 1
        else:
            findings.append(f"missing todo keyword: {keyword}")

    if case_spec.get("require_all_todo_owners_empty"):
        total_checks += 1
        if all(not str(item.get("owner") or "").strip() for item in _todo_items(minutes)):
            passed_checks += 1
        else:
            findings.append("expected all todo owners to be empty")

    min_topic_count = case_spec.get("min_topic_count")
    if min_topic_count is not None:
        total_checks += 1
        topic_count = len(_topic_items(minutes))
        if topic_count >= int(min_topic_count):
            passed_checks += 1
        else:
            findings.append(f"topic_count too low: {topic_count} < {min_topic_count}")

    min_todo_count = case_spec.get("min_todo_count")
    if min_todo_count is not None:
        total_checks += 1
        todo_count = len(_todo_items(minutes))
        if todo_count >= int(min_todo_count):
            passed_checks += 1
        else:
            findings.append(f"todo_count too low: {todo_count} < {min_todo_count}")

    score = round(passed_checks / total_checks, 3) if total_checks else 1.0
    return {
        "ok": not findings,
        "score": score,
        "passed_checks": passed_checks,
        "total_checks": total_checks,
        "findings": findings,
    }


def _overview_text(minutes: dict[str, Any]) -> str:
    parts = [
        str(minutes.get("summary") or "").strip(),
        str(minutes.get("会议概要") or "").strip(),
    ]
    core = minutes.get("core") if isinstance(minutes.get("core"), dict) else {}
    for bucket in ("topics", "conclusions", "risks", "open_questions"):
        for item in core.get(bucket) or []:
            if not isinstance(item, dict):
                continue
            for field in ("title", "detail", "text"):
                text = str(item.get(field) or "").strip()
                if text:
                    parts.append(text)
    return "\n".join(parts)


def _topics_text(minutes: dict[str, Any]) -> str:
    parts: list[str] = []
    core = minutes.get("core") if isinstance(minutes.get("core"), dict) else {}
    for item in core.get("topics") or []:
        if not isinstance(item, dict):
            continue
        for field in ("title", "detail"):
            text = str(item.get(field) or "").strip()
            if text:
                parts.append(text)
    for item in minutes.get("会议议题") if isinstance(minutes.get("会议议题"), list) else []:
        if not isinstance(item, dict):
            continue
        for field in ("title", "summary", "decision", "结论"):
            text = str(item.get(field) or "").strip()
            if text:
                parts.append(text)
    return "\n".join(parts)


def _topic_items(minutes: dict[str, Any]) -> list[dict[str, Any]]:
    core = minutes.get("core") if isinstance(minutes.get("core"), dict) else {}
    topics = core.get("topics")
    if isinstance(topics, list):
        return [item for item in topics if isinstance(item, dict)]
    section_topics = minutes.get("会议议题")
    if isinstance(section_topics, list):
        return [item for item in section_topics if isinstance(item, dict)]
    return []


def _todo_items(minutes: dict[str, Any]) -> list[dict[str, Any]]:
    todos = minutes.get("todos")
    if isinstance(todos, list):
        return [item for item in todos if isinstance(item, dict)]
    section_todos = minutes.get("待办事项")
    if isinstance(section_todos, list):
        return [item for item in section_todos if isinstance(item, dict)]
    return []


def _todo_text(minutes: dict[str, Any]) -> str:
    parts: list[str] = []
    for item in _todo_items(minutes):
        for field in ("task", "owner", "due", "extra"):
            text = str(item.get(field) or "").strip()
            if text:
                parts.append(text)
    return "\n".join(parts)


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python3 evals/judge_three_section_minutes.py <case_id> <minutes_json_path>")
    case_id = sys.argv[1]
    minutes_path = Path(sys.argv[2])
    case_spec = get_case_spec(case_id)
    minutes = json.loads(minutes_path.read_text(encoding="utf-8"))
    print(json.dumps(evaluate_minutes(case_spec, minutes), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
