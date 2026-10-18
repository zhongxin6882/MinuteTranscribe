from __future__ import annotations

from typing import Any

from .schema import Transcript


def verify_minutes(minutes: dict[str, Any], transcript: Transcript) -> dict[str, Any]:
    valid_seg_ids = transcript.segment_ids()
    speakers = transcript.speaker_whitelist()

    fields = minutes.get("fields") if isinstance(minutes.get("fields"), dict) else {}
    verified_fields: dict[str, dict[str, Any]] = {}
    for key, item in fields.items():
        if not isinstance(item, dict):
            continue
        evidence = _valid_evidence(item.get("evidence"), valid_seg_ids)
        value = str(item.get("value") or "").strip()
        if value and evidence:
            verified_fields[key] = {"value": value, "evidence": evidence}

    verified_todos: list[dict[str, Any]] = []
    for item in minutes.get("todos") or []:
        if not isinstance(item, dict):
            continue
        task = str(item.get("task") or "").strip()
        evidence = _valid_evidence(item.get("evidence"), valid_seg_ids)
        if not task or not evidence:
            continue
        owner = str(item.get("owner") or "").strip()
        if owner and owner not in speakers:
            owner = ""
        verified_todos.append(
            {
                "task": task,
                "owner": owner,
                "due": str(item.get("due") or "").strip(),
                "extra": str(item.get("extra") or "").strip(),
                "evidence": evidence,
            }
        )

    verified_core = _verify_core(minutes.get("core"), valid_seg_ids)

    verified = dict(minutes)
    verified["fields"] = verified_fields
    verified["todos"] = verified_todos
    verified["core"] = verified_core
    verified["meta"] = {
        **(minutes.get("meta") if isinstance(minutes.get("meta"), dict) else {}),
        "segments_total": len(transcript.segments),
        "segments_cited": len(_all_cited_segments(verified_fields, verified_todos, verified_core)),
        "core_counts": {
            key: len(items) for key, items in verified_core.items()
        },
    }
    return verified


def _verify_core(value: Any, valid_seg_ids: set[str]) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(value, dict):
        value = {}
    return {
        "topics": _verify_topic_items(value.get("topics"), valid_seg_ids),
        "conclusions": _verify_conclusion_items(value.get("conclusions"), valid_seg_ids),
        "decisions": _verify_decision_items(value.get("decisions"), valid_seg_ids),
        "risks": _verify_risk_items(value.get("risks"), valid_seg_ids),
        "open_questions": _verify_open_question_items(value.get("open_questions"), valid_seg_ids),
    }


def _verify_topic_items(value: Any, valid_seg_ids: set[str]) -> list[dict[str, Any]]:
    verified: list[dict[str, Any]] = []
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        detail = str(item.get("detail") or "").strip()
        evidence = _valid_evidence(item.get("evidence"), valid_seg_ids)
        if detail and evidence:
            verified.append({"title": title, "detail": detail, "evidence": evidence})
    return verified


def _verify_conclusion_items(value: Any, valid_seg_ids: set[str]) -> list[dict[str, Any]]:
    verified: list[dict[str, Any]] = []
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        evidence = _valid_evidence(item.get("evidence"), valid_seg_ids)
        status = str(item.get("status") or "").strip() or "confirmed"
        if status not in {"confirmed", "no_conclusion"}:
            status = "confirmed"
        if text and evidence:
            verified.append({"text": text, "status": status, "evidence": evidence})
    return verified


def _verify_decision_items(value: Any, valid_seg_ids: set[str]) -> list[dict[str, Any]]:
    verified: list[dict[str, Any]] = []
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or "").strip()
        decision = str(item.get("decision") or "").strip()
        evidence = _valid_evidence(item.get("evidence"), valid_seg_ids)
        if decision and evidence:
            verified.append({"question": question, "decision": decision, "evidence": evidence})
    return verified


def _verify_risk_items(value: Any, valid_seg_ids: set[str]) -> list[dict[str, Any]]:
    verified: list[dict[str, Any]] = []
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        level = str(item.get("level") or "").strip()
        evidence = _valid_evidence(item.get("evidence"), valid_seg_ids)
        if text and evidence:
            verified.append({"text": text, "level": level, "evidence": evidence})
    return verified


def _verify_open_question_items(value: Any, valid_seg_ids: set[str]) -> list[dict[str, Any]]:
    verified: list[dict[str, Any]] = []
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        evidence = _valid_evidence(item.get("evidence"), valid_seg_ids)
        if text and evidence:
            verified.append({"text": text, "evidence": evidence})
    return verified


def _valid_evidence(value: Any, valid_seg_ids: set[str]) -> list[str]:
    if not isinstance(value, list):
        return []
    return [seg_id for seg_id in value if isinstance(seg_id, str) and seg_id in valid_seg_ids]


def _all_cited_segments(
    fields: dict[str, dict[str, Any]],
    todos: list[dict[str, Any]],
    core: dict[str, list[dict[str, Any]]],
) -> set[str]:
    cited: set[str] = set()
    for item in fields.values():
        cited.update(item.get("evidence") or [])
    for item in todos:
        cited.update(item.get("evidence") or [])
    for bucket in core.values():
        for item in bucket:
            cited.update(item.get("evidence") or [])
    return cited
