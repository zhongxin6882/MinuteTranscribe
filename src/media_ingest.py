from __future__ import annotations

import mimetypes
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .llm import LLMClient, LLMError
from .schema import Segment, Transcript
from .validate import ValidationError, validate_transcript
from .cleanup import clean_text

AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".webm", ".aif", ".aiff"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm"}
VOLCENGINE_DIRECT_AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".aif", ".aiff"}
PCM_NORMALIZE_AUDIO_SUFFIXES = {".aif", ".aiff"}


def transcript_from_media_path(path: str | Path, user_id: str | None = None, meeting_id: str | None = None) -> Transcript:
    source = Path(path)
    if not source.exists():
        raise ValidationError(f"Media file not found: {source}")
    temp_dir = None
    suffix = source.suffix.lower()
    if suffix in AUDIO_SUFFIXES:
        audio_path = source
    elif suffix in VIDEO_SUFFIXES:
        temp_dir = tempfile.TemporaryDirectory(prefix="minutes-media-")
        audio_path = _extract_audio_from_video(source, Path(temp_dir.name))
    else:
        raise ValidationError(f"Unsupported media file type: {suffix}")
    try:
        client = LLMClient._for_media_transcription(user_id)
        if _should_normalize_audio_before_transcription(audio_path):
            if temp_dir is None:
                temp_dir = tempfile.TemporaryDirectory(prefix="minutes-media-")
            audio_path = _normalize_audio_to_wav(audio_path, Path(temp_dir.name))
        if client.config.provider == "volcengine_asr":
            if temp_dir is None:
                temp_dir = tempfile.TemporaryDirectory(prefix="minutes-media-")
            audio_path = _ensure_volcengine_supported_audio(audio_path, Path(temp_dir.name))
        result = client.transcribe_audio(audio_path)
        transcript = _transcription_to_transcript(result, meeting_id or source.stem)
        return validate_transcript(transcript)
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()


def transcript_from_media_bytes(data: bytes, filename: str, user_id: str | None = None, meeting_id: str | None = None) -> Transcript:
    suffix = Path(filename).suffix or ".wav"
    with tempfile.NamedTemporaryFile(prefix="minutes-media-", suffix=suffix, delete=False) as handle:
        temp_path = Path(handle.name)
        handle.write(data)
    try:
        return transcript_from_media_path(temp_path, user_id=user_id, meeting_id=meeting_id)
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


def _extract_audio_from_video(video_path: Path, temp_dir: Path) -> Path:
    output = temp_dir / f"{video_path.stem}.wav"
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(output),
    ]
    try:
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError as exc:
        raise LLMError("ffmpeg is required for video transcription but was not found.") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode("utf-8", errors="replace").strip()
        raise LLMError(f"Failed to extract audio from video: {detail}") from exc
    return output


def _ensure_volcengine_supported_audio(audio_path: Path, temp_dir: Path) -> Path:
    if audio_path.suffix.lower() in VOLCENGINE_DIRECT_AUDIO_SUFFIXES:
        return audio_path
    output = temp_dir / f"{audio_path.stem}.mp3"
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(audio_path),
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "libmp3lame",
        "-b:a",
        "64k",
        str(output),
    ]
    try:
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError as exc:
        raise LLMError("Volcengine ASR requires ffmpeg to convert this audio format to MP3.") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode("utf-8", errors="replace").strip()
        raise LLMError(f"Failed to convert audio for Volcengine ASR: {detail}") from exc
    return output


def _should_normalize_audio_before_transcription(audio_path: Path) -> bool:
    return audio_path.suffix.lower() in PCM_NORMALIZE_AUDIO_SUFFIXES


def _normalize_audio_to_wav(audio_path: Path, temp_dir: Path) -> Path:
    output = temp_dir / f"{audio_path.stem}.wav"
    command = [
        "afconvert",
        "-f",
        "WAVE",
        "-d",
        "LEI16",
        str(audio_path),
        str(output),
    ]
    try:
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError as exc:
        raise LLMError("aiff 音频需要先转换为 wav，但系统未找到 afconvert。") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode("utf-8", errors="replace").strip()
        raise LLMError(f"Failed to normalize audio before transcription: {detail}") from exc
    return output


def _transcription_to_transcript(result: dict[str, Any], meeting_id: str) -> Transcript:
    segments_data = result.get("segments") if isinstance(result.get("segments"), list) else []
    meta = result.get("meta") if isinstance(result.get("meta"), dict) else None
    segments: list[Segment] = []
    for index, item in enumerate(segments_data, start=1):
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        start = item.get("start")
        speaker_raw = item.get("speaker")
        speaker = str(speaker_raw).strip() if speaker_raw not in (None, "") else None
        segments.append(
            Segment(
                seg_id=f"s{index:03d}",
                speaker=speaker,
                start=_format_seconds(start) if start is not None else None,
                text=text,
                cleaned_text=clean_text(text),
            )
        )
    if not segments:
        text = str(result.get("text") or "").strip()
        if text:
            segments = [
                Segment(
                    seg_id="s001",
                    speaker=None,
                    start=None,
                    text=text,
                    cleaned_text=clean_text(text),
                )
            ]
    return Transcript(meeting_id=meeting_id, segments=segments, meta=meta)


def _format_seconds(value: Any) -> str | None:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    whole = int(seconds)
    hours, remainder = divmod(whole, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"
