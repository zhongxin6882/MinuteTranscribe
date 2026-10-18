from __future__ import annotations

from collections import Counter

from .schema import Classification, MeetingType, Transcript

KEYWORDS: dict[MeetingType, tuple[str, ...]] = {
    "project_sync": ("进度", "阻塞", "排期", "里程碑", "风险", "负责人", "下周", "上线"),
    "decision_review": ("决策", "评审", "需求评审", "方案", "拍板", "通过", "不通过", "取舍", "优劣"),
    "issue_triage": ("问题", "故障", "排查", "原因", "复现", "修复", "影响范围", "止血"),
    "brainstorming": ("头脑风暴", "脑暴", "想法", "创意", "方向", "探索", "试试", "开放", "草案", "可行性"),
    "interview_research": ("受访", "用户访谈", "客户访谈", "痛点", "代表性原话", "使用场景", "体验"),
    "universal_minutes": ("复盘", "部署", "总结", "安排", "推进", "协同", "目标", "任务"),
    "general_meeting": (),
}

PRIORITY: tuple[MeetingType, ...] = (
    "issue_triage",
    "decision_review",
    "project_sync",
    "interview_research",
    "brainstorming",
    "general_meeting",
)


def classify_transcript(transcript: Transcript) -> Classification:
    text = "\n".join(segment.cleaned_text for segment in transcript.segments)
    scores: Counter[MeetingType] = Counter()
    for meeting_type, keywords in KEYWORDS.items():
        for keyword in keywords:
            scores[meeting_type] += text.count(keyword)
    if "需求" in text and any(signal in text for signal in ("用户", "客户", "受访", "痛点", "原话", "体验")):
        scores["interview_research"] += text.count("需求")
    if "头脑风暴" in text or "今天先不定最终方案" in text:
        scores["brainstorming"] += 3
    interview_markers = ("今天访谈的是", "本次访谈", "访谈对象", "用户访谈", "客户访谈", "受访")
    if any(marker in text for marker in interview_markers):
        scores["interview_research"] += 3
    if "同步" in text and any(signal in text for signal in ("进展", "阻塞", "上线", "排期", "里程碑")):
        scores["project_sync"] += 2
    if any(signal in text for signal in ("已完成", "进行中", "下一步", "当前阶段")):
        scores["project_sync"] += 2
    if "反馈" in text and "访谈" not in text and "用户" not in text and "客户" not in text:
        scores["interview_research"] = max(0, scores["interview_research"] - text.count("反馈"))
    if "评审" in text:
        scores["decision_review"] += 2
    if "评审样例" in text or "模板整理" in text:
        scores["decision_review"] = max(0, scores["decision_review"] - 2)
    if "活动安排" in text or "录屏" in text or "内测群" in text:
        scores["general_meeting"] += 2

    best_type: MeetingType = "general_meeting"
    best_score = 0
    for meeting_type in PRIORITY:
        score = scores[meeting_type]
        if score > best_score:
            best_type = meeting_type
            best_score = score

    top_signals = sorted(
        ((meeting_type, score) for meeting_type, score in scores.items() if meeting_type not in ("general_meeting",)),
        key=lambda item: item[1],
        reverse=True,
    )
    dominant_types = [meeting_type for meeting_type, score in top_signals if score > 0]
    is_mixed = len(dominant_types) >= 2 and top_signals[0][1] - top_signals[1][1] <= 1
    is_long_complex = len(transcript.segments) > 20 or len(text) > 2500
    deployment_hits = sum(1 for word in ("复盘", "部署", "下半年", "上半年", "重点任务", "责任分工", "协同", "工作安排", "任务清单", "整改清单") if word in text)
    has_deployment_pattern = deployment_hits >= 2
    has_explicit_interview = any(marker in text for marker in interview_markers)
    has_explicit_brainstorm = "头脑风暴" in text
    has_explicit_review = any(marker in text for marker in ("今天评审", "本次评审", "评审的是", "方案 A", "方案 B", "最终决定", "拍板"))
    should_use_universal = (
        has_deployment_pattern
        or (is_long_complex and scores["universal_minutes"] >= 1)
        or (is_mixed and best_score <= 2)
    )
    if has_explicit_brainstorm and scores["brainstorming"] >= 2:
        best_type = "brainstorming"
        best_score = max(best_score, scores["brainstorming"])
    elif has_explicit_interview and scores["interview_research"] >= 3:
        best_type = "interview_research"
        best_score = max(best_score, scores["interview_research"])
    elif has_explicit_review and scores["decision_review"] >= 2:
        best_type = "decision_review"
        best_score = max(best_score, scores["decision_review"])
    elif should_use_universal:
        best_type = "universal_minutes"
        best_score = max(best_score, scores["universal_minutes"])
    elif scores["general_meeting"] >= 2 and best_score <= 4:
        best_type = "general_meeting"
        best_score = max(best_score, scores["general_meeting"])

    risk_tags = infer_risk_tags(transcript, text)
    if is_mixed:
        risk_tags.append("mixed_type")
    if best_type == "universal_minutes":
        risk_tags.append("use_universal_template")
    confidence = min(0.95, 0.45 + best_score * 0.08) if best_score else 0.35
    if best_type == "universal_minutes" and is_mixed:
        reason = "会议同时命中多类特征，且没有单一主导类型，使用通用模板归纳。"
    elif best_type == "universal_minutes" and has_deployment_pattern:
        reason = "会议内容较长且同时包含复盘、部署、任务压实等结构，使用通用模板归纳。"
    elif best_score:
        reason = f"命中 {best_score} 个与 {best_type} 相关的关键词。"
    else:
        reason = "未命中明显会议类型特征，使用通用模板归纳。"
    return Classification(
        meeting_type=best_type,
        confidence=round(confidence, 2),
        reason=reason,
        risk_tags=risk_tags,
        template=f"extract_{best_type}",
    )


def infer_risk_tags(transcript: Transcript, text: str) -> list[str]:
    tags: list[str] = []
    speaker_missing_count = sum(1 for segment in transcript.segments if not segment.speaker)
    if speaker_missing_count == len(transcript.segments):
        tags.append("speaker_missing")
    elif speaker_missing_count:
        tags.append("speaker_partial")
    if len(transcript.segments) > 120:
        tags.append("long_context")
    if any(word in text for word in ("可能", "猜测", "先看看", "不确定", "假设")):
        tags.append("hypothesis_heavy")
    if any(word in text for word in ("不同意", "反对", "争议", "分歧")):
        tags.append("conflict_present")
    explicit_no_conclusion_markers = (
        "今天先不定",
        "暂不拍板",
        "不在这次会上拍板",
        "下次评审再定",
        "再决定",
        "待确认",
        "未形成明确结论",
    )
    explicit_conclusion_markers = (
        "最终决策",
        "最终决定",
        "决定",
        "确认",
        "定下来",
        "达成一致",
        "通过方案",
        "采用方案",
        "拍板",
    )
    if any(word in text for word in explicit_no_conclusion_markers):
        tags.append("no_clear_conclusion")
    elif not any(word in text for word in explicit_conclusion_markers):
        tags.append("no_clear_conclusion")
    return tags
