# SPEC｜会议纪要生成

## 产品输入

- 支持 `JSON transcript`
- 支持原始逐字稿文本粘贴或文件输入
- 系统内部统一转换为 `segments` 结构

```json
{
  "meeting_id": "m001",
  "segments": [
    { "seg_id": "s001", "speaker": "张三", "start": "00:01:23", "text": "..." }
  ]
}
```

## 处理流程

1. 原始输入接收
2. 文本清洗与 cleaned version 生成
3. 自动会议类型判定
4. 按类型选择模板
5. 结构化生成
6. 规则校验
7. 导出纪要文本和 HTML

## 会议类型

- `project_sync`
- `decision_review`
- `issue_triage`
- `brainstorming`
- `interview_research`
- `universal_minutes`
- `general_meeting`

## 输出要求

- 最终用户输出严格按会议类型模板渲染
- 纪要必须包含：
  - `议题`
  - `结论`
  - `待办`
- 系统内部保存结构化 JSON，便于校验和后续扩展

## 规则约束

- 不允许编造结论、待办、时间、数字、owner
- `owner` 只能来自输入里实际出现过的 speaker
- `due` 只能来自原文明确时间
- 无结论议题不能写成“已达成一致”
- 校验失败的条目必须删除或降级
