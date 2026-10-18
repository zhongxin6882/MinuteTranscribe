from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .cleanup import clean_text
from .schema import Segment, Transcript

MAX_SEGMENTS = 3000
MAX_CHARS = 50_000


class ValidationError(ValueError):
    pass


def load_transcript(path: str | Path) -> Transcript:
    source = Path(path)
    raw = source.read_text(encoding="utf-8")
    if source.suffix.lower() == ".json":
        return transcript_from_json(json.loads(raw), fallback_id=source.stem)
    return transcript_from_text(raw, meeting_id=source.stem)


def transcript_from_json(data: dict[str, Any], fallback_id: str = "meeting") -> Transcript:
    meeting_id = str(data.get("meeting_id") or fallback_id)
    raw_segments = data.get("segments")
    if not isinstance(raw_segments, list):
        raise ValidationError("JSON input must contain a segments array.")
    segments: list[Segment] = []
    for index, item in enumerate(raw_segments, start=1):
        if not isinstance(item, dict):
            raise ValidationError(f"segments[{index}] must be an object.")
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        seg_id = str(item.get("seg_id") or f"s{index:03d}")
        speaker_raw = item.get("speaker")
        speaker = str(speaker_raw).strip() if speaker_raw not in (None, "") else None
        start_raw = item.get("start")
        start = str(start_raw).strip() if start_raw not in (None, "") else None
        segments.append(
            Segment(
                seg_id=seg_id,
                speaker=speaker,
                start=start,
                text=text,
                cleaned_text=clean_text(text),
            )
        )
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else None
    return validate_transcript(Transcript(meeting_id=meeting_id, segments=segments, meta=meta))


def transcript_from_text(raw: str, meeting_id: str = "meeting") -> Transcript:
    segments: list[Segment] = []
    line_pattern = re.compile(
        r"^(?:(?P<start>\d{1,2}:\d{2}(?::\d{2})?)\s+)?(?:(?P<speaker>[^:：]{1,20})[:：]\s*)?(?P<text>.+)$"
    )
    for index, line in enumerate(raw.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        match = line_pattern.match(line)
        if not match:
            continue
        text = match.group("text").strip()
        if not text:
            continue
        speaker = match.group("speaker")
        start = match.group("start")
        segments.append(
            Segment(
                seg_id=f"s{len(segments) + 1:03d}",
                speaker=speaker.strip() if speaker else None,
                start=start.strip() if start else None,
                text=text,
                cleaned_text=clean_text(text),
            )
        )
    return validate_transcript(Transcript(meeting_id=meeting_id, segments=segments))


def validate_transcript(transcript: Transcript) -> Transcript:
    if not transcript.segments:
        raise ValidationError("Transcript must contain at least one non-empty segment.")
    if len(transcript.segments) > MAX_SEGMENTS:
        raise ValidationError(f"Transcript has {len(transcript.segments)} segments; limit is {MAX_SEGMENTS}.")
    total_chars = sum(len(segment.text) for segment in transcript.segments)
    if total_chars > MAX_CHARS:
        raise ValidationError(f"Transcript has {total_chars} characters; limit is {MAX_CHARS}.")
    seen: set[str] = set()
    for segment in transcript.segments:
        if segment.seg_id in seen:
            raise ValidationError(f"Duplicate seg_id: {segment.seg_id}.")
        seen.add(segment.seg_id)
    return transcript
