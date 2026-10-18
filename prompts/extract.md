# 结构化抽取

请根据输入的 meeting_type、required_fields、speaker_whitelist 和 segments 生成 JSON。

硬规则：

- 不得编造 seg_id
- 不得编造 owner
- 不得编造 due
- 不得编造结论或共识
- 每个非空字段必须有 evidence
- todos 中每条 task 必须有 evidence

