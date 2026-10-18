from __future__ import annotations

from datetime import datetime
from pathlib import Path
import subprocess
from uuid import uuid4

UPLOAD_ROOT = Path("data/uploads")
PREVIEW_NORMALIZE_SUFFIXES = {".aif", ".aiff"}


def save_media_upload(user_id: str, filename: str, data: bytes) -> Path:
    user_root = _user_root(user_id)
    user_root.mkdir(parents=True, exist_ok=True)
    suffix = "".join(Path(filename).suffixes[-1:]) or ".bin"
    safe_name = _safe_name(Path(filename).stem)
    stamped = datetime.now().strftime("%Y%m%d%H%M%S")
    media_id = f"media_{stamped}_{uuid4().hex[:8]}"
    path = user_root / f"{media_id}_{safe_name}{suffix}"
    path.write_bytes(data)
    return path


def resolve_media_path(user_id: str, media_path: str) -> Path | None:
    path = Path(media_path)
    try:
        resolved = path.resolve()
    except FileNotFoundError:
        resolved = path.absolute()
    user_root = _user_root(user_id).resolve()
    if user_root not in resolved.parents and resolved != user_root:
        return None
    return resolved if resolved.exists() else None


def get_browser_preview_path(media_path: Path) -> Path:
    """Return a browser-playable derivative for formats Chrome cannot preview reliably."""
    if media_path.suffix.lower() not in PREVIEW_NORMALIZE_SUFFIXES:
        return media_path

    preview_path = media_path.with_suffix(".preview.wav")
    if preview_path.exists() and preview_path.stat().st_mtime >= media_path.stat().st_mtime:
        return preview_path

    command = [
        "afconvert",
        "-f",
        "WAVE",
        "-d",
        "LEI16",
        str(media_path),
        str(preview_path),
    ]
    try:
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return media_path
    return preview_path if preview_path.exists() else media_path


def _user_root(user_id: str) -> Path:
    safe_user_id = "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in user_id)
    return UPLOAD_ROOT / safe_user_id


def _safe_name(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in value).strip("_")
    return cleaned or "audio"
