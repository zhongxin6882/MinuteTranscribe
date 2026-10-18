from __future__ import annotations

import json
import re
from typing import Any

from .llm import LLMClient, LLMError
from .schema import Classification, Segment, Transcript

SYSTEM_PROMPT = """你是会议纪要结构化抽取器。你只能根据输入逐字稿生成内容。
硬规则：
1. 不得编造 speaker、owner、due、数字、结论、待办或 seg_id。
2. owner 只能来自 speaker 白名单；没有明确说话人时 owner 为空字符串。
3. due 只有原文明确时间才可填写，否则为空字符串。
4. 没有明确结论时，必须写“未形成明确结论”或留空，不得写“达成一致”。
5. 输出必须是合法 JSON 对象，不要输出 Markdown、不要输出代码块。
6. 只返回这三个顶层字段：summary, todos, core。
7. core 中只保留有真实证据支撑的信息对象；没有支撑就不要输出。
8. 字符串中不要使用未转义的换行；长内容用中文分号分隔。
"""

REDUCE_SYSTEM_PROMPT = """你是会议纪要汇总器。你只能根据输入的分块抽取结果汇总最终纪要。
硬规则：
1. 不得编造 speaker、owner、due、数字、结论、待办或 seg_id。
2. 只能使用输入里已经出现过的 value 和 evidence；不能凭空补充事实。
3. owner 只能来自 speaker 白名单；没有明确说话人时 owner 为空字符串。
4. due 只有输入明确出现时间才可填写，否则为空字符串。
5. 输出必须是合法 JSON 对象，不要输出 Markdown、不要输出代码块。
6. 只返回这三个顶层字段：summary, todos, core。
7. 允许合并多个分块的同类信息，但 evidence 必须来自输入里已有的 seg_id。
"""

CORE_RECOVERY_SYSTEM_PROMPT = """你是会议纪要核心信息恢复器。首轮模板化抽取结果过空，你需要退回到信息对象层重新提取。
硬规则：
1. 不得编造 speaker、owner、due、数字、结论、待办或 seg_id。
2. 只返回这三个顶层字段：summary, todos, core。
3. 不要返回 fields，不要输出 Markdown，不要输出代码块。
4. core 至少尝试提取 topics、conclusions、open_questions；有明确任务时提取 todos。
5. 如果原文明确说今天不拍板、下次再定，必须输出 no_conclusion，而不是达成一致。
6. 对于 no_conclusion，请尽量直接复用原文里的关键句，不要只做抽象改写。
6. 如果议题较多，请按语义主题归并，不要按发言顺序散列。
7. 没有明确 speaker 的任务可以保留 task 和 due，但 owner 必须留空。
8. 每个对象都必须附带真实存在的 seg_id；没有证据就不要输出该对象。
"""

LONG_CONTEXT_CHAR_THRESHOLD = 12_000
CHUNK_TARGET_CHARS = 6_000
CHUNK_MAX_SEGMENTS = 80
MIN_RECURSIVE_SPLIT_SEGMENTS = 12


def generate_minutes(transcript: Transcript, classification: Classification, llm: LLMClient) -> dict[str, Any]:
    if _should_use_chunked_generation(transcript):
        result = _generate_minutes_chunked(transcript, classification, llm)
    else:
        result = _extract_minutes_once(transcript, classification, llm)
    if _needs_core_recovery(result):
        result = _merge_generation_results(result, derive_transcript_fallback(transcript, classification))
    if _needs_core_recovery(result):
        recovery = _recover_core_minutes(transcript, classification, llm)
        result = _merge_generation_results(result, recovery)
    result = tune_generation_result(result, transcript, classification)
    result["meeting_type"] = classification.meeting_type
    result["classification"] = classification.to_dict()
    return result


def _extract_minutes_once(
    transcript: Transcript,
    classification: Classification,
    llm: LLMClient,
) -> dict[str, Any]:
    prompt = _build_generation_prompt(transcript, classification)
    result = llm.complete_json(SYSTEM_PROMPT, json.dumps(prompt, ensure_ascii=False, indent=2))
    return normalize_generation_result(result)


def _build_generation_prompt(
    transcript: Transcript,
    classification: Classification,
) -> dict[str, Any]:
    return {
        "meeting_id": transcript.meeting_id,
        "meeting_type": classification.meeting_type,
        "risk_tags": classification.risk_tags,
        "speaker_whitelist": sorted(transcript.speaker_whitelist()),
        "extraction_strategy": build_extraction_strategy(classification, transcript),
        "segments": [segment.to_dict() for segment in transcript.segments],
        "output_contract": {
            "summary": "一句话总结，可为空字符串",
            "todos": [
                {
                    "task": "明确待办事项",
                    "owner": "只能来自 speaker_whitelist；没有则为空字符串",
                    "due": "原文明确时间；没有则为空字符串",
                    "extra": "补充限制、备注或期望产出",
                    "evidence": ["真实存在的 seg_id"],
                }
            ],
            "core": {
                "topics": [
                    {
                        "title": "议题标题或主题",
                        "detail": "围绕该议题的关键信息",
                        "evidence": ["真实存在的 seg_id"],
                    }
                ],
                "conclusions": [
                    {
                        "text": "已明确结论；没有明确结论时写未形成明确结论",
                        "status": "confirmed 或 no_conclusion",
                        "evidence": ["真实存在的 seg_id"],
                    }
                ],
                "decisions": [
                    {
                        "question": "需要决策的问题",
                        "decision": "已明确决策；没有则留空字符串",
                        "evidence": ["真实存在的 seg_id"],
                    }
                ],
                "risks": [
                    {
                        "text": "风险、阻塞、约束或不确定性",
                        "level": "原文明确时填写，否则空字符串",
                        "evidence": ["真实存在的 seg_id"],
                    }
                ],
                "open_questions": [
                    {
                        "text": "仍待确认、待验证或未解决的问题",
                        "evidence": ["真实存在的 seg_id"],
                    }
                ],
            },
        },
    }


def _generate_minutes_chunked(
    transcript: Transcript,
    classification: Classification,
    llm: LLMClient,
) -> dict[str, Any]:
    partials = _collect_chunk_results(transcript, classification, llm)
    reduce_prompt = {
        "meeting_id": transcript.meeting_id,
        "meeting_type": classification.meeting_type,
        "speaker_whitelist": sorted(transcript.speaker_whitelist()),
        "extraction_strategy": build_extraction_strategy(classification, transcript),
        "chunk_results": partials,
        "output_contract": {
            "summary": "一句话总结，可为空字符串",
            "todos": [
                {
                    "task": "明确待办事项",
                    "owner": "只能来自 speaker_whitelist；没有则为空字符串",
                    "due": "输入明确出现时间；没有则为空字符串",
                    "extra": "按模板列填写补充信息",
                    "evidence": ["只能使用 chunk_results 中已出现过的 seg_id"],
                }
            ],
            "core": {
                "topics": [
                    {
                        "title": "只能使用 chunk_results 中已有信息",
                        "detail": "只能使用 chunk_results 中已有信息",
                        "evidence": ["只能使用 chunk_results 中已出现过的 seg_id"],
                    }
                ],
                "conclusions": [
                    {
                        "text": "只能使用 chunk_results 中已有信息",
                        "status": "confirmed 或 no_conclusion",
                        "evidence": ["只能使用 chunk_results 中已出现过的 seg_id"],
                    }
                ],
                "decisions": [
                    {
                        "question": "只能使用 chunk_results 中已有信息",
                        "decision": "只能使用 chunk_results 中已有信息",
                        "evidence": ["只能使用 chunk_results 中已出现过的 seg_id"],
                    }
                ],
                "risks": [
                    {
                        "text": "只能使用 chunk_results 中已有信息",
                        "level": "只能使用 chunk_results 中已有信息",
                        "evidence": ["只能使用 chunk_results 中已出现过的 seg_id"],
                    }
                ],
                "open_questions": [
                    {
                        "text": "只能使用 chunk_results 中已有信息",
                        "evidence": ["只能使用 chunk_results 中已出现过的 seg_id"],
                    }
                ],
            },
        },
    }
    reduced = llm.complete_json(REDUCE_SYSTEM_PROMPT, json.dumps(reduce_prompt, ensure_ascii=False, indent=2))
    normalized = normalize_generation_result(reduced)
    normalized["meta"] = {
        **(normalized.get("meta") if isinstance(normalized.get("meta"), dict) else {}),
        "generation_strategy": "chunked_reduce",
        "chunk_count": len(partials),
    }
    return normalized


def _recover_core_minutes(
    transcript: Transcript,
    classification: Classification,
    llm: LLMClient,
) -> dict[str, Any]:
    prompt = {
        "meeting_id": transcript.meeting_id,
        "meeting_type": classification.meeting_type,
        "risk_tags": classification.risk_tags,
        "speaker_whitelist": sorted(transcript.speaker_whitelist()),
        "extraction_strategy": build_extraction_strategy(classification, transcript),
        "segments": [segment.to_dict() for segment in transcript.segments],
        "output_contract": {
            "summary": "一句话总结，可为空字符串",
            "todos": [
                {
                    "task": "明确待办事项",
                    "owner": "只能来自 speaker_whitelist；没有明确 speaker 时留空",
                    "due": "原文明确时间；没有则为空字符串",
                    "extra": "补充限制、备注或期望产出",
                    "evidence": ["真实存在的 seg_id"],
                }
            ],
            "core": {
                "topics": [
                    {"title": "语义归并后的主题", "detail": "该主题下的关键观点/方案/事实", "evidence": ["真实存在的 seg_id"]}
                ],
                "conclusions": [
                    {"text": "已明确结论；没有明确结论时写未形成明确结论", "status": "confirmed 或 no_conclusion", "evidence": ["真实存在的 seg_id"]}
                ],
                "decisions": [
                    {"question": "需要决策的问题", "decision": "明确决策；没有则留空字符串", "evidence": ["真实存在的 seg_id"]}
                ],
                "risks": [
                    {"text": "风险、分歧、约束或阻塞", "level": "原文明确时填写，否则空字符串", "evidence": ["真实存在的 seg_id"]}
                ],
                "open_questions": [
                    {"text": "待确认、待验证或下次再定的问题", "evidence": ["真实存在的 seg_id"]}
                ],
            },
        },
    }
    recovered = llm.complete_json(CORE_RECOVERY_SYSTEM_PROMPT, json.dumps(prompt, ensure_ascii=False, indent=2))
    normalized = normalize_generation_result(recovered if isinstance(recovered, dict) else {})
    normalized["meta"] = {
        **(normalized.get("meta") if isinstance(normalized.get("meta"), dict) else {}),
        "generation_strategy": "core_recovery",
    }
    return normalized


def _collect_chunk_results(
    transcript: Transcript,
    classification: Classification,
    llm: LLMClient,
) -> list[dict[str, Any]]:
    chunks = _split_transcript(transcript)
    partials: list[dict[str, Any]] = []
    for index, chunk in enumerate(chunks, start=1):
        partials.extend(_extract_chunk_recursively(chunk, classification, llm, index))
    return partials


def _extract_chunk_recursively(
    transcript: Transcript,
    classification: Classification,
    llm: LLMClient,
    chunk_index: int,
) -> list[dict[str, Any]]:
    try:
        result = _extract_minutes_once(transcript, classification, llm)
        return [
            {
                "chunk_index": chunk_index,
                "segment_start": transcript.segments[0].seg_id,
                "segment_end": transcript.segments[-1].seg_id,
                "todos": result.get("todos", []),
                "core": result.get("core", {}),
                "summary": str(result.get("summary") or "").strip(),
            }
        ]
    except LLMError:
        if len(transcript.segments) < MIN_RECURSIVE_SPLIT_SEGMENTS:
            raise
        midpoint = len(transcript.segments) // 2
        left = Transcript(meeting_id=transcript.meeting_id, segments=transcript.segments[:midpoint])
        right = Transcript(meeting_id=transcript.meeting_id, segments=transcript.segments[midpoint:])
        return _extract_chunk_recursively(left, classification, llm, chunk_index * 2 - 1) + _extract_chunk_recursively(
            right,
            classification,
            llm,
            chunk_index * 2,
        )


def _split_transcript(transcript: Transcript) -> list[Transcript]:
    chunks: list[Transcript] = []
    bucket: list[Segment] = []
    bucket_chars = 0
    for segment in transcript.segments:
        segment_chars = len(segment.text) + len(segment.cleaned_text)
        should_flush = (
            bucket
            and (
                len(bucket) >= CHUNK_MAX_SEGMENTS
                or bucket_chars + segment_chars > CHUNK_TARGET_CHARS
            )
        )
        if should_flush:
            chunks.append(Transcript(meeting_id=transcript.meeting_id, segments=bucket))
            bucket = []
            bucket_chars = 0
        bucket.append(segment)
        bucket_chars += segment_chars
    if bucket:
        chunks.append(Transcript(meeting_id=transcript.meeting_id, segments=bucket))
    return chunks


def _should_use_chunked_generation(transcript: Transcript) -> bool:
    total_chars = sum(len(segment.text) + len(segment.cleaned_text) for segment in transcript.segments)
    return total_chars > LONG_CONTEXT_CHAR_THRESHOLD or len(transcript.segments) > CHUNK_MAX_SEGMENTS


def _needs_core_recovery(result: dict[str, Any]) -> bool:
    todos = result.get("todos") if isinstance(result.get("todos"), list) else []
    has_todos = any(str(item.get("task") or "").strip() for item in todos if isinstance(item, dict))
    core = result.get("core") if isinstance(result.get("core"), dict) else {}
    topic_count = len(core.get("topics") or []) if isinstance(core.get("topics"), list) else 0
    decision_count = len(core.get("decisions") or []) if isinstance(core.get("decisions"), list) else 0
    risk_count = len(core.get("risks") or []) if isinstance(core.get("risks"), list) else 0
    open_question_count = len(core.get("open_questions") or []) if isinstance(core.get("open_questions"), list) else 0
    return not any((has_todos, topic_count, decision_count, risk_count, open_question_count))


def _merge_generation_results(base: dict[str, Any], recovery: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    if not str(merged.get("summary") or "").strip():
        merged["summary"] = str(recovery.get("summary") or "").strip()
    if not any(str(item.get("task") or "").strip() for item in merged.get("todos") or [] if isinstance(item, dict)):
        merged["todos"] = list(recovery.get("todos") or [])
    base_core = merged.get("core") if isinstance(merged.get("core"), dict) else {}
    recovery_core = recovery.get("core") if isinstance(recovery.get("core"), dict) else {}
    combined_core: dict[str, list[dict[str, Any]]] = {}
    for key in ("topics", "conclusions", "decisions", "risks", "open_questions"):
        existing = base_core.get(key) if isinstance(base_core.get(key), list) else []
        fallback = recovery_core.get(key) if isinstance(recovery_core.get(key), list) else []
        combined_core[key] = existing if existing else fallback
    merged["core"] = combined_core
    merged["meta"] = {
        **(merged.get("meta") if isinstance(merged.get("meta"), dict) else {}),
        "used_core_recovery": True,
    }
    return merged


def normalize_generation_result(result: dict[str, Any]) -> dict[str, Any]:
    todos = result.get("todos")
    if not isinstance(todos, list):
        todos = []

    normalized = dict(result)
    normalized["summary"] = str(result.get("summary") or "").strip()
    normalized["fields"] = {}
    normalized["todos"] = todos
    normalized["core"] = normalize_core_result(result.get("core"))
    return normalized


def build_extraction_strategy(classification: Classification, transcript: Transcript) -> list[str]:
    strategy = [
        "先提取稳定的信息对象：议题、结论、待办、风险、开放问题。",
        "所有信息都必须能回指到 segments 中的真实 seg_id。",
    ]
    tags = set(classification.risk_tags)
    if "mixed_type" in tags or classification.meeting_type == "universal_minutes":
        strategy.append("如果会议包含多个业务方向或议题，请按语义主题归并，不要按发言先后顺序机械罗列。")
    if "no_clear_conclusion" in tags:
        strategy.append("如果原文明确表示今天不拍板、下次再定或仅列问题，请在 core.conclusions 中保留 no_conclusion 项，不要伪造共识。")
    if "speaker_missing" in tags or "speaker_partial" in tags:
        strategy.append("没有明确 speaker 的任务可以保留 task 和 due，但 owner 必须留空。")
    if "conflict_present" in tags:
        strategy.append("存在反对意见或分歧时，要保留分歧点和保留意见，不要把冲突总结成达成一致。")
    if len(transcript.segments) > 20:
        strategy.append("长会优先保留跨段出现的重点议题、风险和待办，避免只覆盖前半段内容。")
    return strategy


def tune_generation_result(
    result: dict[str, Any],
    transcript: Transcript,
    classification: Classification,
) -> dict[str, Any]:
    tuned = dict(result)
    core = tuned.get("core") if isinstance(tuned.get("core"), dict) else {}
    todos = tuned.get("todos") if isinstance(tuned.get("todos"), list) else []
    tags = set(classification.risk_tags)
    transcript_fallback = derive_transcript_fallback(transcript, classification)

    if "speaker_missing" in tags:
        for item in todos:
            if isinstance(item, dict):
                item["owner"] = ""
    if "speaker_partial" in tags:
        speaker_whitelist = transcript.speaker_whitelist()
        for item in todos:
            if isinstance(item, dict) and str(item.get("owner") or "").strip() not in speaker_whitelist:
                item["owner"] = ""

    if "no_clear_conclusion" in tags and isinstance(core, dict):
        conclusions = core.get("conclusions") if isinstance(core.get("conclusions"), list) else []
        has_no_conclusion = any(
            isinstance(item, dict) and (
                str(item.get("status") or "").strip() == "no_conclusion"
                or "未形成明确结论" in str(item.get("text") or "")
            )
            for item in conclusions
        )
        fallback = derive_no_conclusion_item(transcript)
        if fallback:
            if not has_no_conclusion:
                conclusions.append(fallback)
            elif not any(
                isinstance(item, dict) and str(item.get("text") or "").strip() == fallback["text"]
                for item in conclusions
            ):
                conclusions.insert(0, fallback)
            core["conclusions"] = conclusions

        open_questions = core.get("open_questions") if isinstance(core.get("open_questions"), list) else []
        for fallback_question in derive_open_question_items(transcript):
            if not any(
                isinstance(item, dict) and str(item.get("text") or "").strip() == fallback_question["text"]
                for item in open_questions
            ):
                open_questions.insert(0, fallback_question)
        core["open_questions"] = dedupe_core_items(open_questions, ("text",))

    for key, identity_fields in (
        ("topics", ("title", "detail")),
        ("conclusions", ("text", "status")),
        ("decisions", ("question", "decision")),
        ("risks", ("text", "level")),
        ("open_questions", ("text",)),
    ):
        merged_items = list(core.get(key) or []) if isinstance(core.get(key), list) else []
        fallback_items = transcript_fallback["core"].get(key) if isinstance(transcript_fallback["core"], dict) else []
        for fallback_item in fallback_items if isinstance(fallback_items, list) else []:
            if not any(isinstance(item, dict) and item == fallback_item for item in merged_items):
                merged_items.append(fallback_item)
        core[key] = dedupe_core_items(merged_items, identity_fields)

    todos = merge_todo_items(todos, transcript_fallback["todos"])

    tuned["core"] = core
    tuned["todos"] = todos
    return tuned


def derive_no_conclusion_item(transcript: Transcript) -> dict[str, Any] | None:
    markers = (
        "今天先不定",
        "暂不拍板",
        "不在这次会上拍板",
        "下次评审再定",
        "再决定",
        "待确认",
        "先把问题列清",
    )
    for segment in transcript.segments:
        text = str(segment.cleaned_text or segment.text or "").strip()
        if any(marker in text for marker in markers):
            return {
                "text": text,
                "status": "no_conclusion",
                "evidence": [segment.seg_id],
            }
    return None


def derive_open_question_items(transcript: Transcript) -> list[dict[str, Any]]:
    prioritized_markers = (
        ("还是", "再决定"),
        ("待", "后再定"),
        ("等", "再决定"),
        ("是否",),
        ("哪个",),
    )
    fallback_markers = (
        "待确认",
        "待补充数据",
        "后续再定",
        "下周再定",
        "暂时没有结论",
    )
    items: list[dict[str, Any]] = []
    for segment in transcript.segments:
        text = str(segment.cleaned_text or segment.text or "").strip()
        if not text:
            continue
        if any(all(marker in text for marker in marker_group) for marker_group in prioritized_markers) or any(
            marker in text for marker in fallback_markers
        ):
            items.append({"text": text, "evidence": [segment.seg_id]})
    return dedupe_core_items(items, ("text",))


def derive_transcript_fallback(transcript: Transcript, classification: Classification) -> dict[str, Any]:
    tags = set(classification.risk_tags)
    topics: list[dict[str, Any]] = []
    conclusions: list[dict[str, Any]] = []
    risks: list[dict[str, Any]] = []
    open_questions = derive_open_question_items(transcript)
    todos = derive_todo_items(transcript)

    topic_markers = (
        "主要讨论",
        "会议主题",
        "会议的主题",
        "主要目标",
        "当前现状",
        "目前掌握的现状",
        "下面进入问题讨论",
        "阶段性方案",
        "重点工作",
        "最大的问题",
        "交付问题",
        "回到市场",
        "人效来看",
        "风控检查",
    )
    risk_markers = ("风险点", "风险", "漏洞", "偏慢", "不足", "滞后", "不稳定", "晚了一周", "拖着不动")
    conclusion_markers = (
        "纪要要",
        "不要凭空写负责人",
        "已经确认",
        "统一由项目组跟进",
        "形成一个阶段性方案",
        "今天的结论",
        "可以概括成一句话",
        "今天不直接拍板",
    )

    for segment in transcript.segments:
        text = str(segment.cleaned_text or segment.text or "").strip()
        if not text:
            continue
        if any(marker in text for marker in topic_markers):
            topics.append({"title": summarize_topic_title(text), "detail": text, "evidence": [segment.seg_id]})
        if any(marker in text for marker in risk_markers):
            risks.append({"text": text, "level": "", "evidence": [segment.seg_id]})
        if any(marker in text for marker in conclusion_markers):
            conclusions.append({"text": text, "status": "confirmed", "evidence": [segment.seg_id]})

    no_conclusion_item = derive_no_conclusion_item(transcript)
    if no_conclusion_item:
        conclusions.append(no_conclusion_item)

    if "speaker_missing" in tags and not any("不要凭空写负责人" in str(item.get("text") or "") for item in conclusions):
        for segment in transcript.segments:
            text = str(segment.cleaned_text or segment.text or "").strip()
            if "不要凭空写负责人" in text:
                conclusions.append({"text": text, "status": "confirmed", "evidence": [segment.seg_id]})

    return {
        "core": {
            "topics": dedupe_core_items(topics, ("title", "detail")),
            "conclusions": dedupe_core_items(conclusions, ("text", "status")),
            "decisions": [],
            "risks": dedupe_core_items(risks, ("text", "level")),
            "open_questions": open_questions,
        },
        "todos": todos,
    }


def derive_todo_items(transcript: Transcript) -> list[dict[str, Any]]:
    time_pattern = re.compile(
        r"(下周[一二三四五六日天][^，。；]{0,10}?前|本周[一二三四五六日天][^，。；]{0,10}?前|月底前|\d+\s*月\s*\d+\s*日(?:前)?)"
    )
    action_markers = ("完成", "出", "补齐", "整理", "拉清单", "确定", "同步", "改版", "整改", "跟进", "给出", "约好", "补齐")
    items: list[dict[str, Any]] = []

    for segment in transcript.segments:
        text = str(segment.cleaned_text or segment.text or "").strip()
        if not text:
            continue
        clauses = [clause.strip(" ，。；") for clause in re.split(r"[，；]", text) if clause.strip(" ，。；")]
        pending_due = ""
        for clause in clauses:
            due_match = time_pattern.search(clause)
            due = due_match.group(1) if due_match else pending_due
            has_action = any(marker in clause for marker in action_markers)
            if due_match and not has_action:
                pending_due = due_match.group(1)
                continue
            if not due or not has_action:
                continue
            task = clause.replace(due_match.group(1), "", 1).strip() if due_match else clause.strip()
            task = re.sub(r"^(第一项待办|第二项待办|第三项待办|第四项待办|已经确认|确认|要把|需要|请|由|项目条线|市场条线|人事|运营负责人|产品经理|研发负责人|我来负责|我负责)", "", task).strip()
            if task.startswith("前"):
                task = task[1:].strip()
            task = re.sub(r"^(在|于)", "", task).strip()
            if not task:
                task = clause
            items.append(
                {
                    "task": task,
                    "owner": "",
                    "due": due,
                    "extra": "",
                    "evidence": [segment.seg_id],
                }
            )
            pending_due = due
    return dedupe_todo_items(items)


def summarize_topic_title(text: str) -> str:
    for marker in ("主要讨论", "最大的问题是", "重点工作", "交付问题", "回到市场"):
        if marker in text:
            tail = text.split(marker, 1)[-1].strip(" ，。")
            return tail[:16] or "会议议题"
    return text[:16] or "会议议题"


def dedupe_todo_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, tuple[str, ...]]] = set()
    for item in items:
        task = str(item.get("task") or "").strip()
        due = str(item.get("due") or "").strip()
        evidence = tuple(str(seg_id) for seg_id in item.get("evidence") or [])
        key = (task, due, evidence)
        if not task or not evidence or key in seen:
            continue
        seen.add(key)
        deduped.append(
            {
                "task": task,
                "owner": str(item.get("owner") or "").strip(),
                "due": due,
                "extra": str(item.get("extra") or "").strip(),
                "evidence": list(evidence),
            }
        )
    return deduped


def merge_todo_items(existing: list[dict[str, Any]], fallback: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = dedupe_todo_items(existing)
    existing_signatures = {
        (
            str(item.get("due") or "").strip(),
            tuple(str(seg_id) for seg_id in item.get("evidence") or []),
            str(item.get("task") or "").strip(),
        )
        for item in merged
        if isinstance(item, dict)
    }
    for item in fallback:
        if not isinstance(item, dict):
            continue
        signature = (
            str(item.get("due") or "").strip(),
            tuple(str(seg_id) for seg_id in item.get("evidence") or []),
            str(item.get("task") or "").strip(),
        )
        if signature in existing_signatures:
            continue
        merged.append(item)
    return dedupe_todo_items(merged)


def _contains_any_no_conclusion_marker(text: str) -> bool:
    markers = (
        "今天先不定",
        "暂不拍板",
        "不在这次会上拍板",
        "下次评审再定",
        "再决定",
        "待确认",
        "先把问题列清",
    )
    return any(marker in text for marker in markers)


def normalize_core_result(
    raw_core: Any,
) -> dict[str, list[dict[str, Any]]]:
    if isinstance(raw_core, dict):
        return {
            "topics": _normalize_core_topic_items(raw_core.get("topics")),
            "conclusions": _normalize_core_conclusion_items(raw_core.get("conclusions")),
            "decisions": _normalize_core_decision_items(raw_core.get("decisions")),
            "risks": _normalize_core_risk_items(raw_core.get("risks")),
            "open_questions": _normalize_core_open_question_items(raw_core.get("open_questions")),
        }
    return {key: [] for key in ("topics", "conclusions", "decisions", "risks", "open_questions")}


def dedupe_core_items(items: list[dict[str, Any]], identity_fields: tuple[str, ...]) -> list[dict[str, Any]]:
    merged: dict[tuple[str, ...], dict[str, Any]] = {}
    for item in items:
        key = tuple(str(item.get(field) or "").strip() for field in identity_fields)
        if not any(key):
            continue
        if key not in merged:
            merged[key] = {**item, "evidence": list(item.get("evidence") or [])}
            continue
        existing = merged[key]
        combined = []
        for seg_id in list(existing.get("evidence") or []) + list(item.get("evidence") or []):
            if seg_id not in combined:
                combined.append(seg_id)
        existing["evidence"] = combined
    return list(merged.values())


def _normalize_core_topic_items(value: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        items.append(
            {
                "title": str(item.get("title") or item.get("topic") or "").strip(),
                "detail": str(item.get("detail") or item.get("text") or "").strip(),
                "evidence": item.get("evidence") if isinstance(item.get("evidence"), list) else [],
            }
        )
    return dedupe_core_items(items, ("title", "detail"))


def _normalize_core_conclusion_items(value: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "").strip() or "confirmed"
        if status not in {"confirmed", "no_conclusion"}:
            status = "confirmed"
        items.append(
            {
                "text": str(item.get("text") or item.get("value") or "").strip(),
                "status": status,
                "evidence": item.get("evidence") if isinstance(item.get("evidence"), list) else [],
            }
        )
    return dedupe_core_items(items, ("text", "status"))


def _normalize_core_decision_items(value: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        items.append(
            {
                "question": str(item.get("question") or "").strip(),
                "decision": str(item.get("decision") or item.get("text") or "").strip(),
                "evidence": item.get("evidence") if isinstance(item.get("evidence"), list) else [],
            }
        )
    return dedupe_core_items(items, ("question", "decision"))


def _normalize_core_risk_items(value: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        items.append(
            {
                "text": str(item.get("text") or item.get("detail") or "").strip(),
                "level": str(item.get("level") or "").strip(),
                "evidence": item.get("evidence") if isinstance(item.get("evidence"), list) else [],
            }
        )
    return dedupe_core_items(items, ("text", "level"))


def _normalize_core_open_question_items(value: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        items.append(
            {
                "text": str(item.get("text") or item.get("question") or "").strip(),
                "evidence": item.get("evidence") if isinstance(item.get("evidence"), list) else [],
            }
        )
    return dedupe_core_items(items, ("text",))
