from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONFIG_PATH = Path(".minutes.config.json")
USER_CONFIG_ROOT = Path("data/configs")


@dataclass(frozen=True)
class ModelConfig:
    app_id: str
    provider: str
    model: str
    base_url: str
    api_key: str
    secret_key: str
    request_options: dict[str, Any]
    temperature: float
    max_tokens: int
    timeout_seconds: int

    def public_dict(self) -> dict[str, object]:
        return {
            "app_id": self.app_id,
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "request_options": self.request_options,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "timeout_seconds": self.timeout_seconds,
            "has_api_key": bool(self.api_key),
            "has_secret_key": bool(self.secret_key),
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "app_id": self.app_id,
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "api_key": self.api_key,
            "secret_key": self.secret_key,
            "request_options": self.request_options,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass(frozen=True)
class StoredConfig:
    minutes: ModelConfig
    asr: ModelConfig

    def public_dict(self) -> dict[str, object]:
        return {
            "minutes": self.minutes.public_dict(),
            "asr": self.asr.public_dict(),
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "minutes": self.minutes.to_dict(),
            "asr": self.asr.to_dict(),
        }


def load_config(path: Path = CONFIG_PATH) -> StoredConfig | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return _parse_stored_config(data)


def load_user_config(user_id: str) -> StoredConfig | None:
    path = _user_config_path(user_id)
    if not path.exists():
        return None
    return load_config(path)


def save_config(payload: dict[str, object], path: Path = CONFIG_PATH) -> StoredConfig:
    existing = load_config(path)
    minutes = _parse_model_config(
        payload.get("minutes") if isinstance(payload.get("minutes"), dict) else payload,
        existing.minutes if existing else None,
    )
    asr = _parse_model_config(
        payload.get("asr") if isinstance(payload.get("asr"), dict) else payload.get("asr_model") if isinstance(payload.get("asr_model"), dict) else payload,
        existing.asr if existing else None,
    )
    config = StoredConfig(minutes=minutes, asr=asr)
    path.write_text(json.dumps(config.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return config


def save_user_config(user_id: str, payload: dict[str, object]) -> StoredConfig:
    path = _user_config_path(user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    return save_config(payload, path)


def _parse_stored_config(data: dict[str, Any]) -> StoredConfig:
    if isinstance(data.get("minutes"), dict) or isinstance(data.get("asr"), dict):
        return StoredConfig(
            minutes=_parse_model_config(data.get("minutes") if isinstance(data.get("minutes"), dict) else {}, None),
            asr=_parse_model_config(data.get("asr") if isinstance(data.get("asr"), dict) else {}, None),
        )
    legacy = _parse_model_config(data, None)
    return StoredConfig(minutes=legacy, asr=legacy)


def _parse_model_config(data: dict[str, Any], fallback: ModelConfig | None) -> ModelConfig:
    provider = str(data.get("provider") or (fallback.provider if fallback else "openai_compatible")).strip()
    base_url = str(data.get("base_url") or (fallback.base_url if fallback else "")).strip()
    if provider == "openai_compatible" and base_url and not base_url.rstrip("/").endswith("/v1"):
        base_url = f"{base_url.rstrip('/')}/v1"
    return ModelConfig(
        app_id=str(data.get("app_id") or (fallback.app_id if fallback else "")).strip(),
        provider=provider,
        model=str(data.get("model") or (fallback.model if fallback else "")).strip(),
        base_url=base_url,
        api_key=str(data.get("api_key") or (fallback.api_key if fallback else "")).strip(),
        secret_key=str(data.get("secret_key") or (fallback.secret_key if fallback else "")).strip(),
        request_options=_parse_request_options(data.get("request_options"), fallback.request_options if fallback else None),
        temperature=float(data.get("temperature") or (fallback.temperature if fallback else 0.1)),
        max_tokens=int(data.get("max_tokens") or (fallback.max_tokens if fallback else 4000)),
        timeout_seconds=int(data.get("timeout_seconds") or (fallback.timeout_seconds if fallback else 120)),
    )


def _user_config_path(user_id: str) -> Path:
    safe_user_id = "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in user_id)
    return USER_CONFIG_ROOT / safe_user_id / "config.json"


def _parse_request_options(value: Any, fallback: dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return dict(fallback or {})
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return dict(fallback or {})
        if isinstance(parsed, dict):
            return parsed
    return dict(fallback or {})
