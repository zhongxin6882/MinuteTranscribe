from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

MeetingType = Literal[
    "project_sync",
    "decision_review",
    "issue_triage",
    "brainstorming",
    "interview_research",
    "universal_minutes",
    "general_meeting",
]

MEETING_TYPES: tuple[MeetingType, ...] = (
    "project_sync",
    "decision_review",
    "issue_triage",
    "brainstorming",
    "interview_research",
    "universal_minutes",
    "general_meeting",
)


@dataclass(frozen=True)
class Segment:
    seg_id: str
    speaker: str | None
    start: str | None
    text: str
    cleaned_text: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "seg_id": self.seg_id,
            "speaker": self.speaker,
            "start": self.start,
            "text": self.text,
            "cleaned_text": self.cleaned_text,
        }


@dataclass(frozen=True)
class Transcript:
    meeting_id: str
    segments: list[Segment]
    meta: dict[str, Any] | None = None

    def speaker_whitelist(self) -> set[str]:
        return {segment.speaker for segment in self.segments if segment.speaker}

    def segment_ids(self) -> set[str]:
        return {segment.seg_id for segment in self.segments}

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "meeting_id": self.meeting_id,
            "segments": [segment.to_dict() for segment in self.segments],
        }
        if self.meta:
            payload["meta"] = self.meta
        return payload


@dataclass(frozen=True)
class Classification:
    meeting_type: MeetingType
    confidence: float
    reason: str
    risk_tags: list[str]
    template: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "meeting_type": self.meeting_type,
            "confidence": self.confidence,
            "reason": self.reason,
            "risk_tags": self.risk_tags,
            "template": self.template,
        }
