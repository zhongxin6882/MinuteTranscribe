from __future__ import annotations

import json
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse
import base64
import mimetypes

from .auth_store import (
    AuthError,
    authenticate_user,
    clear_session_cookie_value,
    create_session,
    delete_session,
    get_user_for_session,
    parse_session_token,
    register_user,
    session_cookie_value,
)
from .config_store import load_user_config, save_user_config
from .documents_store import (
    create_draft_document,
    delete_document,
    get_document,
    list_documents,
    save_generated_document,
    update_document_content,
)
from .llm import LLMClient, LLMConfig, LLMError
from .media_store import get_browser_preview_path, resolve_media_path, save_media_upload
from .pipeline import run_transcript, transcript_from_payload
from .render import render_document_html, render_html, render_markdown
from .validate import ValidationError

WEB_ROOT = Path("web")


class AppHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            return self._serve_file(WEB_ROOT / "index.html", "text/html; charset=utf-8")
        if parsed.path.startswith("/assets/"):
            asset_path = (WEB_ROOT / parsed.path.lstrip("/")).resolve()
            web_root = WEB_ROOT.resolve()
            if web_root not in asset_path.parents and asset_path != web_root:
                return self._json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
            content_type = self._guess_content_type(asset_path)
            return self._serve_file(asset_path, content_type)
        if parsed.path == "/api/auth/session":
            user = self._current_user()
            if not user:
                return self._json({"user": None}, status=HTTPStatus.UNAUTHORIZED)
            return self._json({"user": user})
        user = self._require_user()
        if not user:
            return
        if parsed.path == "/api/media":
            query = parse_qs(parsed.query)
            media_path = str((query.get("path") or [""])[0] or "")
            resolved = resolve_media_path(user["id"], media_path)
            if not resolved:
                return self._json({"error": "Media not found"}, status=HTTPStatus.NOT_FOUND)
            preview_path = get_browser_preview_path(resolved)
            return self._serve_file(preview_path, self._guess_content_type(preview_path))
        if parsed.path == "/api/config":
            config = load_user_config(user["id"])
            return self._json({"config": config.public_dict() if config else None})
        if parsed.path == "/api/minutes":
            return self._json({"documents": list_documents(user["id"])})
        if parsed.path.startswith("/api/minutes/"):
            meeting_id = parsed.path.removeprefix("/api/minutes/")
            record = get_document(user["id"], meeting_id)
            if not record:
                return self._json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
            return self._json({"document": record})
        return self._json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/auth/register":
            try:
                payload = self._read_json()
                user = register_user(
                    str(payload.get("email") or ""),
                    str(payload.get("password") or ""),
                )
                token = create_session(user["id"])
            except (AuthError, json.JSONDecodeError) as exc:
                return self._json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return self._json(
                {"ok": True, "user": user},
                status=HTTPStatus.CREATED,
                extra_headers={"Set-Cookie": session_cookie_value(token)},
            )
        if parsed.path == "/api/auth/login":
            try:
                payload = self._read_json()
                user = authenticate_user(
                    str(payload.get("email") or ""),
                    str(payload.get("password") or ""),
                )
                token = create_session(user["id"])
            except (AuthError, json.JSONDecodeError) as exc:
                return self._json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return self._json(
                {"ok": True, "user": user},
                extra_headers={"Set-Cookie": session_cookie_value(token)},
            )
        if parsed.path == "/api/auth/logout":
            token = parse_session_token(self.headers.get("Cookie"))
            delete_session(token)
            return self._json({"ok": True}, extra_headers={"Set-Cookie": clear_session_cookie_value()})
        user = self._require_user()
        if not user:
            return
        if parsed.path == "/api/config":
            payload = self._read_json()
            config = save_user_config(user["id"], payload)
            return self._json({"ok": True, "config": config.public_dict()})
        if parsed.path == "/api/media":
            payload = self._read_json()
            media_name = str(payload.get("media_name") or "audio.wav")
            media_data = str(payload.get("media_data") or "")
            if not media_data:
                return self._json({"error": "Missing media_data"}, status=HTTPStatus.BAD_REQUEST)
            try:
                raw = media_data.split(",", 1)[-1]
                data = base64.b64decode(raw)
            except (ValueError, TypeError) as exc:
                return self._json({"error": f"Invalid media_data: {exc}"}, status=HTTPStatus.BAD_REQUEST)
            saved_path = save_media_upload(user["id"], media_name, data)
            return self._json(
                {
                    "ok": True,
                    "media": {
                        "media_path": str(saved_path.resolve()),
                        "media_name": media_name,
                        "media_mime": mimetypes.guess_type(media_name)[0] or "application/octet-stream",
                        "media_url": f"/api/media?path={quote(str(saved_path.resolve()))}",
                    },
                },
                status=HTTPStatus.CREATED,
            )
        if parsed.path == "/api/test-config":
            payload = self._read_json()
            kind = str(payload.get("kind") or "minutes").strip() or "minutes"
            try:
                client = LLMClient(LLMConfig.from_env(user["id"], kind=kind))
                if kind == "asr":
                    result = {
                        "ok": True,
                        "message": "ASR 配置已加载，需通过真实音频验证。",
                        "provider": client.config.provider,
                        "model": client.config.model,
                    }
                else:
                    result = client.test_connection()
            except LLMError as exc:
                return self._json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return self._json({"ok": True, "result": result})
        if parsed.path == "/api/minutes":
            payload = self._read_json()
            record = create_draft_document(
                user["id"],
                str(payload.get("title") or "").strip() or None,
                str(payload.get("status") or "草稿").strip() or "草稿",
            )
            return self._json({"ok": True, "document": record}, status=HTTPStatus.CREATED)
        if parsed.path == "/api/generate":
            payload = self._read_json()
            try:
                payload = {**payload, "user_id": user["id"]}
                transcript = transcript_from_payload(payload)
                minutes = run_transcript(transcript, user["id"])
                markdown = render_markdown(minutes, transcript)
                document_html = render_document_html(markdown)
                html_doc = render_html(markdown, transcript, minutes)
                record = save_generated_document(
                    user["id"],
                    transcript,
                    minutes,
                    markdown,
                    document_html,
                    html_doc,
                    input_kind=str(payload.get("kind") or "text"),
                    source_input=json.dumps(payload.get("transcript"), ensure_ascii=False, indent=2)
                    if payload.get("kind") == "json"
                    else str(payload.get("media_name") or "") if payload.get("kind") == "media" else str(payload.get("text") or ""),
                    media_path=str(payload.get("media_path") or ""),
                    media_name=str(payload.get("media_name") or ""),
                    media_mime=str(payload.get("media_mime") or ""),
                )
            except (ValidationError, LLMError, KeyError, ValueError) as exc:
                meeting_id = str(payload.get("meeting_id") or "").strip()
                if meeting_id:
                    update_document_content(
                        user["id"],
                        meeting_id,
                        document_html="",
                        markdown="",
                        title=str(payload.get("title") or "") or None,
                        status="纪要生成失败",
                        source_input=json.dumps(payload.get("transcript"), ensure_ascii=False, indent=2)
                        if payload.get("kind") == "json"
                        else str(payload.get("media_name") or "") if payload.get("kind") == "media" else str(payload.get("text") or ""),
                        input_kind=str(payload.get("kind") or "text"),
                        transcript=transcript.to_dict() if "transcript" in locals() and transcript else payload.get("transcript") if isinstance(payload.get("transcript"), dict) else None,
                        media_path=str(payload.get("media_path") or "") if "media_path" in payload else None,
                        media_name=str(payload.get("media_name") or "") if "media_name" in payload else None,
                        media_mime=str(payload.get("media_mime") or "") if "media_mime" in payload else None,
                        failure_reason=str(exc),
                    )
                return self._json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return self._json(
                {
                    "ok": True,
                    "classification": minutes.get("classification"),
                    "minutes": minutes,
                    "markdown": markdown,
                    "document_html": document_html,
                    "html": html_doc,
                    "transcript": transcript.to_dict(),
                    "document": record,
                }
            )
        if parsed.path.startswith("/api/minutes/"):
            meeting_id = parsed.path.removeprefix("/api/minutes/")
            payload = self._read_json()
            record = update_document_content(
                user["id"],
                meeting_id,
                document_html=str(payload.get("document_html") or ""),
                markdown=str(payload.get("markdown") or "") or None,
                title=str(payload.get("title") or "") if "title" in payload else None,
                status=str(payload.get("status") or "") or None,
                source_input=str(payload.get("source_input") or "") if "source_input" in payload else None,
                input_kind=str(payload.get("input_kind") or "") if "input_kind" in payload else None,
                transcript=payload.get("transcript") if isinstance(payload.get("transcript"), dict) else None,
                media_path=str(payload.get("media_path") or "") if "media_path" in payload else None,
                media_name=str(payload.get("media_name") or "") if "media_name" in payload else None,
                media_mime=str(payload.get("media_mime") or "") if "media_mime" in payload else None,
                failure_reason=str(payload.get("failure_reason") or "") if "failure_reason" in payload else None,
            )
            if not record:
                return self._json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
            return self._json({"ok": True, "document": record})
        return self._json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        user = self._require_user()
        if not user:
            return
        if parsed.path.startswith("/api/minutes/"):
            meeting_id = parsed.path.removeprefix("/api/minutes/")
            if not delete_document(user["id"], meeting_id):
                return self._json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
            return self._json({"ok": True})
        return self._json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args) -> None:
        return None

    def _serve_file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            return self._json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
        file_size = path.stat().st_size
        range_header = self.headers.get("Range")
        start = 0
        end = max(0, file_size - 1)
        status = HTTPStatus.OK

        if range_header and range_header.startswith("bytes=") and file_size > 0:
            range_spec = range_header.removeprefix("bytes=").strip()
            start_text, _, end_text = range_spec.partition("-")
            try:
                if start_text:
                    start = max(0, int(start_text))
                    end = int(end_text) if end_text else end
                else:
                    suffix_length = int(end_text)
                    start = max(0, file_size - suffix_length)
                    end = file_size - 1
            except ValueError:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{file_size}")
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                return

            end = min(end, file_size - 1)
            if start > end or start >= file_size:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{file_size}")
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                return
            status = HTTPStatus.PARTIAL_CONTENT

        content_length = max(0, end - start + 1)
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(content_length))
        if status == HTTPStatus.PARTIAL_CONTENT:
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        self.end_headers()
        with path.open("rb") as file_obj:
            file_obj.seek(start)
            remaining = content_length
            while remaining > 0:
                chunk = file_obj.read(min(64 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def _guess_content_type(self, path: Path) -> str:
        suffix = path.suffix.lower()
        media_types = {
            ".m4a": "audio/mp4",
            ".mp4": "video/mp4",
            ".wav": "audio/wav",
            ".mp3": "audio/mpeg",
            ".ogg": "audio/ogg",
            ".webm": "audio/webm",
            ".aiff": "audio/aiff",
            ".aif": "audio/aiff",
        }
        if suffix in media_types:
            return media_types[suffix]
        guessed = mimetypes.guess_type(path.name)[0]
        if guessed:
            return guessed
        if suffix == ".json":
            return "application/json; charset=utf-8"
        if suffix == ".svg":
            return "image/svg+xml"
        if suffix == ".css":
            return "text/css; charset=utf-8"
        if suffix == ".js":
            return "application/javascript; charset=utf-8"
        if suffix == ".png":
            return "image/png"
        if suffix == ".jpg" or suffix == ".jpeg":
            return "image/jpeg"
        return "application/octet-stream"

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        return json.loads(raw or "{}")

    def _current_user(self) -> dict | None:
        token = parse_session_token(self.headers.get("Cookie"))
        return get_user_for_session(token)

    def _require_user(self) -> dict | None:
        user = self._current_user()
        if not user:
            self._json({"error": "请先登录后再使用。"}, status=HTTPStatus.UNAUTHORIZED)
            return None
        return user

    def _json(
        self,
        payload: dict,
        status: HTTPStatus = HTTPStatus.OK,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        if extra_headers:
            for key, value in extra_headers.items():
                self.send_header(key, value)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    server = ThreadingHTTPServer(("127.0.0.1", port), AppHandler)
    print(f"Listening on http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
