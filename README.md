# AI 驱动的竞品分析 Agent 协作系统

一个面向实习项目演示的最小可运行版本。系统模拟真实数字调研小组，将竞品分析拆成采集、清洗、分析、报告、质检五个 Agent，并保留每一步的输入、输出、证据和日志。

## 你可以展示什么

- 输入行业和 3-5 个竞品名称，生成结构化竞品分析报告。
- 查看 Agent DAG 工作流，理解每个 Agent 的职责和任务依赖。
- 查看每条结论对应的证据来源，体现可追溯能力。
- 查看质检 Agent 给出的缺失来源、低置信度和风险提示。
- 查看完整运行日志，说明系统不是一次性生成文本，而是多 Agent 协作完成。
- 可选启用真实网页搜索、网页抓取和正文抽取；网络失败时会降级到演示数据。
- 可选接入你自己的大模型 API，让画像和报告由 LLM 基于证据生成。

## 快速开始

```bash
python3 app.py
```

然后打开：

```text
http://127.0.0.1:8000
```

默认示例场景是“AI 笔记工具”，竞品为 Notion AI、Mem、Reflect、Evernote AI。

如果要尝试实时网页采集，在页面中勾选“启用真实网页搜索、抓取和正文抽取”。该模式使用 Python 标准库请求 DuckDuckGo HTML 搜索页并抽取候选网页正文，不需要额外安装依赖。

如果要启用大模型增强，配置你自己的 OpenAI-compatible API。支持 Chat Completions 和 Responses 两种格式：

```bash
export LLM_API_URL="https://你的服务地址/v1/chat/completions"
export LLM_API_KEY="你的 key，如果本地服务不需要鉴权可不填"
export LLM_MODEL="你的模型名"
export LLM_API_FORMAT="chat"
python3 app.py
```

如果你的服务是 Responses 风格接口：

```bash
export LLM_API_URL="https://你的服务地址/v1/responses"
export LLM_API_FORMAT="responses"
python3 app.py
```

如果 URL 包含 `chat/completions`，系统会自动按 `chat` 格式调用；否则默认按 `responses` 格式调用。

也可以参考 `.env.example`。如果你的模型服务不需要鉴权，`LLM_API_KEY` 可以留空；如果你的服务要求其他鉴权方式，需要在 `competitor_agents/llm_client.py` 里调整请求头。

如果你不想每次在终端里 `export`，可以复制本地配置文件：

```bash
cp config.local.example.json config.local.json
```

然后编辑 `config.local.json`，填入你自己的 API 地址、Key 和模型名。`config.local.json` 已加入 `.gitignore`，不会上传到 GitHub。

## 项目结构

```text
.
├── app.py                         # 本地 Web 服务和 API
├── competitor_agents/             # 多 Agent 流水线核心代码
├── data/demo_sources.json         # 演示用公开信息样例库
├── docs/                          # 架构、Schema、答辩材料
├── static/                        # 前端页面
└── tests/                         # 单元测试
```

## Agent 分工

- 采集 Agent：从演示源库中匹配竞品公开信息，缺失时生成待补充记录。
- 实时采集增强：可从搜索结果中抓取公开网页并抽取正文，无法访问时自动降级。
- 清洗 Agent：去重、规范化字段、按竞品知识 Schema 整理证据。
- 分析 Agent：比较功能、定位、价格、目标用户、风险和差异化。
- 分析 Agent：有 API Key 时调用大模型生成结构化画像，否则使用规则兜底。
- 报告撰写 Agent：有 API Key 时调用大模型生成 Markdown 报告，否则使用模板兜底。
- 质检/溯源 Agent：检查关键结论是否有证据、是否存在缺失或低置信度。

## 适合面试讲解的亮点

1. 不是简单 prompt，而是有明确角色分工的 Agent 协作系统。
2. 每个结论都绑定证据 ID，可追踪到来源、摘录和可信度。
3. 工作流是 DAG，可以解释任务依赖和失败降级策略。
4. 代码没有依赖重型框架，适合作为第一版 MVP 继续扩展到 LangGraph、真实爬虫、数据库和 LLM。

## 后续可扩展方向

- 接入更多搜索源、反爬处理、robots 策略和正文抽取质量评估。
- 接入大模型，让分析 Agent 和报告 Agent 生成更自然的洞察。
- 使用 SQLite/Postgres 保存多次运行结果。
- 使用 LangGraph 表达更复杂的 DAG、重试、人工审核和并行分支。
- 增加 PDF/Word 导出，形成正式商业分析交付物。
