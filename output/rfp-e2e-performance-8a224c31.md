# DealFlow RFP 全链路耗时测试

- 测试时间：2026-09-21（日志时间为 UTC）
- 输入文件：`output/pdf/enterprise_10k_v1/rfp/beichen-energy-dedicated-rfp.pdf`
- 文件大小：157,518 bytes
- PDF 页数：6
- RFP ID：`8a224c31-c5e7-46bf-9968-aec1e406b8e2`
- Workflow Run ID：`3490fd1e-e14e-4b30-b505-167e79f3bcc8`
- Proposal ID：`abb2fe1c-588d-4d4a-baa0-95924dc6f539`
- 最终状态：`REVIEW_PENDING / human_review`
- 输出：76 Requirements、76 Capability Results、1 Proposal、40,618 字符 Markdown

## 端到端结果

API 业务记录创建于 `12:34:56.984533Z`，Proposal 落库完成于
`13:03:04.868856Z`，端到端耗时 **1,687.884 秒（28 分 07.884 秒）**。
HTTP 上传请求本身耗时 0.067 秒并返回 `202 Accepted`。

| 阶段 | 起止依据 | 耗时 | 端到端占比 |
| --- | --- | ---: | ---: |
| API 接收至开始处理 | RFP created → processing_started | 0.196 秒 | 0.01% |
| PDF 解析 | processing_started → rfp_document_parsed | 6.509 秒 | 0.39% |
| 解析至需求 LLM 启动 | parsed → extract LLM started | 0.417 秒 | 0.02% |
| Requirement 抽取 | extract LLM started → requirements_extracted | 81.160 秒 | 4.81% |
| Capability 评估 | requirements_extracted → capabilities_evaluated | 826.816 秒（13 分 46.816 秒） | 48.99% |
| Proposal 生成 | proposal LLM started → proposal_generated | 772.717 秒（12 分 52.717 秒） | 45.78% |

## LLM 调用统计

| 操作 | 调用数 | LLM 总耗时 | 平均 | P95 | 最大 | Prompt tokens | Completion tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Requirement extraction | 1 | 76.691 秒 | 76.691 秒 | 76.691 秒 | 76.691 秒 | 2,964 | 11,139 |
| Capability judgment | 76 | 762.712 秒 | 10.036 秒 | 18.654 秒 | 23.867 秒 | 276,791 | 27,949 |
| Proposal batches | 11 | 643.800 秒 | 58.527 秒 | 161.559 秒 | 161.559 秒 | 96,902 | 27,941 |
| Proposal sections | 1 | 91.223 秒 | 91.223 秒 | 91.223 秒 | 91.223 秒 | 22,563 | 3,697 |

全部 LLM 调用累计 **1,574.426 秒（26 分 14.426 秒）**，约占端到端耗时的
**93.28%**。总计使用 399,220 prompt tokens、70,726 completion tokens，合计
469,946 tokens。

## 观测到的问题

1. Capability 对 76 条 Requirement 逐条串行调用 LLM，单阶段耗时 13 分 46.816 秒，
   是最大瓶颈。LLM 累计耗时 762.712 秒，其余约 64.104 秒用于初始 Embedding、逐条
   Hybrid Retrieval、Rerank、调度和结果落库。
2. Proposal 按每批 8 条拆为 10 个串行批次，随后再生成总体章节。第 4 批首次漏掉
   `REQ-0029`、`REQ-0030`、`REQ-0031`，触发一次完整覆盖修复，因此实际执行 11 次批次
   调用。修复调用单独耗时 161.559 秒。
3. Proposal 批次生成时间波动很大，单次为 21.192～161.559 秒；总体章节输入 45,725
   字符，耗时 91.223 秒。Proposal 阶段 95% 左右的时间在 LLM 调用中。
4. Requirement 抽取从约 4,058 个输入字符生成 76 条需求，输出 11,139 tokens。结果是否
   过度原子化需要通过人工抽样和评测集确认，不能仅按数量合并强制性要求。
5. 本次没有 LLM 传输重试或 Schema 修复；主要延迟来自串行 LLM 调用和生成长度，而不是
   网络故障。仅出现一次 Proposal Requirement 覆盖修复。
6. MinerU PDF 解析仅耗时约 6.5 秒，Kafka/Outbox 阶段交接通常低于 1 秒，不是当前瓶颈。

## 优化优先级

1. 为同一 RFP 内的 Capability 判断增加受控并发，例如配置 4 个并发协程，并用 Semaphore
   控制 LLM、Qdrant 和 Reranker 压力；按 Requirement 原顺序汇总结果。
2. 将独立的 Proposal 批次以 2～3 个受控并发执行，全部完成后再生成总体章节；保留批次
   覆盖检查和最终全量 Requirement 校验。
3. 将当前全局 `LLM_REASONING_EFFORT=max` 改为按操作配置，针对结构化抽取、Capability
   判断和批次响应对比 `low/medium` 的质量与延迟，把高推理强度留给确有必要的环节。
4. 为 Proposal Batch 设置更贴近 Schema 上限的输出预算并压缩 Prompt；当前每批统一允许
   12,000 tokens，容易产生过长思考或输出。调整前需做截断和覆盖率回归测试。
5. 建立 Requirement 抽取评测集，检查遗漏、重复和过度拆分；只有在语义与强制条件均一致时
   才合并需求，避免用减少条数换取错误结果。
6. 增加持久化阶段计时或 OpenTelemetry Span，分别记录 MinerU、Embedding、Dense/Sparse
   Retrieval、RRF、Reranker、LLM、数据库及 MinIO 耗时，避免以后依赖日志重建性能数据。
