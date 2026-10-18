from __future__ import annotations

import base64
import json
import mimetypes
import os
from pathlib import Path
import re
import uuid
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .config_store import load_config, load_user_config


class LLMError(RuntimeError):
    pass


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    model: str
    api_key: str
    base_url: str | None = None
    app_id: str = ""
    secret_key: str = ""
    request_options: dict[str, Any] | None = None
    temperature: float = 0.1
    max_tokens: int = 4000
    timeout_seconds: int = 120

    @classmethod
    def from_env(cls, user_id: str | None = None, kind: str = "minutes") -> "LLMConfig":
        stored = load_user_config(user_id) if user_id else load_config()
        if stored:
            model_config = stored.asr if kind == "asr" else stored.minutes
            if model_config.model and model_config.api_key:
                provider = model_config.provider or "openai_compatible"
                base_url = model_config.base_url or None
                return cls(
                    app_id=model_config.app_id,
                    provider=provider,
                    model=model_config.model,
                    api_key=model_config.api_key,
                    base_url=base_url,
                    secret_key=model_config.secret_key,
                    request_options=model_config.request_options,
                    temperature=model_config.temperature,
                    max_tokens=model_config.max_tokens,
                    timeout_seconds=model_config.timeout_seconds,
                )
        prefix = "MINUTES_ASR" if kind == "asr" else "MINUTES_LLM"
        provider = os.environ.get(f"{prefix}_PROVIDER", "openai_compatible").strip()
        model = os.environ.get(f"{prefix}_MODEL", "").strip()
        api_key_env = os.environ.get(f"{prefix}_API_KEY_ENV", "").strip()
        api_key = os.environ.get(api_key_env) if api_key_env else os.environ.get(f"{prefix}_API_KEY")
        base_url = os.environ.get(f"{prefix}_BASE_URL")
        if not model:
            raise LLMError(f"Missing {prefix}_MODEL.")
        if not api_key:
            raise LLMError(f"Missing {prefix}_API_KEY or {prefix}_API_KEY_ENV target value.")
        return cls(
            app_id=os.environ.get(f"{prefix}_APP_ID", "").strip(),
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
            secret_key=os.environ.get(f"{prefix}_SECRET_KEY", "").strip(),
            request_options={},
            temperature=float(os.environ.get(f"{prefix}_TEMPERATURE", "0.1")),
            max_tokens=int(os.environ.get(f"{prefix}_MAX_TOKENS", "4000")),
            timeout_seconds=int(os.environ.get(f"{prefix}_TIMEOUT", "120")),
        )


class LLMClient:
    def __init__(self, config: LLMConfig):
        self.config = config

    @classmethod
    def _for_media_transcription(cls, user_id: str | None = None) -> "LLMClient":
        return cls(LLMConfig.from_env(user_id, kind="asr"))

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        text = self._complete_text(system_prompt, user_prompt)
        try:
            return _parse_json_object(text)
        except LLMError as first_error:
            repaired = self._repair_json_with_model(text)
            try:
                return _parse_json_object(repaired)
            except LLMError as repair_error:
                retry_prompt = (
                    user_prompt
                    + "\n\n上一次输出不是合法 JSON。请重新生成，且只能返回一个 JSON 对象，不要解释，不要 Markdown，不要代码块。"
                )
                retried = self._complete_text(system_prompt, retry_prompt)
                try:
                    return _parse_json_object(retried)
                except LLMError as retry_error:
                    preview = retried[:800].replace("\n", "\\n")
                    raise LLMError(
                        "模型输出不稳定：首次生成、修复 JSON、重新生成三次都未得到合法 JSON。"
                        f" 首次错误：{first_error}；修复错误：{repair_error}；重试错误：{retry_error}。"
                        f" 最后一次返回片段：{preview}"
                    ) from retry_error

    def test_connection(self) -> dict[str, Any]:
        return self.complete_json(
            "你是连接测试服务。只输出合法 JSON 对象。",
            '请只返回 {"ok": true, "message": "connected"}，不要输出其他内容。',
        )

    def transcribe_audio(self, audio_path: str | os.PathLike[str], response_format: str = "verbose_json") -> dict[str, Any]:
        if self.config.provider == "anthropic":
            raise LLMError("Anthropic provider does not support audio transcription in this project yet.")
        if self.config.provider == "volcengine_asr":
            return self._transcribe_volcengine(audio_path)
        base_url = normalize_openai_compatible_base_url(self.config.base_url)
        url = f"{base_url}/audio/transcriptions"
        path = os.fspath(audio_path)
        payload = {
            "model": self.config.model,
            "response_format": response_format,
        }
        data = self._post_multipart(
            url,
            payload,
            "file",
            path,
            {
                "Authorization": f"Bearer {self.config.api_key}",
            },
        )
        if not isinstance(data, dict):
            raise LLMError(f"Unexpected transcription response: {data}")
        return data

    def _transcribe_volcengine(self, audio_path: str | os.PathLike[str]) -> dict[str, Any]:
        path = os.fspath(audio_path)
        with open(path, "rb") as handle:
            audio_bytes = handle.read()
        request_id = str(uuid.uuid4())
        payload = {
            "user": {
                "uid": f"minutes-{request_id[:12]}",
            },
            "audio": {
                "format": _guess_audio_format(path),
                "data": base64.b64encode(audio_bytes).decode("utf-8"),
            },
            "request": {
                "model_name": self.config.model or "bigmodel",
            },
        }
        if self.config.request_options:
            payload["request"].update(self.config.request_options)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        url = (self.config.base_url or "https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash").rstrip("/")
        headers = {
            "Content-Type": "application/json",
            "X-Api-Resource-Id": "volc.bigasr.auc_turbo",
            "X-Api-Request-Id": request_id,
            "X-Api-Sequence": "-1",
        }
        if self.config.app_id:
            headers["X-Api-App-Key"] = self.config.app_id
            headers["X-Api-Access-Key"] = self.config.api_key
        else:
            headers["X-Api-Key"] = self.config.api_key
        request = urllib.request.Request(
            url=url,
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise LLMError(f"Volcengine ASR HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise LLMError(f"Volcengine ASR request failed: {exc}") from exc
        return _normalize_volcengine_asr_response(raw, payload.get("request") if isinstance(payload.get("request"), dict) else {})

    def _complete_text(self, system_prompt: str, user_prompt: str) -> str:
        if self.config.provider == "anthropic":
            return self._complete_anthropic(system_prompt, user_prompt)
        return self._complete_openai_compatible(system_prompt, user_prompt)

    def _complete_openai_compatible(self, system_prompt: str, user_prompt: str) -> str:
        base_url = normalize_openai_compatible_base_url(self.config.base_url)
        url = f"{base_url}/chat/completions"
        payload = {
            "model": self.config.model,
            "temperature": max(0.0, min(self.config.temperature, 0.2)),
            "max_tokens": self.config.max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        data = self._post_json(url, payload, {"Authorization": f"Bearer {self.config.api_key}"})
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"Unexpected OpenAI-compatible response: {data}") from exc

    def _complete_anthropic(self, system_prompt: str, user_prompt: str) -> str:
        base_url = (self.config.base_url or "https://api.anthropic.com/v1").rstrip("/")
        url = f"{base_url}/messages"
        payload = {
            "model": self.config.model,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        data = self._post_json(
            url,
            payload,
            {
                "x-api-key": self.config.api_key,
                "anthropic-version": "2023-06-01",
            },
        )
        try:
            return "".join(part.get("text", "") for part in data["content"] if part.get("type") == "text")
        except (KeyError, TypeError) as exc:
            raise LLMError(f"Unexpected Anthropic response: {data}") from exc

    def _repair_json_with_model(self, broken_text: str) -> str:
        repair_system = "你是 JSON 修复器。你的任务是把输入内容修复成唯一一个合法 JSON 对象。不要补充解释。"
        repair_user = (
            "下面是一段本应为 JSON 的模型输出，但格式可能损坏。"
            "请尽量保留原意，修复为唯一一个合法 JSON 对象，只输出 JSON 本身。\n\n"
            f"{broken_text}"
        )
        return self._complete_text(repair_system, repair_user)

    def _post_json(self, url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        request = urllib.request.Request(
            url=url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                **headers,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise LLMError(f"LLM HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise LLMError(f"LLM request failed: {exc}") from exc

    def _post_multipart(
        self,
        url: str,
        fields: dict[str, Any],
        file_field_name: str,
        file_path: str,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        boundary = f"----CodexBoundary{uuid.uuid4().hex}"
        body = bytearray()

        for key, value in fields.items():
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8"))
            body.extend(str(value).encode("utf-8"))
            body.extend(b"\r\n")

        filename = os.path.basename(file_path)
        mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        with open(file_path, "rb") as handle:
            file_bytes = handle.read()
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(
            f'Content-Disposition: form-data; name="{file_field_name}"; filename="{filename}"\r\n'.encode("utf-8")
        )
        body.extend(f"Content-Type: {mime_type}\r\n\r\n".encode("utf-8"))
        body.extend(file_bytes)
        body.extend(b"\r\n")
        body.extend(f"--{boundary}--\r\n".encode("utf-8"))

        request = urllib.request.Request(
            url=url,
            data=bytes(body),
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                **headers,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise LLMError(f"LLM HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise LLMError(f"LLM transcription request failed: {exc}") from exc


def _parse_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        candidate = _extract_json_object(text)
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as exc:
            repaired = _repair_common_json_issues(candidate)
            try:
                parsed = json.loads(repaired)
            except json.JSONDecodeError as repaired_exc:
                preview = text[:500].replace("\n", "\\n")
                raise LLMError(
                    f"模型返回不是合法 JSON：{repaired_exc.msg} at line {repaired_exc.lineno} column {repaired_exc.colno}. "
                    f"返回片段：{preview}"
                ) from exc
    if not isinstance(parsed, dict):
        raise LLMError("Model response JSON must be an object.")
    return parsed


def normalize_openai_compatible_base_url(base_url: str | None) -> str:
    normalized = (base_url or "https://api.openai.com/v1").rstrip("/")
    if normalized.endswith("/v1"):
        return normalized
    return f"{normalized}/v1"


def _guess_audio_format(path: str) -> str:
    suffix = Path(path).suffix.lower().lstrip(".")
    if suffix == "aif":
        return "aiff"
    if suffix == "oga":
        return "ogg"
    return suffix or "wav"


def _normalize_volcengine_asr_response(data: dict[str, Any], request_options: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise LLMError(f"Unexpected Volcengine ASR response: {data}")
    result = data.get("result") if isinstance(data.get("result"), dict) else {}
    utterances = result.get("utterances") if isinstance(result.get("utterances"), list) else []
    segments: list[dict[str, Any]] = []
    speaker_labels: dict[str, str] = {}
    for item in utterances:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        speaker = _extract_volcengine_speaker(item, speaker_labels)
        segments.append(
            {
                "start": (float(item.get("start_time") or 0) / 1000.0) if item.get("start_time") is not None else None,
                "speaker": speaker,
                "text": text,
            }
        )
    full_text = str(result.get("text") or "").strip()
    if not full_text and segments:
        full_text = "\n".join(segment["text"] for segment in segments)
    if not full_text and not segments:
        raise LLMError(f"Unexpected Volcengine ASR response: {data}")
    speaker_debug = _build_volcengine_speaker_debug(utterances)
    return {
        "text": full_text,
        "segments": segments,
        "meta": {
            "provider": "volcengine_asr",
            "request_options": request_options or {},
            "speaker_debug": speaker_debug,
            "raw_result_keys": sorted(result.keys()),
        },
    }


def _extract_volcengine_speaker(item: dict[str, Any], speaker_labels: dict[str, str]) -> str | None:
    for key in ("speaker", "speaker_name", "speaker_label", "role", "participant_name"):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    raw_id = None
    for key in ("speaker_id", "spk_id", "speaker_idx", "speaker_index", "role_id", "participant_id"):
        candidate = item.get(key)
        if candidate not in (None, ""):
            raw_id = str(candidate).strip()
            if raw_id:
                break
    if not raw_id:
        return None
    if raw_id not in speaker_labels:
        speaker_labels[raw_id] = f"说话人{len(speaker_labels) + 1}"
    return speaker_labels[raw_id]


def _build_volcengine_speaker_debug(utterances: list[Any]) -> dict[str, Any]:
    debug = {
        "utterance_count": 0,
        "utterance_keys": [],
        "speaker_label_fields_present": False,
        "speaker_id_fields_present": False,
        "speaker_values_sample": [],
        "speaker_id_values_sample": [],
    }
    if not utterances:
        return debug
    first_item = utterances[0] if isinstance(utterances[0], dict) else {}
    debug["utterance_count"] = len(utterances)
    debug["utterance_keys"] = sorted(first_item.keys()) if isinstance(first_item, dict) else []
    label_samples: list[str] = []
    id_samples: list[str] = []
    for item in utterances:
        if not isinstance(item, dict):
            continue
        for key in ("speaker", "speaker_name", "speaker_label", "role", "participant_name"):
            value = str(item.get(key) or "").strip()
            if value:
                debug["speaker_label_fields_present"] = True
                if value not in label_samples:
                    label_samples.append(value)
        for key in ("speaker_id", "spk_id", "speaker_idx", "speaker_index", "role_id", "participant_id"):
            candidate = item.get(key)
            if candidate in (None, ""):
                continue
            debug["speaker_id_fields_present"] = True
            value = str(candidate).strip()
            if value and value not in id_samples:
                id_samples.append(value)
        if len(label_samples) >= 5 and len(id_samples) >= 5:
            break
    debug["speaker_values_sample"] = label_samples[:5]
    debug["speaker_id_values_sample"] = id_samples[:5]
    return debug


def _extract_json_object(text: str) -> str:
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        return fenced.group(1).strip()
    start = text.find("{")
    if start < 0:
        raise LLMError("Model response did not contain a JSON object.")
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    end = text.rfind("}")
    if end < start:
        raise LLMError("Model response did not contain a complete JSON object.")
    return text[start : end + 1]


def _repair_common_json_issues(text: str) -> str:
    repaired = text.strip()
    repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
    repaired = repaired.replace("\u201c", '"').replace("\u201d", '"')
    repaired = repaired.replace("\u2018", "'").replace("\u2019", "'")
    return repaired
