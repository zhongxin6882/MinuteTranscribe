from __future__ import annotations

import unittest

from src.render import render_document_html, render_markdown
from src.schema import Segment, Transcript


class Phase2RenderingTests(unittest.TestCase):
    def test_render_markdown_prefers_core_content(self) -> None:
        markdown = render_markdown(
            {
                "meeting_type": "decision_review",
                "summary": "本次评审围绕首页推荐是否上线展开，先补充数据后再定最终方案。",
                "core": {
                    "topics": [
                        {"title": "首页推荐问题", "detail": "讨论是否默认展示推荐问题", "evidence": ["s001"]},
                    ],
                    "conclusions": [
                        {"text": "先补数据，下次评审再定最终方案", "status": "no_conclusion", "evidence": ["s006"]},
                    ],
                    "decisions": [
                        {"question": "本次是否拍板", "decision": "本次不拍板", "evidence": ["s004", "s006"]},
                    ],
                    "risks": [
                        {"text": "缺少移动端点击率和留存数据", "level": "", "evidence": ["s004"]},
                    ],
                    "open_questions": [
                        {"text": "需要补一轮用户反馈", "evidence": ["s005"]},
                    ],
                },
                "todos": [
                    {
                        "task": "补移动端点击率和留存对比数据",
                        "owner": "产品经理陈溪",
                        "due": "",
                        "extra": "下次评审前",
                        "evidence": ["s006"],
                    }
                ],
            }
        )

        self.assertIn("# 智能纪要：决策评审会议", markdown)
        self.assertIn("## 总结", markdown)
        self.assertIn("## 核心结论", markdown)
        self.assertIn("## 现状与核心问题", markdown)
        self.assertIn("## 阶段性待办安排", markdown)
        self.assertIn("## 待办", markdown)
        self.assertIn("本次评审围绕首页推荐是否上线展开，先补充数据后再定最终方案。", markdown)
        self.assertIn("先补数据，下次评审再定最终方案（未形成明确结论）", markdown)
        self.assertIn("本次是否拍板：本次不拍板", markdown)
        self.assertNotIn("{topic_background}", markdown)

    def test_render_markdown_uses_summary_and_core_only(self) -> None:
        markdown = render_markdown(
            {
                "meeting_type": "general_meeting",
                "summary": "同步下周排期，当前还需要先确定资源。",
                "core": {
                    "topics": [
                        {"title": "排期同步", "detail": "同步下周排期", "evidence": ["s001"]},
                    ],
                    "conclusions": [
                        {"text": "本周先收集意见", "status": "confirmed", "evidence": ["s004"]},
                    ],
                    "decisions": [],
                    "risks": [],
                    "open_questions": [
                        {"text": "最终排期待下次确认", "evidence": ["s005"]},
                    ],
                },
                "todos": [],
            }
        )

        self.assertIn("# 智能纪要：普通会议", markdown)
        self.assertIn("## 总结", markdown)
        self.assertIn("## 核心结论", markdown)
        self.assertIn("同步下周排期", markdown)
        self.assertIn("本周先收集意见", markdown)

    def test_render_markdown_includes_chapters_and_quotes_when_transcript_available(self) -> None:
        transcript = Transcript(
            meeting_id="m001",
            segments=[
                Segment(seg_id="s001", speaker=None, start="00:00", text="今天先复盘首页改版后的数据表现。", cleaned_text="今天先复盘首页改版后的数据表现。"),
                Segment(seg_id="s002", speaker=None, start="00:30", text="我们暂时不拍板，等数据补齐后再做最终决定。", cleaned_text="我们暂时不拍板，等数据补齐后再做最终决定。"),
                Segment(seg_id="s003", speaker=None, start="01:10", text="当前埋点还不够细，无法准确定位用户卡点。", cleaned_text="当前埋点还不够细，无法准确定位用户卡点。"),
            ],
        )
        markdown = render_markdown(
            {
                "meeting_type": "general_meeting",
                "summary": "本次会议围绕首页改版复盘和后续动作安排展开。",
                "core": {
                    "topics": [{"title": "首页改版复盘", "detail": "复盘首页改版后的数据表现。", "evidence": ["s001"]}],
                    "conclusions": [{"text": "暂不拍板，待补齐数据后再做决定。", "status": "no_conclusion", "evidence": ["s002"]}],
                    "decisions": [],
                    "risks": [{"text": "埋点还不够细，无法准确定位用户卡点。", "level": "", "evidence": ["s003"]}],
                    "open_questions": [],
                },
                "todos": [],
            },
            transcript,
        )
        self.assertIn("## 智能章节", markdown)
        self.assertIn("00:00  首页改版复盘", markdown)
        self.assertIn("## 金句时刻", markdown)
        self.assertIn("我们暂时不拍板，等数据补齐后再做最终决定。", markdown)

    def test_render_document_html_converts_nested_markdown_headings(self) -> None:
        markdown = "\n".join([
            "# 智能纪要：会议纪要",
            "",
            "## 现状与核心问题",
            "### 业务现状与关键反馈",
            "- 第一条反馈",
            "",
            "### 团队分歧与潜在风险",
            "#### 主要判断",
            "- 需要先补材料",
        ])

        html = render_document_html(markdown)

        self.assertIn('<h3 class="doc-subsection">业务现状与关键反馈</h3>', html)
        self.assertIn('<h3 class="doc-subsection">团队分歧与潜在风险</h3>', html)
        self.assertIn('<h4 class="doc-minorsection">主要判断</h4>', html)
        self.assertNotIn("### 业务现状与关键反馈", html)
        self.assertNotIn("#### 主要判断", html)


if __name__ == "__main__":
    unittest.main()
