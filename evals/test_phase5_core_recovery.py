from __future__ import annotations

import unittest

from src.generate import _merge_generation_results, _needs_core_recovery
from src.pipeline import has_renderable_content


class Phase5CoreRecoveryTests(unittest.TestCase):
    def test_needs_core_recovery_when_template_and_core_are_empty(self) -> None:
        self.assertTrue(
            _needs_core_recovery(
                {
                    "fields": {
                        "topic_theme": {"value": "", "evidence": []},
                        "conclusion_direction": {"value": "", "evidence": []},
                    },
                    "todos": [],
                    "core": {
                        "topics": [],
                        "conclusions": [{"text": "今天先不定方案（未形成明确结论）", "status": "no_conclusion", "evidence": ["s007"]}],
                        "decisions": [],
                        "risks": [],
                        "open_questions": [],
                    },
                }
            )
        )

    def test_merge_generation_results_uses_recovery_core(self) -> None:
        merged = _merge_generation_results(
            {
                "summary": "",
                "fields": {},
                "todos": [],
                "core": {
                    "topics": [],
                    "conclusions": [{"text": "今天先不定方案（未形成明确结论）", "status": "no_conclusion", "evidence": ["s007"]}],
                    "decisions": [],
                    "risks": [],
                    "open_questions": [],
                },
            },
            {
                "summary": "讨论 onboarding 任务卡方向",
                "todos": [{"task": "整理岗位版任务卡草案", "owner": "林嘉", "due": "7 月 29 日前", "extra": "", "evidence": ["s008"]}],
                "core": {
                    "topics": [{"title": "方向一", "detail": "按岗位做任务卡", "evidence": ["s002"]}],
                    "conclusions": [{"text": "今天先不定方案（未形成明确结论）", "status": "no_conclusion", "evidence": ["s007"]}],
                    "decisions": [],
                    "risks": [{"text": "培训团队只有两个人，运营可能太重", "level": "", "evidence": ["s005"]}],
                    "open_questions": [{"text": "下周拿三个原型草案和一轮访谈数据回来再看", "evidence": ["s007"]}],
                },
            },
        )

        self.assertEqual(merged["summary"], "讨论 onboarding 任务卡方向")
        self.assertTrue(merged["todos"])
        self.assertTrue(merged["core"]["topics"])
        self.assertTrue(merged["core"]["open_questions"])
        self.assertTrue(merged["meta"]["used_core_recovery"])

    def test_has_renderable_content_accepts_core_only_output(self) -> None:
        self.assertTrue(
            has_renderable_content(
                {
                    "fields": {},
                    "todos": [],
                    "core": {
                        "topics": [{"title": "方向一", "detail": "按岗位做任务卡", "evidence": ["s002"]}],
                        "conclusions": [],
                        "decisions": [],
                        "risks": [],
                        "open_questions": [],
                    },
                }
            )
        )


if __name__ == "__main__":
    unittest.main()
