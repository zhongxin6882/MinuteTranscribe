from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_manifest(path: str | Path = "evals/manifest.json") -> dict[str, Any]:
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

    core = minutes.get("core") if isinstance(minutes.get("core"), dict) else {}
    haystacks = {
        "topics": _bucket_text(core.get("topics"), ("title", "detail")),
        "conclusions": _bucket_text(core.get("conclusions"), ("text",)),
        "decisions": _bucket_text(core.get("decisions"), ("question", "decision")),
        "risks": _bucket_text(core.get("risks"), ("text", "level")),
        "open_questions": _bucket_text(core.get("open_questions"), ("text",)),
    }

    required_core = case_spec.get("required_core") or {}
    for bucket, keywords in required_core.items():
        for keyword in keywords:
            total_checks += 1
            if keyword in haystacks.get(bucket, ""):
                passed_checks += 1
            else:
                findings.append(f"missing {bucket} keyword: {keyword}")

    todo_text = _todo_text(minutes.get("todos"))
    for keyword in case_spec.get("required_todos") or []:
        total_checks += 1
        if keyword in todo_text:
            passed_checks += 1
        else:
            findings.append(f"missing todo keyword: {keyword}")

    if case_spec.get("require_no_conclusion"):
        total_checks += 1
        if _has_no_conclusion(core):
            passed_checks += 1
        else:
            findings.append("expected a no_conclusion item in core.conclusions")

    if case_spec.get("require_all_todo_owners_empty"):
        total_checks += 1
        if all(not str(item.get("owner") or "").strip() for item in minutes.get("todos") or []):
            passed_checks += 1
        else:
            findings.append("expected all todo owners to be empty")

    full_text = "\n".join(
        [
            haystacks["topics"],
            haystacks["conclusions"],
            haystacks["decisions"],
            haystacks["risks"],
            haystacks["open_questions"],
            todo_text,
            str(minutes.get("summary") or ""),
        ]
    )
    for keyword in case_spec.get("forbidden_text") or []:
        total_checks += 1
        if keyword not in full_text:
            passed_checks += 1
        else:
            findings.append(f"forbidden text present: {keyword}")

    score = round(passed_checks / total_checks, 3) if total_checks else 1.0
    return {
        "ok": not findings,
        "score": score,
        "passed_checks": passed_checks,
        "total_checks": total_checks,
        "findings": findings,
    }


def _bucket_text(items: Any, fields: tuple[str, ...]) -> str:
    parts: list[str] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        for field in fields:
            text = str(item.get(field) or "").strip()
            if text:
                parts.append(text)
    return "\n".join(parts)


def _todo_text(items: Any) -> str:
    parts: list[str] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        for field in ("task", "owner", "due", "extra"):
            text = str(item.get(field) or "").strip()
            if text:
                parts.append(text)
    return "\n".join(parts)


def _has_no_conclusion(core: dict[str, Any]) -> bool:
    for item in core.get("conclusions") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("status") or "").strip() == "no_conclusion":
            return True
        if "未形成明确结论" in str(item.get("text") or ""):
            return True
    return False


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python3 evals/judge_core_recall.py <case_id> <minutes_json_path>")
    case_id = sys.argv[1]
    minutes_path = Path(sys.argv[2])
    case_spec = get_case_spec(case_id)
    minutes = json.loads(minutes_path.read_text(encoding="utf-8"))
    print(json.dumps(evaluate_minutes(case_spec, minutes), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
