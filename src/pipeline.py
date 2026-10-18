from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .classify import classify_transcript
from .generate import generate_minutes
from .media_ingest import transcript_from_media_bytes, transcript_from_media_path
from .llm import LLMClient, LLMConfig, LLMError
from .render import write_outputs
from .validate import load_transcript, transcript_from_json, transcript_from_text
from .verify import verify_minutes


def run(input_path: str | Path, output_dir: str | Path) -> dict[str, Path]:
    transcript = load_input(input_path)
    verified_minutes = run_transcript(transcript)
    return write_outputs(output_dir, transcript, verified_minutes)


def run_transcript(transcript, user_id: str | None = None):
    result = run_transcript_debug(transcript, user_id)
    if result["error"]:
        raise LLMError(str(result["error"]))
    return result["verified_minutes"]


def run_transcript_debug(transcript, user_id: str | None = None):
    classification = classify_transcript(transcript)
    llm = LLMClient(LLMConfig.from_env(user_id))
    raw_minutes = generate_minutes(transcript, classification, llm)
    verified_minutes = verify_minutes(raw_minutes, transcript)
    error: str | None = None
    if not has_renderable_content(verified_minutes):
        error = _build_renderability_failure_reason(raw_minutes, verified_minutes)
    return {
        "classification": classification.to_dict(),
        "raw_minutes": raw_minutes,
        "verified_minutes": verified_minutes,
        "error": error,
    }


def transcript_from_payload(payload: dict[str, Any]):
    meeting_id = str(payload.get("meeting_id") or "").strip() or _new_meeting_id()
    if payload.get("kind") == "json":
        return transcript_from_json(payload["transcript"], fallback_id=meeting_id)
    if payload.get("kind") == "media":
        media_data = payload.get("media_data")
        media_name = str(payload.get("media_name") or payload.get("media_path") or "media.wav")
        user_id = str(payload.get("user_id") or "") or None
        meeting_id = str(payload.get("meeting_id") or "").strip() or None
        media_path = str(payload.get("media_path") or "").strip()
        if media_path:
            return transcript_from_media_path(media_path, user_id=user_id, meeting_id=meeting_id)
        if isinstance(media_data, str) and media_data:
            import base64

            raw = media_data.split(",", 1)[-1]
            return transcript_from_media_bytes(base64.b64decode(raw), media_name, user_id=user_id, meeting_id=meeting_id)
        return transcript_from_media_path(str(payload.get("media_path") or ""), user_id=user_id, meeting_id=meeting_id)
    return transcript_from_text(str(payload.get("text") or ""), meeting_id=meeting_id)


def load_input(path: str | Path):
    source = Path(path)
    if source.suffix.lower() in {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".webm", ".aif", ".aiff", ".mp4", ".mov", ".mkv", ".avi", ".m4v"}:
        return transcript_from_media_path(source)
    return load_transcript(source)


def _new_meeting_id() -> str:
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"meeting_{timestamp}_{uuid4().hex[:8]}"


def has_renderable_content(minutes: dict[str, Any]) -> bool:
    todos = minutes.get("todos") if isinstance(minutes.get("todos"), list) else []
    if any(str(item.get("task") or "").strip() for item in todos if isinstance(item, dict)):
        return True
    core = minutes.get("core") if isinstance(minutes.get("core"), dict) else {}
    for key in ("topics", "conclusions", "decisions", "risks", "open_questions"):
        bucket = core.get(key)
        if isinstance(bucket, list) and bucket:
            return True
    return False


def _build_renderability_failure_reason(raw_minutes: dict[str, Any], verified_minutes: dict[str, Any]) -> str:
    raw_core = raw_minutes.get("core") if isinstance(raw_minutes.get("core"), dict) else {}
    verified_core = verified_minutes.get("core") if isinstance(verified_minutes.get("core"), dict) else {}
    raw_todos = raw_minutes.get("todos") if isinstance(raw_minutes.get("todos"), list) else []
    verified_todos = verified_minutes.get("todos") if isinstance(verified_minutes.get("todos"), list) else []

    raw_topic_values = len(raw_core.get("topics") or []) if isinstance(raw_core.get("topics"), list) else 0
    raw_conclusion_values = len(raw_core.get("conclusions") or []) if isinstance(raw_core.get("conclusions"), list) else 0
    verified_topic_values = len(verified_core.get("topics") or []) if isinstance(verified_core.get("topics"), list) else 0
    verified_conclusion_values = len(verified_core.get("conclusions") or []) if isinstance(verified_core.get("conclusions"), list) else 0

    raw_todo_values = sum(
        1
        for item in raw_todos
        if isinstance(item, dict) and str(item.get("task") or "").strip()
    )
    raw_todos_with_evidence = sum(
        1
        for item in raw_todos
        if isinstance(item, dict)
        and str(item.get("task") or "").strip()
        and isinstance(item.get("evidence"), list)
        and any(str(seg_id).strip() for seg_id in item.get("evidence"))
    )
    verified_todo_values = sum(
        1
        for item in verified_todos
        if isinstance(item, dict) and str(item.get("task") or "").strip()
    )

    if raw_topic_values == 0 and raw_conclusion_values == 0 and raw_todo_values == 0:
        return "本次输出未达到纪要生成标准：模型没有提取出可展示的议题、结论或待办。"

    reasons: list[str] = []

    if raw_topic_values == 0:
        reasons.append("模型没有提取出可展示的议题内容")
    elif verified_topic_values == 0:
        reasons.append(f"模型提取了 {raw_topic_values} 个议题对象，但证据校验后全部被过滤")

    if raw_conclusion_values == 0:
        reasons.append("模型没有提取出可展示的结论内容")
    elif verified_conclusion_values == 0:
        reasons.append(f"模型提取了 {raw_conclusion_values} 个结论对象，但证据校验后全部被过滤")

    if raw_todo_values > 0 and verified_todo_values == 0:
        if raw_todos_with_evidence == 0:
            reasons.append(f"模型提取了 {raw_todo_values} 条待办，但都缺少有效证据")
        else:
            reasons.append(f"模型提取了 {raw_todo_values} 条待办，但证据校验后全部被过滤")
    elif raw_todo_values == 0:
        reasons.append("模型没有提取出可展示的待办")

    if reasons:
        return f"本次输出未达到纪要生成标准：{'；'.join(reasons)}。"

    verified_core_values = sum(
        len(items)
        for items in verified_core.values()
        if isinstance(items, list)
    )
    if verified_core_values == 0 and verified_todo_values == 0:
        return "本次输出未达到纪要生成标准：校验后没有保留下可展示的会议纪要内容。"

    return (
        "本次输出未达到纪要生成标准：模型返回了部分内容，"
        f"但最终仅保留 {verified_core_values} 个信息对象和 {verified_todo_values} 条待办，仍不足以形成可展示纪要。"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate structured meeting minutes from a transcript.")
    parser.add_argument("input", help="Path to transcript .json or .txt/.md file.")
    parser.add_argument("-o", "--output-dir", default="out", help="Output directory.")
    args = parser.parse_args()
    paths = run(args.input, args.output_dir)
    print(json.dumps({key: str(path) for key, path in paths.items()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
