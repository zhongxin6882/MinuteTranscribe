# 当前产品测试集｜会议纪要生成

基于外部 `evals/README.md` 的目标，这份测试集面向当前版本产品，覆盖：

- 正常会议：8 场
- 无结论会议：4 场
- 标签缺失：3 场
- 多议题穿插：3 场
- 超长会议：2 场

总计：20 场

这份测试集优先服务当前产品迭代验证，不要求所有 case 立即有完整自动评测脚本，但每场都给出：

- `case_id`
- `输入来源`
- `预期模板/类型`
- `关键风险`
- `核心断言`

## 使用说明

1. 对已有 `evals/dataset/` 文件，直接跑当前产品。
2. 对未创建的 case，按本文件的构造要求补 transcript。
3. 每次产品改动后，至少回归：
   - 1 场正常会议
   - 1 场无结论会议
   - 1 场标签缺失
   - 1 场多议题穿插
   - 1 场超长会议
4. 当前版本优先检查：
   - 是否稳定输出
   - 是否正确退到 `universal_minutes`
   - 是否出现 JSON 解析失败

## 一、正常会议（8 场）

### 1. `project_sync_001`
- 输入来源：`evals/dataset/project_sync_001.json`
- 预期模板：`project_sync`
- 关键风险：基础抽取、待办 owner/due 识别
- 核心断言：
  - 应抽出项目阶段、阻塞、下一步计划
  - `王珊` 和 `赵强` 的待办不可丢
  - `明天下午六点前`、`周五前` 不可写错

### 2. `project_sync_002`
- 输入来源：`evals/dataset/project_sync_002.json`
- 预期模板：`project_sync`
- 关键风险：项目类模板稳定性
- 核心断言：
  - 输出不应退化为通用模板
  - 待办至少召回 1 条明确任务

### 3. `decision_review_001`
- 输入来源：`evals/dataset/decision_review_001.json`
- 预期模板：`decision_review`
- 关键风险：多方案取舍、反对意见保留
- 核心断言：
  - 必须体现方案 A / B 的取舍
  - `最终决策是采用方案 B` 必须保留
  - 不能把周洋的反对意见丢掉

### 4. `decision_review_002`
- 输入来源：`evals/dataset/decision_review_002.json`
- 预期模板：`decision_review`
- 关键风险：结论与待办分离
- 核心断言：
  - 已拍板内容进入“结论”
  - 后续验证项进入“待办”

### 5. `issue_triage_001`
- 输入来源：`evals/dataset/issue_triage_001.txt`
- 预期模板：`issue_triage`
- 关键风险：假设与结论混淆
- 核心断言：
  - `可能原因` 不能写成最终原因
  - `今天下班前检查 render.py` 必须作为待办保留

### 6. `issue_triage_002`
- 输入来源：`evals/dataset/issue_triage_002.json`
- 预期模板：`issue_triage`
- 关键风险：问题定性与排查动作映射
- 核心断言：
  - 至少有 1 条“处理路径”
  - 不得漏掉排查协作方

### 7. `interview_research_001`
- 输入来源：`evals/dataset/interview_research_001.json`
- 预期模板：`interview_research`
- 关键风险：用户观点与产品结论混淆
- 核心断言：
  - `检索结果太多`、`希望看到产品版本和生效时间` 必须保留
  - 不应强行生成产品内部 owner

### 8. `general_meeting_001`
- 输入来源：`evals/dataset/general_meeting_001.json`
- 预期模板：`general_meeting`
- 关键风险：一般同步会的宽模板适配
- 核心断言：
  - 能覆盖“进展、重点信息、待确认问题”
  - `7 月 25 日前给出排期建议` 需进入待办

## 二、无结论会议（4 场）

### 9. `brainstorming_001`
- 输入来源：`evals/dataset/brainstorming_001.json`
- 预期模板：`brainstorming`
- 关键风险：无结论时编共识
- 核心断言：
  - 必须体现“今天先不定最终方案”
  - 不能把讨论写成已拍板
  - 仅保留明确的试验性待办

### 10. `brainstorming_002`
- 输入来源：待新增
- 构造要点：
  - 主题为“新人 onboarding AI 任务卡设计”
  - 至少 3 个方向、2 处明显分歧
  - 结尾明确“今天不定方案，下周再看数据”
- 预期模板：`brainstorming`
- 核心断言：
  - 输出应以观点和开放问题为主
  - 不得生成“达成一致”

### 11. `general_no_conclusion_001`
- 输入来源：待新增
- 构造要点：
  - 普通讨论会
  - 大量问题暴露，但无人拍板
  - 没有 owner，没有 due
- 预期模板：`general_meeting` 或 `universal_minutes`
- 核心断言：
  - 必须写“暂未确定的问题”
  - 不得硬造待办

### 12. `decision_review_no_conclusion_001`
- 输入来源：待新增
- 构造要点：
  - 两个方案都有人支持
  - 最后明确“先补数据，下次评审”
- 预期模板：`decision_review`
- 核心断言：
  - 不能写“最终决策”
  - 可以保留“待验证问题”与后续动作

## 三、标签缺失（3 场）

### 13. `speaker_missing_all_001`
- 输入来源：待新增
- 构造要点：
  - 全部 `speaker = null`
  - 内容中存在明确任务和时间
- 预期模板：`universal_minutes` 或匹配类型模板
- 核心断言：
  - 待办可以有 `task`
  - `owner` 必须全部留空
  - 不得猜负责人

### 14. `speaker_missing_partial_001`
- 输入来源：待新增
- 构造要点：
  - 半数段落有 speaker，半数无
  - 其中 1 条任务来自无 speaker 段
- 预期模板：匹配类型模板
- 核心断言：
  - 有 speaker 的待办可正常归属
  - 无 speaker 的待办 owner 必须留空

### 15. `speaker_missing_partial_002`
- 输入来源：待新增
- 构造要点：
  - 复盘部署类会议
  - 多个待办中只有部分能识别 owner
- 预期模板：`universal_minutes`
- 核心断言：
  - 不能把上一句 speaker 套用到下一段无 speaker 内容上

## 四、多议题穿插（3 场）

### 16. `interleaved_topics_001`
- 输入来源：待新增
- 构造要点：
  - 讨论 A 项目进度
  - 插入 B 项目预算
  - 再回到 A 项目风险
- 预期模板：`project_sync` 或 `universal_minutes`
- 核心断言：
  - A 相关内容应语义归并
  - 不应被按时间切成 3 个孤立主题

### 17. `interleaved_topics_002`
- 输入来源：待新增
- 构造要点：
  - 产品需求评审中，交替讨论“首页推荐”与“检索排序”
- 预期模板：`decision_review`
- 核心断言：
  - 两个议题分别保留各自结论
  - 不要把 A 的结论写到 B 下

### 18. `interleaved_topics_003`
- 输入来源：待新增
- 构造要点：
  - 经营复盘会中，市场、项目、人效、风控来回切换
- 预期模板：`universal_minutes`
- 核心断言：
  - 应稳定走通用模板
  - 输出需按“进展 / 问题 / 部署 / 待办”整理，而不是按原文跳跃顺序散列

## 五、超长会议（2 场）

### 19. `long_meeting_001`
- 输入来源：待新增
- 构造要点：
  - 约 2.5 万到 3 万字
  - 首段埋 1 条待办，中段埋 2 条待办，尾段埋 1 条待办
  - 复盘 + 部署混合
- 预期模板：`universal_minutes`
- 核心断言：
  - 首 / 中 / 尾待办全部召回
  - 不出现 JSON 解析失败

### 20. `long_meeting_002`
- 输入来源：待新增
- 构造要点：
  - 长项目群同步会
  - 多个项目、多个负责人、多个时间节点
- 预期模板：`project_sync` 或 `universal_minutes`
- 核心断言：
  - 不丢中后段待办
  - 不混淆 owner / due

## 六、当前版本优先回归清单（最小必跑）

每次改动至少跑这 6 场：

1. `project_sync_001`
2. `decision_review_001`
3. `brainstorming_001`
4. `speaker_missing_all_001`
5. `interleaved_topics_003`
6. `long_meeting_001`

## 七、当前产品的重点观察项

针对当前版本，不只看“内容对不对”，还要重点看：

- 是否还会频繁出现非法 JSON
- 是否能稳定落到 `universal_minutes`
- 输出区是否渲染成标准文档样式
- 长文时是否出现空模板
- 复杂会议是否仍被误判成窄模板

## 八、建议补充文件

建议后续新增：

- `evals/gold/`：每场 case 的期望输出摘要与待办 gold
- `evals/judges/consensus_judge.md`
- `evals/manifest.json`：机器可读的 case 清单

当前这份文档先作为手工测试与后续自动评测的基线。
