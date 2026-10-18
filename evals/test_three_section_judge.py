from __future__ import annotations

import unittest

from evals.judge_three_section_minutes import evaluate_minutes, get_case_spec, load_manifest


class ThreeSectionJudgeTests(unittest.TestCase):
    def test_project_sync_case(self) -> None:
        manifest = load_manifest()
        case_spec = get_case_spec("project_sync_001", manifest)
        result = evaluate_minutes(
            case_spec,
            {
                "meeting_type": "project_sync",
                "summary": "回顾项目进展，确认问题与下一步。",
                "core": {
                    "topics": [
                        {"title": "项目进展", "detail": "当前项目阶段稳定，存在阻塞与风险", "evidence": ["s001"]},
                        {"title": "下一步计划", "detail": "后续计划需要继续推进", "evidence": ["s002"]},
                    ],
                    "conclusions": [{"text": "需要先补数据再推进", "status": "confirmed", "evidence": ["s002"]}],
                    "decisions": [],
                    "risks": [{"text": "有阻塞", "level": "", "evidence": ["s003"]}],
                    "open_questions": [],
                },
                "todos": [
                    {"task": "王珊跟进项目问题", "owner": "王珊", "due": "周五前", "extra": "", "evidence": ["s004"]},
                    {"task": "赵强整理下一步计划", "owner": "赵强", "due": "明天下午六点前", "extra": "", "evidence": ["s005"]},
                ],
            },
        )
        self.assertTrue(result["ok"])

    def test_rendered_three_section_case(self) -> None:
        manifest = load_manifest()
        case_spec = get_case_spec("project_sync_001", manifest)
        result = evaluate_minutes(
            case_spec,
            {
                "meeting_type": "project_sync",
                "会议概要": "本次会议同步了项目进展，明确当前主要问题是上线阻塞，并确认下一步先完成修复再安排回归。",
                "会议议题": [
                    {
                        "title": "项目进展",
                        "summary": "团队确认当前项目整体推进正常，但上线前还有阻塞项未关闭。",
                        "decision": "先解决阻塞问题，再进入发布确认。",
                    },
                    {
                        "title": "下一步计划",
                        "summary": "测试会在阻塞项关闭后组织回归，研发同步完成修复。",
                        "decision": "本周内完成修复并推进后续计划。",
                    },
                ],
                "待办事项": [
                    {"task": "王珊跟进阻塞问题修复", "owner": "王珊", "due": ""},
                    {"task": "赵强整理回归计划", "owner": "赵强", "due": ""},
                ],
            },
        )
        self.assertTrue(result["ok"])

    def test_missing_owner_fails(self) -> None:
        manifest = load_manifest()
        case_spec = get_case_spec("speaker_missing_all_001", manifest)
        result = evaluate_minutes(
            case_spec,
            {
                "meeting_type": "universal_minutes",
                "summary": "检索排序、FAQ、移动端都存在问题。",
                "core": {
                    "topics": [{"title": "检索排序", "detail": "FAQ 和移动端也在讨论", "evidence": ["s001"]}],
                    "conclusions": [],
                    "decisions": [],
                    "risks": [],
                    "open_questions": [],
                },
                "todos": [{"task": "FAQ 数据全量同步", "owner": "张三", "due": "下周一前", "extra": "", "evidence": ["s003"]}],
            },
        )
        self.assertFalse(result["ok"])
        self.assertIn("expected all todo owners to be empty", result["findings"])


if __name__ == "__main__":
    unittest.main()
