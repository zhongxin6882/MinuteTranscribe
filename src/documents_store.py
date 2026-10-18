from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .render import render_document_html, render_html, render_markdown
from .schema import Segment, Transcript

STORE_ROOT = Path("data/minutes")
TITLE_LIMIT = 120
LEGACY_TEMPLATE_MARKERS = (
    "## 会议概况",
    "1. 进展与现状",
    "2. 问题与风险",
    "3. 决策与共识",
    "4. 后续部署",
)


def list_documents(user_id: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    store_root = _store_root(user_id)
    if not store_root.exists():
        return records
    for path in store_root.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        records.append(_to_summary(payload))
    records.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    return records


def get_document(user_id: str, meeting_id: str) -> dict[str, Any] | None:
    path = _record_path(user_id, meeting_id)
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return _maybe_migrate_legacy_template(user_id, payload)


def delete_document(user_id: str, meeting_id: str) -> bool:
    path = _record_path(user_id, meeting_id)
    if not path.exists():
        return False
    path.unlink()
    return True


def create_draft_document(user_id: str, title: str | None = None, status: str = "草稿") -> dict[str, Any]:
    now = _now_iso()
    meeting_id = _new_draft_id()
    record = {
        "id": meeting_id,
        "owner_id": user_id,
        "title": _normalize_title(title, now),
        "status": status or "草稿",
        "meeting_type": "general_meeting",
        "created_at": now,
        "updated_at": now,
        "markdown": "",
        "document_html": "",
        "html": "",
        "minutes": {},
        "transcript": {"meeting_id": meeting_id, "segments": []},
        "input_kind": "text",
        "source_input": "",
        "media_path": "",
        "media_name": "",
        "media_mime": "",
        "failure_reason": "",
    }
    _ensure_store_root(user_id)
    _record_path(user_id, meeting_id).write_text(
        json.dumps(record, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return record


def update_document_content(
    user_id: str,
    meeting_id: str,
    *,
    document_html: str,
    markdown: str | None = None,
    title: str | None = None,
    status: str | None = None,
    source_input: str | None = None,
    input_kind: str | None = None,
    transcript: dict[str, Any] | None = None,
    media_path: str | None = None,
    media_name: str | None = None,
    media_mime: str | None = None,
    failure_reason: str | None = None,
) -> dict[str, Any] | None:
    existing = get_document(user_id, meeting_id)
    if not existing:
        return None
    existing["document_html"] = document_html
    if markdown is not None:
        existing["markdown"] = markdown
    if title is not None:
        existing["title"] = _normalize_title(title, existing.get("created_at") or _now_iso())
    if status is not None:
        existing["status"] = status
    if source_input is not None:
        existing["source_input"] = source_input
    if input_kind is not None:
        existing["input_kind"] = input_kind
    if transcript is not None:
        existing["transcript"] = transcript
    if media_path is not None:
        existing["media_path"] = media_path
    if media_name is not None:
        existing["media_name"] = media_name
    if media_mime is not None:
        existing["media_mime"] = media_mime
    if failure_reason is not None:
        existing["failure_reason"] = str(failure_reason or "")
    existing["updated_at"] = _now_iso()
    _ensure_store_root(user_id)
    _record_path(user_id, meeting_id).write_text(
        json.dumps(existing, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return existing


def save_generated_document(
    user_id: str,
    transcript: Transcript,
    minutes: dict[str, Any],
    markdown: str,
    document_html: str,
    html_doc: str,
    input_kind: str = "text",
    source_input: str = "",
    media_path: str = "",
    media_name: str = "",
    media_mime: str = "",
) -> dict[str, Any]:
    existing = get_document(user_id, transcript.meeting_id)
    if not existing and media_path:
        existing = _find_document_by_media_path(user_id, media_path)
    now = _now_iso()
    created_at = existing.get("created_at") if existing else now
    title = _normalize_title(existing.get("title") if existing else None, created_at)
    record_id = existing.get("id") if existing else transcript.meeting_id
    transcript_record = transcript if transcript.meeting_id == record_id else Transcript(meeting_id=record_id, segments=transcript.segments)
    record = {
        "id": record_id,
        "owner_id": user_id,
        "title": title,
        "status": "纪要已生成",
        "meeting_type": minutes.get("meeting_type") or "general_meeting",
        "created_at": created_at,
        "updated_at": now,
        "markdown": markdown,
        "document_html": document_html,
        "html": html_doc,
        "minutes": minutes,
        "transcript": transcript_record.to_dict(),
        "input_kind": input_kind,
        "source_input": source_input,
        "media_path": media_path,
        "media_name": media_name,
        "media_mime": media_mime,
        "failure_reason": "",
    }
    _ensure_store_root(user_id)
    _record_path(user_id, record_id).write_text(
        json.dumps(record, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return record


def _to_summary(record: dict[str, Any]) -> dict[str, Any]:
    minutes = record.get("minutes") if isinstance(record.get("minutes"), dict) else {}
    preview = ""
    summary = str(minutes.get("summary") or "").strip()
    if summary:
        preview = summary
    else:
        core = minutes.get("core") if isinstance(minutes.get("core"), dict) else {}
        for bucket in ("topics", "conclusions", "risks", "open_questions"):
            items = core.get(bucket)
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                value = str(item.get("detail") or item.get("text") or item.get("title") or "").strip()
                if value:
                    preview = value
                    break
            if preview:
                break
    if not preview:
        preview = str(record.get("source_input") or "").strip().replace("\n", " ")
    return {
        "id": record.get("id") or "",
        "title": record.get("title") or "未命名会议",
        "status": record.get("status") or "草稿",
        "meeting_type": record.get("meeting_type") or minutes.get("meeting_type") or "general_meeting",
        "created_at": record.get("created_at") or "",
        "updated_at": record.get("updated_at") or "",
        "preview": preview[:72],
        "failure_reason": str(record.get("failure_reason") or ""),
    }


def _record_path(user_id: str, meeting_id: str) -> Path:
    safe_name = "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in meeting_id)
    return _store_root(user_id) / f"{safe_name}.json"


def _store_root(user_id: str) -> Path:
    safe_user_id = "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in user_id)
    return STORE_ROOT / safe_user_id


def _ensure_store_root(user_id: str) -> None:
    _store_root(user_id).mkdir(parents=True, exist_ok=True)


def _find_document_by_media_path(user_id: str, media_path: str) -> dict[str, Any] | None:
    target = str(Path(media_path).resolve()) if media_path else ""
    if not target:
        return None
    store_root = _store_root(user_id)
    if not store_root.exists():
        return None
    candidates: list[dict[str, Any]] = []
    for path in store_root.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        current_path = str(payload.get("media_path") or "")
        if not current_path:
            continue
        try:
            current_resolved = str(Path(current_path).resolve())
        except FileNotFoundError:
            current_resolved = str(Path(current_path).absolute())
        if current_resolved != target:
            continue
        if str(payload.get("status") or "") in {"草稿", "纪要生成中"}:
            candidates.append(payload)
    if not candidates:
        return None
    candidates.sort(key=lambda item: item.get("updated_at") or item.get("created_at") or "", reverse=True)
    return candidates[0]


def _default_title(created_at: str) -> str:
    return "未命名"


def _normalize_title(title: str | None, created_at: str) -> str:
    value = (title or "").strip()
    if not value:
        return _default_title(created_at)
    return value[:TITLE_LIMIT]


def _maybe_migrate_legacy_template(user_id: str, record: dict[str, Any]) -> dict[str, Any]:
    if str(record.get("status") or "") != "纪要已生成":
        return record
    if not _is_legacy_template(record):
        return record
    minutes = record.get("minutes") if isinstance(record.get("minutes"), dict) else {}
    if not minutes:
        return record
    transcript = _transcript_from_dict(
        record.get("transcript") if isinstance(record.get("transcript"), dict) else {},
        meeting_id=str(record.get("id") or ""),
    )
    markdown = render_markdown(minutes, transcript)
    document_html = render_document_html(markdown)
    html_doc = render_html(markdown, transcript, minutes)
    record["markdown"] = markdown
    record["document_html"] = document_html
    record["html"] = html_doc
    record["updated_at"] = _now_iso()
    _ensure_store_root(user_id)
    _record_path(user_id, str(record.get("id") or "")).write_text(
        json.dumps(record, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return record


def _is_legacy_template(record: dict[str, Any]) -> bool:
    markdown = str(record.get("markdown") or "")
    document_html = str(record.get("document_html") or "")
    for marker in LEGACY_TEMPLATE_MARKERS:
        if marker in markdown:
            return True
    html_markers = ("会议概况", "进展与现状", "问题与风险", "决策与共识", "后续部署")
    return any(marker in document_html for marker in html_markers)


def _transcript_from_dict(payload: dict[str, Any], meeting_id: str) -> Transcript:
    segments_payload = payload.get("segments") if isinstance(payload.get("segments"), list) else []
    segments: list[Segment] = []
    for index, item in enumerate(segments_payload, start=1):
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or item.get("cleaned_text") or "").strip()
        if not text:
            continue
        cleaned = str(item.get("cleaned_text") or text).strip()
        segments.append(
            Segment(
                seg_id=str(item.get("seg_id") or f"seg_{index:03d}"),
                speaker=str(item.get("speaker")) if item.get("speaker") is not None else None,
                start=str(item.get("start")) if item.get("start") is not None else None,
                text=text,
                cleaned_text=cleaned,
            )
        )
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else None
    return Transcript(meeting_id=meeting_id or str(payload.get("meeting_id") or "restored_minutes"), segments=segments, meta=meta)


def _new_draft_id() -> str:
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"draft_{timestamp}_{uuid4().hex[:8]}"


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")
