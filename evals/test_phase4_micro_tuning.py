from __future__ import annotations

import unittest

from src.classify import infer_risk_tags
from src.generate import (
    build_extraction_strategy,
    derive_no_conclusion_item,
    derive_open_question_items,
    derive_transcript_fallback,
    derive_todo_items,
    tune_generation_result,
)
from src.schema import Classification, Segment, Transcript


class Phase4MicroTuningTests(unittest.TestCase):
    def test_infer_risk_tags_keeps_no_clear_conclusion_even_with_due_and_owner(self) -> None:
        transcript = Transcript(
            meeting_id="m001",
            segments=[
                Segment(
                    seg_id="s001",
                    speaker="产品经理陈溪",
                    start="00:00:10",
                    text="先补数据，下次评审再定最终方案。我负责整理结论，周五前给大家。",
                    cleaned_text="先补数据，下次评审再定最终方案。我负责整理结论，周五前给大家。",
                )
            ],
        )

        tags = infer_risk_tags(transcript, transcript.segments[0].cleaned_text)
        self.assertIn("no_clear_conclusion", tags)

    def test_tune_generation_result_adds_no_conclusion_and_clears_missing_speaker_owner(self) -> None:
        transcript = Transcript(
            meeting_id="m002",
            segments=[
                Segment(seg_id="s001", speaker=None, start="00:00:12", text="今天先把问题列清，不在这次会上拍板首页结构。", cleaned_text="今天先把问题列清，不在这次会上拍板首页结构。"),
                Segment(seg_id="s002", speaker=None, start="00:01:10", text="下周一前完成 FAQ 数据全量同步。", cleaned_text="下周一前完成 FAQ 数据全量同步。"),
            ],
        )
        classification = Classification(
            meeting_type="general_meeting",
            confidence=0.6,
            reason="test",
            risk_tags=["speaker_missing", "no_clear_conclusion"],
            template="extract_general_meeting",
        )

        tuned = tune_generation_result(
            {
                "core": {
                    "topics": [{"title": "首页结构", "detail": "讨论改版问题", "evidence": ["s001"]}],
                    "conclusions": [],
                    "decisions": [],
                    "risks": [],
                    "open_questions": [],
                },
                "todos": [
                    {"task": "FAQ 数据全量同步", "owner": "项目组", "due": "下周一前", "extra": "", "evidence": ["s002"]}
                ],
            },
            transcript,
            classification,
        )

        self.assertEqual(tuned["todos"][0]["owner"], "")
        self.assertTrue(tuned["core"]["conclusions"])
        self.assertEqual(tuned["core"]["conclusions"][0]["status"], "no_conclusion")
        self.assertEqual(tuned["core"]["conclusions"][0]["evidence"], ["s001"])
        self.assertEqual(tuned["core"]["conclusions"][0]["text"], "今天先把问题列清，不在这次会上拍板首页结构。")

    def test_build_extraction_strategy_mentions_theme_grouping_for_mixed_meetings(self) -> None:
        transcript = Transcript(
            meeting_id="m003",
            segments=[Segment(seg_id="s001", speaker="周总", start="00:00:10", text="市场、项目、人效、风控都要归纳。", cleaned_text="市场、项目、人效、风控都要归纳。")],
        )
        classification = Classification(
            meeting_type="universal_minutes",
            confidence=0.7,
            reason="test",
            risk_tags=["mixed_type"],
            template="extract_universal_minutes",
        )

        strategy = build_extraction_strategy(classification, transcript)
        self.assertTrue(any("按语义主题归并" in line for line in strategy))
        self.assertTrue(any("信息对象" in line for line in strategy))

    def test_derive_no_conclusion_item_uses_source_segment(self) -> None:
        transcript = Transcript(
            meeting_id="m004",
            segments=[
                Segment(seg_id="s009", speaker="苏北", start="00:06:16", text="今天先不定方案，下周拿三个原型草案和一轮访谈数据回来再看。", cleaned_text="今天先不定方案，下周拿三个原型草案和一轮访谈数据回来再看。")
            ],
        )
        item = derive_no_conclusion_item(transcript)
        self.assertIsNotNone(item)
        self.assertEqual(item["status"], "no_conclusion")
        self.assertEqual(item["evidence"], ["s009"])

    def test_derive_open_question_items_preserves_source_sentence(self) -> None:
        transcript = Transcript(
            meeting_id="m005",
            segments=[
                Segment(seg_id="s005", speaker="王茗", start="00:04:06", text="等下周有埋点和访谈结果以后，再决定是改入口还是改推荐区。", cleaned_text="等下周有埋点和访谈结果以后，再决定是改入口还是改推荐区。")
            ],
        )
        items = derive_open_question_items(transcript)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["text"], "等下周有埋点和访谈结果以后，再决定是改入口还是改推荐区。")
        self.assertEqual(items[0]["evidence"], ["s005"])

    def test_tune_generation_result_adds_source_open_question_fallback(self) -> None:
        transcript = Transcript(
            meeting_id="m006",
            segments=[
                Segment(seg_id="s004", speaker="赵祎", start="00:03:10", text="今天先把问题列清，不在这次会上拍板首页结构。", cleaned_text="今天先把问题列清，不在这次会上拍板首页结构。"),
                Segment(seg_id="s005", speaker="王茗", start="00:04:06", text="等下周有埋点和访谈结果以后，再决定是改入口还是改推荐区。", cleaned_text="等下周有埋点和访谈结果以后，再决定是改入口还是改推荐区。"),
            ],
        )
        classification = Classification(
            meeting_type="general_meeting",
            confidence=0.7,
            reason="test",
            risk_tags=["no_clear_conclusion"],
            template="extract_general_meeting",
        )

        tuned = tune_generation_result(
            {
                "core": {
                    "topics": [{"title": "首页改版", "detail": "讨论路径变长原因", "evidence": ["s004"]}],
                    "conclusions": [],
                    "decisions": [],
                    "risks": [],
                    "open_questions": [{"text": "后续应改搜索入口还是改推荐区，需等下周埋点和访谈结果后再定。", "evidence": ["s005"]}],
                },
                "todos": [],
            },
            transcript,
            classification,
        )

        self.assertEqual(tuned["core"]["open_questions"][0]["text"], "等下周有埋点和访谈结果以后，再决定是改入口还是改推荐区。")
        self.assertEqual(tuned["core"]["open_questions"][0]["evidence"], ["s005"])

    def test_derive_todo_items_extracts_time_bound_actions(self) -> None:
        transcript = Transcript(
            meeting_id="m007",
            segments=[
                Segment(seg_id="s010", speaker="周总", start="00:08:20", text="下周三前市场条线出重点客户台账，8 月 10 日前项目条线完成滞后项目整改计划，月底前人事补齐培训方案。", cleaned_text="下周三前市场条线出重点客户台账，8 月 10 日前项目条线完成滞后项目整改计划，月底前人事补齐培训方案。")
            ],
        )
        todos = derive_todo_items(transcript)
        self.assertEqual(len(todos), 3)
        self.assertTrue(any("重点客户台账" in item["task"] for item in todos))
        self.assertTrue(any("滞后项目整改计划" in item["task"] for item in todos))
        self.assertTrue(any("培训方案" in item["task"] for item in todos))

    def test_derive_todo_items_supports_spoken_due_phrases(self) -> None:
        transcript = Transcript(
            meeting_id="m008",
            segments=[
                Segment(seg_id="s020", speaker=None, start="00:15:30", text="第一项待办，运营负责人在下周二下午六点前，补齐首页点击路径分析，并整理一版数据结论。", cleaned_text="第一项待办，运营负责人在下周二下午六点前，补齐首页点击路径分析，并整理一版数据结论。"),
                Segment(seg_id="s021", speaker=None, start="00:16:00", text="产品经理在下周三下班前完成五到八个用户访谈。", cleaned_text="产品经理在下周三下班前完成五到八个用户访谈。"),
            ],
        )
        todos = derive_todo_items(transcript)
        self.assertTrue(any(item["due"] == "下周二下午六点前" for item in todos))
        self.assertTrue(any("补齐首页点击路径分析" in item["task"] for item in todos))
        self.assertTrue(any(item["due"] == "下周三下班前" for item in todos))
        self.assertTrue(any("完成五到八个用户访谈" in item["task"] for item in todos))

    def test_derive_transcript_fallback_covers_structured_spoken_template(self) -> None:
        transcript = Transcript(
            meeting_id="m009",
            segments=[
                Segment(seg_id="s001", speaker=None, start="00:00:00", text="今天会议的主题，是知识库助手首页改版复盘与下周优化安排。", cleaned_text="今天会议的主题，是知识库助手首页改版复盘与下周优化安排。"),
                Segment(seg_id="s002", speaker=None, start="00:02:00", text="目前最核心的问题主要有三个。", cleaned_text="目前最核心的问题主要有三个。"),
                Segment(seg_id="s003", speaker=None, start="00:10:00", text="基于以上这些判断，我建议今天形成一个阶段性方案，而不是最终方案。", cleaned_text="基于以上这些判断，我建议今天形成一个阶段性方案，而不是最终方案。"),
                Segment(seg_id="s004", speaker=None, start="00:15:30", text="第一项待办，运营负责人在下周二下午六点前，补齐首页点击路径分析。", cleaned_text="第一项待办，运营负责人在下周二下午六点前，补齐首页点击路径分析。"),
                Segment(seg_id="s005", speaker=None, start="00:18:00", text="今天的结论可以概括成一句话，首页改版后的转化问题已经成立，但最终改入口还是改推荐区，今天暂不拍板。", cleaned_text="今天的结论可以概括成一句话，首页改版后的转化问题已经成立，但最终改入口还是改推荐区，今天暂不拍板。"),
            ],
        )
        classification = Classification(
            meeting_type="general_meeting",
            confidence=0.7,
            reason="test",
            risk_tags=["no_clear_conclusion"],
            template="extract_general_meeting",
        )
        fallback = derive_transcript_fallback(transcript, classification)
        self.assertTrue(fallback["core"]["topics"])
        self.assertTrue(fallback["core"]["conclusions"])
        self.assertTrue(fallback["todos"])


if __name__ == "__main__":
    unittest.main()
