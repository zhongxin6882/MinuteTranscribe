from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.documents_store import get_document


class DocumentTemplateMigrationTests(unittest.TestCase):
    def test_get_document_migrates_legacy_template_to_latest_render(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store_root = Path(tmpdir) / "minutes"
            user_id = "user_001"
            meeting_id = "draft_legacy"
            user_root = store_root / user_id
            user_root.mkdir(parents=True, exist_ok=True)
            record_path = user_root / f"{meeting_id}.json"
            legacy_record = {
                "id": meeting_id,
                "owner_id": user_id,
                "title": "未命名",
                "status": "纪要已生成",
                "meeting_type": "general_meeting",
                "created_at": "2026-08-18T15:42:56",
                "updated_at": "2026-08-18T15:42:56",
                "markdown": "# 会议纪要\n\n## 会议概况\n- 会议主题：旧模版\n\n## 议题\n1. 进展与现状\n- 当前情况：旧内容\n",
                "document_html": "<h1 class=\"doc-title\">会议纪要</h1><h2 class=\"doc-section\">会议概况</h2>",
                "html": "<html><body>会议概况</body></html>",
                "minutes": {
                    "meeting_type": "general_meeting",
                    "summary": "本次会议围绕新版纪要输出格式展开。",
                    "core": {
                        "topics": [{"title": "新版模版", "detail": "确认纪要展示结构。", "evidence": ["s001"]}],
                        "conclusions": [{"text": "纪要需要切换到最新模版。", "status": "confirmed", "evidence": ["s002"]}],
                        "decisions": [],
                        "risks": [],
                        "open_questions": [],
                    },
                    "todos": [{"task": "替换线上展示模版", "owner": None, "due": "", "extra": "", "evidence": ["s003"]}],
                },
                "transcript": {
                    "meeting_id": meeting_id,
                    "segments": [
                        {"seg_id": "s001", "speaker": None, "start": "00:00", "text": "先确认纪要结构。", "cleaned_text": "先确认纪要结构。"},
                        {"seg_id": "s002", "speaker": None, "start": "00:20", "text": "统一切到最新模版。", "cleaned_text": "统一切到最新模版。"},
                        {"seg_id": "s003", "speaker": None, "start": "00:35", "text": "替换线上展示模版。", "cleaned_text": "替换线上展示模版。"},
                    ],
                },
                "input_kind": "media",
                "source_input": "meeting_voice_template_20min.wav",
                "media_path": "",
                "media_name": "meeting_voice_template_20min.wav",
                "media_mime": "audio/wav",
                "failure_reason": "",
            }
            record_path.write_text(json.dumps(legacy_record, ensure_ascii=False, indent=2), encoding="utf-8")

            with patch("src.documents_store.STORE_ROOT", store_root):
                record = get_document(user_id, meeting_id)

            self.assertIsNotNone(record)
            assert record is not None
            self.assertIn("# 智能纪要：普通会议", record["markdown"])
            self.assertIn("## 核心结论", record["markdown"])
            self.assertNotIn("## 会议概况", record["markdown"])
            self.assertNotIn("进展与现状", record["document_html"])

            persisted = json.loads(record_path.read_text(encoding="utf-8"))
            self.assertIn("# 智能纪要：普通会议", persisted["markdown"])
            self.assertIn("## 核心结论", persisted["markdown"])
            self.assertNotIn("## 会议概况", persisted["markdown"])


if __name__ == "__main__":
    unittest.main()
