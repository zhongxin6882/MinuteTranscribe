# 会议纪要转写

逐字稿到结构化会议纪要的本地产品原型。

## 当前范围

- 同时提供命令行和本地 Web/HTML 输出
- 支持两类输入：
  - 标准 JSON transcript
  - 原始逐字稿文本
- 保留两层文本：
  - 原始逐字稿
  - cleaned version
- 自动判定会议类型
- 类型不明确、因素较多、长会内容默认可退到通用模板
- 最终纪要严格使用会议类型模板输出
- 第一版先输出纪要文本，不做 evidence 点击高亮交互
- 直接接真实模型
- 支持邮箱注册 / 登录，纪要与模型配置按用户隔离
- 测试数据先使用仓库内构造样例

## 目标流程

`输入 -> 清洗/润色 -> 分类 -> 模板选择 -> 生成 -> 校验 -> 导出`

## 模型配置

第一版直接接真实模型，不提供 mock 生成。模型不固定，通过环境变量配置：

```bash
export MINUTES_LLM_PROVIDER=openai_compatible
export MINUTES_LLM_MODEL=your-model-name
export MINUTES_LLM_BASE_URL=https://api.openai.com/v1
export MINUTES_LLM_API_KEY=your-api-key
```

Anthropic 示例：

```bash
export MINUTES_LLM_PROVIDER=anthropic
export MINUTES_LLM_MODEL=claude-haiku-4-5
export MINUTES_LLM_API_KEY=your-api-key
```

运行：

```bash
python3 -m src.pipeline evals/dataset/project_sync_001.json -o out/project_sync_001

也支持在本地页面里直接配置模型。页面填写的配置会保存在仓库根目录的 `.minutes.config.json`，模型调用仍由服务端执行。

启动本地页面：

```bash
python3 -m src.server
```

然后打开：

```text
http://127.0.0.1:8000
```

首次打开后需要先注册或登录邮箱账号。登录后：

- 会议纪要按用户隔离保存到 `data/minutes/<user_id>/`
- 模型配置按用户隔离保存到 `data/configs/<user_id>/config.json`
- 账号和会话信息保存在 `data/auth/`

如果 8000 端口不可用，可以指定端口：

```bash
python3 -m src.server 8010
```

然后访问：

```text
http://127.0.0.1:8010
```

## 真实模型稳定性测试

在本机已配置真实模型后，可运行：

```bash
python3 -B evals/run_real_model_smoke.py
```

输出结果会写到：

```text
evals/results/real-model-smoke-<timestamp>.md
evals/results/real-model-smoke-<timestamp>.json
```
```

## 目录

- `docs/`: 产品和技术文档
- `src/`: Python pipeline
- `prompts/`: 模型提示词模板
- `evals/dataset/`: 构造测试数据
- `web/`: 本地 HTML 模板与导出文件
