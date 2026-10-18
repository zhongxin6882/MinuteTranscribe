from __future__ import annotations

import unittest

from evals.judge_core_recall import evaluate_minutes, get_case_spec, load_manifest


class Phase3CoreRecallTests(unittest.TestCase):
    def test_general_no_conclusion_case_passes_with_expected_core(self) -> None:
        manifest = load_manifest()
        case_spec = get_case_spec("general_no_conclusion_001", manifest)
        result = evaluate_minutes(
            case_spec,
            {
                "meeting_type": "general_meeting",
                "summary": "讨论问题，但未拍板。",
                "core": {
                    "topics": [
                        {"title": "首页改版", "detail": "用户路径变长，推荐区和搜索入口都被讨论", "evidence": ["s001", "s003"]},
                    ],
                    "conclusions": [
                        {"text": "今天先把问题列清，不在这次会上拍板首页结构", "status": "no_conclusion", "evidence": ["s004"]},
                    ],
                    "decisions": [],
                    "risks": [],
                    "open_questions": [
                        {"text": "等下周有埋点和访谈结果以后，再决定是改入口还是改推荐区", "evidence": ["s005"]},
                    ],
                },
                "todos": [],
            },
        )

        self.assertTrue(result["ok"])
        self.assertGreaterEqual(result["score"], 0.9)

    def test_speaker_missing_case_fails_if_owner_is_fabricated(self) -> None:
        manifest = load_manifest()
        case_spec = get_case_spec("speaker_missing_all_001", manifest)
        result = evaluate_minutes(
            case_spec,
            {
                "meeting_type": "universal_minutes",
                "summary": "",
                "core": {
                    "topics": [
                        {"title": "问题清单", "detail": "检索排序、FAQ、移动端展示信息不全", "evidence": ["s002"]},
                    ],
                    "conclusions": [
                        {"text": "纪要里不要凭空写负责人", "status": "confirmed", "evidence": ["s005"]},
                    ],
                    "decisions": [],
                    "risks": [],
                    "open_questions": [],
                },
                "todos": [
                    {"task": "FAQ 数据全量同步", "owner": "张三", "due": "下周一前", "extra": "", "evidence": ["s003"]},
                    {"task": "移动端结果卡片改版", "owner": "", "due": "下周三前", "extra": "", "evidence": ["s003"]},
                    {"task": "评估方案整理", "owner": "", "due": "本周五前", "extra": "", "evidence": ["s004"]},
                ],
            },
        )

        self.assertFalse(result["ok"])
        self.assertIn("expected all todo owners to be empty", result["findings"])


if __name__ == "__main__":
    unittest.main()
