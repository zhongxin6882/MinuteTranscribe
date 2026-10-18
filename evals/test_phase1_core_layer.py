from __future__ import annotations

import unittest

from src.generate import normalize_generation_result
from src.schema import Segment, Transcript
from src.verify import verify_minutes


class Phase1CoreLayerTests(unittest.TestCase):
    def test_normalize_generation_result_preserves_core_objects(self) -> None:
        result = normalize_generation_result(
            {
                "summary": "项目进展与阻塞同步",
                "core": {
                    "topics": [
                        {"title": "当前阻塞", "detail": "测试环境 FAQ 数据缺失", "evidence": ["s004"]},
                    ],
                    "conclusions": [
                        {"text": "本周先完成试用演示", "status": "confirmed", "evidence": ["s008"]},
                    ],
                    "decisions": [
                        {"question": "本周目标", "decision": "本周先完成试用演示", "evidence": ["s008"]},
                    ],
                    "risks": [
                        {"text": "测试环境 FAQ 数据缺失", "level": "", "evidence": ["s004"]},
                    ],
                    "open_questions": [
                        {"text": "明天中午前确认数据是否到位", "evidence": ["s005"]},
                    ],
                },
                "todos": [
                    {
                        "task": "完成权限接口联调",
                        "owner": "唐雪",
                        "due": "7 月 24 日下午六点前",
                        "extra": "",
                        "evidence": ["s006"],
                    }
                ],
            },
        )

        self.assertEqual(result["summary"], "项目进展与阻塞同步")
        self.assertEqual(result["fields"], {})
        self.assertTrue(result["core"]["topics"])
        self.assertTrue(result["core"]["conclusions"])
        self.assertTrue(result["core"]["decisions"])
        self.assertTrue(result["core"]["risks"])
        self.assertTrue(result["core"]["open_questions"])
        self.assertEqual(result["core"]["decisions"][0]["decision"], "本周先完成试用演示")

    def test_verify_minutes_filters_invalid_core_evidence(self) -> None:
        transcript = Transcript(
            meeting_id="m001",
            segments=[
                Segment(seg_id="s001", speaker="林岚", start="00:00:10", text="今天同步项目进度。", cleaned_text="今天同步项目进度。"),
                Segment(seg_id="s002", speaker="唐雪", start="00:01:00", text="我负责明天下午前完成联调。", cleaned_text="我负责明天下午前完成联调。"),
            ],
        )

        verified = verify_minutes(
            {
                "fields": {},
                "todos": [
                    {
                        "task": "完成联调",
                        "owner": "唐雪",
                        "due": "明天下午前",
                        "extra": "",
                        "evidence": ["s002"],
                    }
                ],
                "core": {
                    "topics": [
                        {"title": "当前阶段", "detail": "联调阶段", "evidence": ["s001"]},
                        {"title": "无效项", "detail": "没有有效证据", "evidence": ["missing"]},
                    ],
                    "conclusions": [
                        {"text": "本周继续推进", "status": "confirmed", "evidence": ["s001"]}
                    ],
                    "decisions": [
                        {"question": "是否继续推进", "decision": "继续推进", "evidence": ["missing"]}
                    ],
                    "risks": [
                        {"text": "测试数据尚未到位", "level": "", "evidence": ["s001"]}
                    ],
                    "open_questions": [
                        {"text": "明天下午前能否完成", "evidence": ["s002"]}
                    ],
                },
            },
            transcript,
        )

        self.assertEqual(len(verified["core"]["topics"]), 1)
        self.assertEqual(len(verified["core"]["decisions"]), 0)
        self.assertEqual(verified["meta"]["core_counts"]["conclusions"], 1)
        self.assertEqual(verified["meta"]["segments_cited"], 2)


if __name__ == "__main__":
    unittest.main()
