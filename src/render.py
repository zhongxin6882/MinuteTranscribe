from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from .schema import MeetingType, Transcript


def render_markdown(minutes: dict[str, Any], transcript: Transcript | None = None) -> str:
    return render_three_section_markdown(minutes, transcript)


def render_three_section_markdown(minutes: dict[str, Any], transcript: Transcript | None = None) -> str:
    meeting_type = minutes.get("meeting_type") or "general_meeting"
    core = minutes.get("core") if isinstance(minutes.get("core"), dict) else {}
    todos = _todo_items(minutes)
    topic_lines = _topic_lines(core)
    conclusion_lines = _conclusion_lines(core)
    decision_lines = _decision_lines(core)
    risk_lines = _risk_lines(core)
    open_question_lines = _open_question_lines(core)
    chapter_lines = _chapter_lines(core, transcript)
    quote_blocks = _quote_blocks(core, transcript)
    decision_summary = _key_decision_block(core, todos)
    summary_text = _summary_text(minutes, topic_lines, conclusion_lines, decision_lines, risk_lines, open_question_lines)
    lines = [f"# 智能纪要：{TYPE_TITLES.get(meeting_type, '会议纪要')}", "", "## 总结", summary_text, ""]
    lines.extend(_render_core_conclusion_section(conclusion_lines))
    lines.append("")
    lines.extend(_render_problem_section(topic_lines, decision_lines, risk_lines, open_question_lines))
    lines.append("")
    lines.extend(_render_action_plan_section(todos))
    lines.append("")
    lines.extend(_render_todo_section(todos))
    if chapter_lines:
        lines.append("")
        lines.extend(_render_chapter_section(chapter_lines))
    if decision_summary:
        lines.append("")
        lines.extend(_render_key_decision_section(decision_summary))
    if quote_blocks:
        lines.append("")
        lines.extend(_render_quote_section(quote_blocks))
    return "\n".join(lines).strip() + "\n"


def render_document_html(markdown: str) -> str:
    lines = markdown.splitlines()
    parts: list[str] = []
    index = 0
    in_list = False
    while index < len(lines):
        raw_line = lines[index].rstrip()
        line = raw_line.strip()
        if not line:
            if in_list:
                parts.append("</ul>")
                in_list = False
            index += 1
            continue
        if line.startswith("# "):
            if in_list:
                parts.append("</ul>")
                in_list = False
            parts.append(f'<h1 class="doc-title">{html.escape(line[2:].strip())}</h1>')
            index += 1
            continue
        if line.startswith("## "):
            if in_list:
                parts.append("</ul>")
                in_list = False
            parts.append(f'<h2 class="doc-section">{html.escape(line[3:].strip())}</h2>')
            index += 1
            continue
        if line.startswith("### "):
            if in_list:
                parts.append("</ul>")
                in_list = False
            parts.append(f'<h3 class="doc-subsection">{html.escape(line[4:].strip())}</h3>')
            index += 1
            continue
        if line.startswith("#### "):
            if in_list:
                parts.append("</ul>")
                in_list = False
            parts.append(f'<h4 class="doc-minorsection">{html.escape(line[5:].strip())}</h4>')
            index += 1
            continue
        if _is_table_header(lines, index):
            if in_list:
                parts.append("</ul>")
                in_list = False
            table_html, index = _render_table(lines, index)
            parts.append(table_html)
            continue
        if _is_ordered_item(line):
            if in_list:
                parts.append("</ul>")
                in_list = False
            parts.append(f'<h3 class="doc-subsection">{html.escape(_strip_ordered_item(line))}</h3>')
            index += 1
            continue
        if line.startswith("- "):
            if not in_list:
                parts.append('<ul class="doc-list">')
                in_list = True
            parts.append(f"<li>{html.escape(line[2:].strip())}</li>")
            index += 1
            continue
        if in_list:
            parts.append("</ul>")
            in_list = False
        parts.append(f'<p class="doc-paragraph">{html.escape(line)}</p>')
        index += 1
    if in_list:
        parts.append("</ul>")
    return "\n".join(parts)


def render_todo_rows(todos: list[dict[str, Any]], columns: int = 5) -> str:
    if not todos:
        return "| " + " | ".join("" for _ in range(columns)) + " |"
    rows = []
    for item in todos:
        rows.append(
            "| {task} | {owner} | {due} | {extra} | {remark} |".format(
                task=_cell(item.get("task")),
                owner=_cell(item.get("owner")),
                due=_cell(item.get("due")),
                extra=_cell(item.get("extra")),
                remark=_cell("证据：" + ",".join(item.get("evidence") or [])),
            )
        )
    return "\n".join(rows)


def render_html(markdown: str, transcript: Transcript, minutes: dict[str, Any]) -> str:
    original_rows = "\n".join(
        f"<tr><td>{html.escape(segment.seg_id)}</td><td>{html.escape(segment.start or '')}</td>"
        f"<td>{html.escape(segment.speaker or '')}</td><td>{html.escape(segment.text)}</td></tr>"
        for segment in transcript.segments
    )
    cleaned_rows = "\n".join(
        f"<tr><td>{html.escape(segment.seg_id)}</td><td>{html.escape(segment.cleaned_text)}</td></tr>"
        for segment in transcript.segments
    )
    classification = html.escape(json.dumps(minutes.get("classification", {}), ensure_ascii=False, indent=2))
    document_html = render_document_html(markdown)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>会议纪要</title>
  <style>
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f6f3ed; color: #1d1b16; }}
    main {{ display: grid; grid-template-columns: minmax(0, 1fr) minmax(360px, 0.9fr); gap: 18px; padding: 24px; }}
    section {{ background: #fffaf0; border: 1px solid #ded3bd; border-radius: 18px; padding: 20px; box-shadow: 0 14px 40px rgba(65, 48, 20, 0.08); }}
    pre {{ white-space: pre-wrap; line-height: 1.65; font-size: 14px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; margin: 12px 0 24px; }}
    th, td {{ border-bottom: 1px solid #e6dcc8; padding: 8px; vertical-align: top; text-align: left; }}
    h1, h2 {{ margin-top: 0; }}
    .meta {{ color: #715d3c; font-size: 13px; }}
    .doc-sheet {{ background: #fff; border: 1px solid #e5d8c1; border-radius: 12px; padding: 40px 46px; }}
    .doc-title {{ margin: 0 0 28px; font-size: 30px; text-align: center; letter-spacing: 0.02em; }}
    .doc-section {{ margin: 28px 0 14px; font-size: 22px; border-bottom: 1px solid #eadfcf; padding-bottom: 8px; }}
    .doc-subsection {{ margin: 20px 0 10px; font-size: 18px; }}
    .doc-minorsection {{ margin: 16px 0 8px; font-size: 16px; font-weight: 600; }}
    .doc-paragraph {{ margin: 8px 0; line-height: 1.9; font-size: 15px; }}
    .doc-list {{ margin: 10px 0 16px 0; padding-left: 22px; line-height: 1.9; }}
    .doc-list li {{ margin: 4px 0; }}
    .doc-table {{ width: 100%; border-collapse: collapse; margin: 14px 0 24px; font-size: 14px; }}
    .doc-table th, .doc-table td {{ border: 1px solid #d8ccb5; padding: 10px 12px; text-align: left; vertical-align: top; }}
    .doc-table th {{ background: #f5efe4; font-weight: 600; }}
    @media (max-width: 900px) {{ main {{ grid-template-columns: 1fr; padding: 12px; }} }}
  </style>
</head>
<body>
  <main>
    <section>
      <h1>会议纪要</h1>
      <p class="meta">第一版暂不支持点击高亮，证据 seg_id 已保留在待办备注与结构化 JSON 中。</p>
      <div class="doc-sheet">{document_html}</div>
    </section>
    <section>
      <h2>会议类型判定</h2>
      <pre>{classification}</pre>
      <h2>原文</h2>
      <table><thead><tr><th>ID</th><th>时间</th><th>说话人</th><th>内容</th></tr></thead><tbody>{original_rows}</tbody></table>
      <h2>Cleaned Version</h2>
      <table><thead><tr><th>ID</th><th>内容</th></tr></thead><tbody>{cleaned_rows}</tbody></table>
    </section>
  </main>
</body>
</html>
"""


def write_outputs(output_dir: str | Path, transcript: Transcript, minutes: dict[str, Any]) -> dict[str, Path]:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    markdown = render_markdown(minutes, transcript)
    paths = {
        "json": target / "minutes.json",
        "md": target / "minutes.md",
        "html": target / "minutes.html",
        "transcript": target / "transcript.cleaned.json",
    }
    paths["json"].write_text(json.dumps(minutes, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["md"].write_text(markdown, encoding="utf-8")
    paths["html"].write_text(render_html(markdown, transcript, minutes), encoding="utf-8")
    paths["transcript"].write_text(json.dumps(transcript.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return paths


TYPE_TITLES: dict[MeetingType, str] = {
    "project_sync": "项目同步会议",
    "decision_review": "决策评审会议",
    "issue_triage": "问题排查会议",
    "brainstorming": "头脑风暴会议",
    "interview_research": "访谈调研会议",
    "universal_minutes": "会议纪要",
    "general_meeting": "普通会议",
}


def _has_core_content(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    for bucket in value.values():
        if isinstance(bucket, list) and bucket:
            return True
    return False


def _summary_text(
    minutes: dict[str, Any],
    topic_lines: list[str],
    conclusion_lines: list[str],
    decision_lines: list[str],
    risk_lines: list[str],
    open_question_lines: list[str],
) -> str:
    candidates = [
        str(minutes.get("会议概要") or "").strip(),
        str(minutes.get("summary") or "").strip(),
        _prefer(topic_lines),
        _prefer(conclusion_lines),
        _prefer(decision_lines),
        _prefer(risk_lines),
        _prefer(open_question_lines),
    ]
    for candidate in candidates:
        if candidate and candidate != "无":
            return candidate
    return "暂无总结"


def _render_core_conclusion_section(
    conclusion_lines: list[str],
) -> list[str]:
    lines = ["## 核心结论"]
    if conclusion_lines:
        for item in conclusion_lines[:3]:
            lines.append(f"- {item}")
    else:
        lines.append("- 暂无明确结论")
    return lines


def _render_problem_section(
    topic_lines: list[str],
    decision_lines: list[str],
    risk_lines: list[str],
    open_question_lines: list[str],
) -> list[str]:
    lines = ["## 现状与核心问题", "### 业务现状与关键反馈"]
    if topic_lines:
        for item in topic_lines[:4]:
            lines.append(f"- {item}")
    else:
        lines.append("- 暂无可归纳的现状反馈")

    lines.append("")
    lines.append("### 团队分歧与潜在风险")
    judgment_rows = _judgment_rows(decision_lines, open_question_lines, risk_lines)
    if judgment_rows:
        lines.append("#### 主要判断")
        for row in judgment_rows:
            lines.append(f"- {row[1]}")
        lines.append("")
        lines.append("#### 观点对比")
        lines.append("| 观点类型 | 核心思路 | 补充说明 |")
        lines.append("|---|---|---|")
        for row in judgment_rows:
            lines.append(f"| {_cell(row[0])} | {_cell(row[1])} | {_cell(row[2])} |")
    else:
        lines.append("- 暂无明确分歧观点")

    lines.append("")
    lines.append("#### 核心风险提示")
    if risk_lines:
        for item in risk_lines[:4]:
            lines.append(f"- {item}")
    else:
        lines.append("- 暂无明确风险提示")
    return lines


def _render_action_plan_section(todos: list[dict[str, Any]]) -> list[str]:
    lines = ["## 阶段性待办安排", "| 责任角色 | 待办事项 | 完成时间节点 | 核心输出要求 |", "|---|---|---|---|"]
    if not todos:
        lines.append("| 未明确 | 暂无待办 | 未明确 | 暂无 |")
        return lines
    for item in todos:
        lines.append(
            "| {owner} | {task} | {due} | {extra} |".format(
                owner=_cell(item.get("owner") or "未明确"),
                task=_cell(item.get("task")),
                due=_cell(item.get("due") or "未明确"),
                extra=_cell(item.get("extra") or "待补充"),
            )
        )
    return lines


def _render_todo_section(todos: list[dict[str, Any]]) -> list[str]:
    lines = ["## 待办"]
    if not todos:
        lines.append("- 暂无待办事项")
        return lines
    for item in todos:
        due = str(item.get("due") or "").strip()
        owner = str(item.get("owner") or "").strip()
        extra = str(item.get("extra") or "").strip()
        detail = str(item.get("task") or "").strip()
        if owner:
            detail += f"；负责人：{owner}"
        if due:
            detail += f"；时间：{due}"
        if extra:
            detail += f"；补充：{extra}"
        lines.append(f"- {detail}")
    return lines


def _render_chapter_section(chapter_lines: list[str]) -> list[str]:
    return ["## 智能章节", *[f"- {item}" for item in chapter_lines]]


def _render_key_decision_section(decision_summary: dict[str, Any]) -> list[str]:
    lines = ["## 关键决策", f"- 关键决策：{decision_summary['decision']}"]
    if decision_summary.get("question"):
        lines.append(f"- 问题：{decision_summary['question']}")
    if decision_summary.get("options"):
        lines.append("- 讨论方案：")
        for item in decision_summary["options"]:
            lines.append(f"  {item}")
    if decision_summary.get("basis"):
        lines.append(f"- 决策依据：{decision_summary['basis']}")
    if decision_summary.get("other_actions"):
        lines.append("- 其他安排：")
        for item in decision_summary["other_actions"]:
            lines.append(f"  {item}")
    return lines


def _render_quote_section(quote_blocks: list[dict[str, str]]) -> list[str]:
    lines = ["## 金句时刻"]
    for item in quote_blocks:
        lines.append(f"> {item['quote']}")
        lines.append(f"- {item['note']}")
        lines.append("")
    if lines[-1] == "":
        lines.pop()
    return lines


def _todo_items(minutes: dict[str, Any]) -> list[dict[str, Any]]:
    todos = minutes.get("todos")
    if isinstance(todos, list):
        return [item for item in todos if isinstance(item, dict)]
    section_todos = minutes.get("待办事项")
    if isinstance(section_todos, list):
        return [item for item in section_todos if isinstance(item, dict)]
    return []


def _judgment_rows(
    decision_lines: list[str],
    open_question_lines: list[str],
    risk_lines: list[str],
) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for item in decision_lines[:2]:
        rows.append(("候选决策", item, "会议中已明确被讨论的决策方向"))
    for item in open_question_lines[:2]:
        rows.append(("待确认问题", item, "当前仍需补充验证或继续讨论"))
    for item in risk_lines[:1]:
        rows.append(("关键风险", item, "与执行或判断相关的主要风险点"))
    return rows[:3]


def _chapter_lines(core: dict[str, Any], transcript: Transcript | None) -> list[str]:
    if transcript is None:
        return []
    segment_map = {segment.seg_id: segment for segment in transcript.segments}
    chapters: list[tuple[str, str]] = []
    for item in core.get("topics") or []:
        if not isinstance(item, dict):
            continue
        evidence = item.get("evidence") if isinstance(item.get("evidence"), list) else []
        if not evidence:
            continue
        segment = segment_map.get(str(evidence[0]))
        if segment is None:
            continue
        title = str(item.get("title") or item.get("detail") or "").strip() or segment.text.strip()
        chapters.append((segment.start or "00:00", title[:28]))
    if not chapters:
        for segment in transcript.segments[: min(6, len(transcript.segments))]:
            text = str(segment.cleaned_text or segment.text or "").strip()
            if not text:
                continue
            chapters.append((segment.start or "00:00", text[:28]))
    deduped: list[str] = []
    seen: set[tuple[str, str]] = set()
    for start, title in chapters:
        key = (start, title)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(f"{start}  {title}")
    return deduped[:8]


def _key_decision_block(core: dict[str, Any], todos: list[dict[str, Any]]) -> dict[str, Any] | None:
    conclusions = _conclusion_lines(core)
    decisions = _decision_lines(core)
    questions = _open_question_lines(core)
    risks = _risk_lines(core)
    if not any((conclusions, decisions, questions, todos)):
        return None
    decision_text = decisions[0] if decisions else conclusions[0] if conclusions else "本次会议形成阶段性安排，后续继续跟进。"
    question_text = questions[0] if questions else _topic_lines(core)[0] if _topic_lines(core) else ""
    option_lines = [f"- {item}" for item in (decisions[:2] or questions[:2])]
    basis = risks[0] if risks else conclusions[1] if len(conclusions) > 1 else ""
    other_actions = [
        f"- {str(item.get('task') or '').strip()}（{str(item.get('due') or '时间未明确').strip()}）"
        for item in todos[:3]
        if isinstance(item, dict) and str(item.get("task") or "").strip()
    ]
    return {
        "decision": decision_text,
        "question": question_text,
        "options": option_lines,
        "basis": basis,
        "other_actions": other_actions,
    }


def _quote_blocks(core: dict[str, Any], transcript: Transcript | None) -> list[dict[str, str]]:
    if transcript is None:
        return []
    segment_map = {segment.seg_id: segment for segment in transcript.segments}
    blocks: list[dict[str, str]] = []
    source_buckets = [
        ("结论原话", core.get("conclusions") or []),
        ("待确认原话", core.get("open_questions") or []),
        ("风险原话", core.get("risks") or []),
    ]
    for label, items in source_buckets:
        for item in items:
            if not isinstance(item, dict):
                continue
            evidence = item.get("evidence") if isinstance(item.get("evidence"), list) else []
            if not evidence:
                continue
            segment = segment_map.get(str(evidence[0]))
            if segment is None:
                continue
            quote = str(segment.text or "").strip()
            if len(quote) < 12:
                continue
            blocks.append({"quote": quote, "note": f"对应{label}，可直接作为纪要中的代表性表达。"})
            break
    deduped: list[dict[str, str]] = []
    seen_quotes: set[str] = set()
    for item in blocks:
        if item["quote"] in seen_quotes:
            continue
        seen_quotes.add(item["quote"])
        deduped.append(item)
    return deduped[:3]


def _render_agenda_section(
    meeting_type: str,
    topic_lines: list[str],
    decision_lines: list[str],
    risk_lines: list[str],
    open_question_lines: list[str],
) -> list[str]:
    lines: list[str] = []
    if meeting_type == "project_sync":
        lines.extend(
            _render_named_block(
                "1. 进展与现状",
                [
                    ("重点进展", _prefer(topic_lines)),
                    ("当前风险", _prefer(risk_lines)),
                    ("待确认问题", _prefer(open_question_lines)),
                ],
            )
        )
    elif meeting_type == "decision_review":
        lines.extend(
            _render_named_block(
                "1. 决策背景与讨论焦点",
                [
                    ("讨论议题", _prefer(topic_lines)),
                    ("已讨论决策项", _prefer(decision_lines)),
                    ("风险与约束", _prefer(risk_lines)),
                    ("待补充依据", _prefer(open_question_lines)),
                ],
            )
        )
    elif meeting_type == "issue_triage":
        lines.extend(
            _render_named_block(
                "1. 问题现象与排查重点",
                [
                    ("问题与现象", _prefer(topic_lines)),
                    ("可能风险或影响", _prefer(risk_lines)),
                    ("待确认问题", _prefer(open_question_lines)),
                ],
            )
        )
    elif meeting_type == "brainstorming":
        lines.extend(
            _render_named_block(
                "1. 讨论主题与主要想法",
                [
                    ("主要想法", _prefer(topic_lines)),
                    ("分歧与约束", _prefer(risk_lines)),
                    ("开放问题", _prefer(open_question_lines)),
                ],
            )
        )
    elif meeting_type == "interview_research":
        lines.extend(
            _render_named_block(
                "1. 访谈发现与用户反馈",
                [
                    ("关键观点", _prefer(topic_lines)),
                    ("风险与保留意见", _prefer(risk_lines)),
                    ("待验证问题", _prefer(open_question_lines)),
                ],
            )
        )
    elif meeting_type == "universal_minutes":
        lines.extend(
            _render_named_block(
                "1. 会议重点",
                [
                    ("主要议题", _prefer(topic_lines)),
                    ("关键风险", _prefer(risk_lines)),
                    ("待确认事项", _prefer(open_question_lines)),
                ],
            )
        )
    else:
        lines.extend(
            _render_named_block(
                "1. 本次讨论事项",
                [
                    ("讨论议题", _prefer(topic_lines)),
                    ("重点信息", _prefer(risk_lines)),
                    ("待确认问题", _prefer(open_question_lines)),
                ],
            )
        )
    return lines


def _render_conclusion_section(
    meeting_type: str,
    conclusion_lines: list[str],
    decision_lines: list[str],
    open_question_lines: list[str],
) -> list[str]:
    lines = ["## 结论"]
    if meeting_type == "decision_review":
        pairs = [
            ("已明确决策", _prefer(decision_lines)),
            ("已明确结论", _prefer(conclusion_lines)),
            ("待验证问题", _prefer(open_question_lines)),
        ]
    elif meeting_type == "brainstorming":
        pairs = [
            ("当前形成方向", _prefer(conclusion_lines)),
            ("优先尝试事项", _prefer(decision_lines)),
            ("下一轮讨论重点", _prefer(open_question_lines)),
        ]
    else:
        pairs = [
            ("已明确结论", _prefer(conclusion_lines)),
            ("已做决策", _prefer(decision_lines)),
            ("仍需跟进问题", _prefer(open_question_lines)),
        ]
    for label, value in pairs:
        lines.append(f"- {label}：{value}")
    return lines


def _render_named_block(title: str, pairs: list[tuple[str, str]]) -> list[str]:
    lines = [title]
    for label, value in pairs:
        lines.append(f"- {label}：{value}")
    return lines


def _topic_lines(core: dict[str, Any]) -> list[str]:
    lines = []
    for item in core.get("topics") or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        detail = str(item.get("detail") or "").strip()
        if detail:
            lines.append(detail)
        elif title:
            lines.append(title)
    return lines


def _conclusion_lines(core: dict[str, Any]) -> list[str]:
    lines = []
    for item in core.get("conclusions") or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        status = str(item.get("status") or "").strip()
        if status == "no_conclusion" and "未形成明确结论" not in text:
            lines.append(f"{text}（未形成明确结论）")
        else:
            lines.append(text)
    return lines


def _decision_lines(core: dict[str, Any]) -> list[str]:
    lines = []
    for item in core.get("decisions") or []:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or "").strip()
        decision = str(item.get("decision") or "").strip()
        if decision:
            lines.append(f"{question}：{decision}" if question else decision)
    return lines


def _risk_lines(core: dict[str, Any]) -> list[str]:
    lines = []
    for item in core.get("risks") or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        level = str(item.get("level") or "").strip()
        lines.append(f"{text}（{level}）" if level else text)
    return lines


def _open_question_lines(core: dict[str, Any]) -> list[str]:
    lines = []
    for item in core.get("open_questions") or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if text:
            lines.append(text)
    return lines


def _prefer(lines: list[str]) -> str:
    if not lines:
        return "无"
    return "；".join(lines[:3])


def _cell(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")


def _is_ordered_item(line: str) -> bool:
    return len(line) > 2 and line[0].isdigit() and line[1] == "."


def _strip_ordered_item(line: str) -> str:
    return line.split(".", 1)[1].strip()


def _is_table_header(lines: list[str], index: int) -> bool:
    if index + 1 >= len(lines):
        return False
    return lines[index].strip().startswith("|") and lines[index + 1].strip().startswith("|---")


def _render_table(lines: list[str], index: int) -> tuple[str, int]:
    header = [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
    rows: list[list[str]] = []
    index += 2
    while index < len(lines):
        line = lines[index].strip()
        if not line.startswith("|"):
            break
        rows.append([cell.strip() for cell in line.strip("|").split("|")])
        index += 1
    header_html = "".join(f"<th>{html.escape(cell)}</th>" for cell in header)
    body_html: list[str] = []
    for row in rows:
        cells = "".join(f"<td>{html.escape(cell)}</td>" for cell in row)
        body_html.append(f"<tr>{cells}</tr>")
    return f'<table class="doc-table"><thead><tr>{header_html}</tr></thead><tbody>{"".join(body_html)}</tbody></table>', index
