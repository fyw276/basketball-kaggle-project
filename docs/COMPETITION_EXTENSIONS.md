# 竞赛/课题扩展清单（多智能体 · 记忆 · 数据飞轮）

本文档与 README「竞赛/课题扩展方向」对应：**已完成交付**与**可选下一步**分开列出。

## 2026-04-13 已落地（代码与文档）

| 项 | 说明 |
|----|------|
| CLI 与 API Envelope | `cli/outfit_cli.py` 成功响应解包 `{success,data}` |
| MCP 与 Envelope | `mcp/server.py` 同上 |
| CLI 扩展 | `feedback-create`、`analytics-summary`、`agent-intent`、`memory-add`、`memory-search` 等 |
| MCP 扩展 | `submit_feedback`、`get_analytics_summary`、`route_agent_intent`、`add_memory_snippet`、`search_memory_snippets` |
| 反馈入库 + 重排 | `FeedbackEvent` 表；`POST /api/v1/feedback/events`；场景搭配 `OutfitRecommender3D` 对 `like/adopt` 与风格加权微调 `overall_score` |
| 数据飞轮 | `GET /api/v1/analytics/summary`（`positive_feedback_rate`、`collection_rate_proxy`）；`scripts/export_feedback_jsonl.py` |
| 薄意图路由 | `POST /api/v1/agent/intent`（关键词规则 → 建议 MCP 工具名） |
| 轻量 RAG | `MemorySnippet` + `GET /memory/snippets/search`（Jaccard 式关键词重叠）；`embedding_json` 预留向量 |
| 文档 | `README.md`、`backend/API_EXAMPLES.md`、本文档 |

## 多智能体架构（驾驭工程）

| 状态 | 内容 |
|------|------|
| **已有** | MCP 多工具；`route_agent_intent` + `route_intent_rules`；Host 动态选工具 |
| **可选** | 更细粒度规则 / 小分类模型；申报材料中附 **Cursor 选工具录屏** |

## 自我进化 / 记忆

| 状态 | 内容 |
|------|------|
| **已有** | 反馈事件驱动推荐重排；记忆片段 + 关键词检索 |
| **可选** | `embedding_json` 接 sentence-transformers + pgvector；Redis 会话摘要 |

## 底层数据飞轮

| 状态 | 内容 |
|------|------|
| **已有** | 汇总指标 API；JSONL 导出脚本 |
| **可选** | 定时任务打标签；离线训练/重排流水线 |

## 答辩/申报可用的一句话

本项目将穿搭决策 **API 化 + MCP/CLI 工具化**，并提供 **反馈闭环与轻量分析指标**；意图路由与记忆检索支撑 **Agent 动态编排** 叙事，数据可通过 **JSONL 导出** 进入下一轮评估与迭代。
