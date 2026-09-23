# DealFlow 项目面试指南

> 依据简历中的 DealFlow 项目描述，并优先按照 2026-09-23 本地工作区代码整理。部分本地代码尚未提交，面试时如需展示 GitHub，请先核对远程版本。本文中的配置数字是代码默认值，不是性能测试结果。

## 一、面试时怎样介绍项目

### 30 秒版本

DealFlow 是一个面向企业 RFP 的自动处理系统。用户上传招标文件和企业知识文档后，系统通过 Kafka 驱动多个 Worker，依次完成文档解析、需求抽取、知识检索、能力判断和 Proposal 生成。结果在 Web 工作台展示，由人审核 Markdown 方案。项目重点是长文档处理、有证据的 RAG 判断，以及异步任务在失败和重复消息下的可靠性。

### 2 分钟版本

企业销售或售前人员处理长篇 RFP 时，通常需要逐条找出客户需求、对照企业资料判断是否支持，最后形成回复方案。我把这个过程拆成几个异步阶段：上传后，原文件进入 MinIO，业务记录和待发送事件一起写入 MySQL；Kafka 将解析、需求抽取、能力评估、方案生成交给不同 Worker。

PDF 解析接入 MinerU，解析结果转换成统一文档结构；企业知识按照 Parent/Child 层级切块，Child 用于检索，Parent 用于补足上下文。评估需求时，Qdrant 同时做 Dense 和 BM25 召回，经 RRF 融合后可用 BGE Cross-Encoder 重排，再由 LLM 基于候选证据给出能力结论，并保存引用信息。Proposal 按需求分批生成，最后形成 Markdown 交由人审核。

工程上使用 Outbox 处理数据库与 Kafka 的双写问题；消费者手动提交 Offset，配合消费记录、业务状态检查和 Redis 锁处理重复投递与并发执行。这里实现的是 **at-least-once 场景下的幂等处理，不是端到端 exactly-once**。

### 一张图讲清主链路

```text
企业知识上传 ──→ Knowledge Worker ──→ 解析/结构化切块 ──→ Qdrant 索引
                                                     │
RFP 上传 ──→ RFP Worker ──→ Requirement Worker ──→ Capability Worker
                                                     │
                                                     ↓
                          人工审核 ←─ Markdown Proposal ←─ Proposal Worker
```

企业知识入库和 RFP 处理是两条流程，在能力评估阶段汇合。MySQL 保存业务状态与结构化结果，MinIO 保存原件及生成的文件，Kafka 传递阶段事件；**完整 PDF 不放进 Kafka 消息**。

## 二、逐条讲解简历内容

### 1. 项目介绍与技术栈

简历说“通过异步 Agent 工作流完成需求拆解、企业知识检索、能力判断与 Proposal 生成”。这里的 Agent 指承担特定任务的 LLM 组件和处理阶段；工作流由业务状态、Kafka 事件和 Worker 编排，**当前没有使用 LangGraph**。也不是把整份 PDF 直接送给一次模型调用。

| 技术 | 实际职责 |
| --- | --- |
| FastAPI | 上传、查询、任务重试、审核等 API |
| MySQL | RFP、文档、需求、能力结果、证据、工作流状态、Outbox 与消费记录 |
| MinIO | 原文件、解析文本、结构化产物及 Proposal Markdown |
| Kafka | 阶段完成或失败事件，解耦不同 Worker |
| Redis | 同一 RFP 在同一阶段的分布式锁 |
| Qdrant | 企业知识的 Dense + BM25 混合检索 |
| React + TypeScript | 上传、状态、需求/证据/方案展示及审核工作台 |
| Docker Compose | 编排基础设施与应用服务，支持本地部署 |

阅读代码的入口：[`app/services/rfp.py`](app/services/rfp.py)、[`app/workflow/stages/`](app/workflow/stages/)、[`docker-compose.yml`](docker-compose.yml)。

### 2. 异步工作流与可靠消费

#### 事件如何流转

上传 RFP 时，服务先把原文件保存到 MinIO，再在一个 MySQL 事务中写入 RFP、Document、WorkflowRun 和 OutboxEvent。事务提交后尝试发布事件；如果当时没发布成功，Outbox relay 后续扫描并重试。每个处理阶段完成业务落库后，再写下一阶段的 OutboxEvent。

| Topic | 生产者 → 消费者 | 事件含义 |
| --- | --- | --- |
| `rfp.uploaded` | 上传服务 → RFP Worker | 新 RFP 等待解析 |
| `rfp.completed` | RFP Worker → Requirement Worker | 解析完成，可抽取需求 |
| `rfp.requirements.extracted` | Requirement Worker → Capability Worker | 需求已经入库 |
| `rfp.capabilities.evaluated` | Capability Worker → Proposal Worker；审核要求修改时也会重新产生 | 能力判断完成，可生成或重生成方案 |
| `proposal.generated` | Proposal Worker 产生 | 方案已生成，等待人工审核 |
| `proposal.approved` | 审核服务产生 | 方案通过审核 |
| `rfp.failed` | 失败阶段产生 | 阶段处理失败 |
| `knowledge.ingestion.requested` | 知识上传服务 → Knowledge Worker | 企业知识需要解析和索引 |

事件中通常包含 `event_id`、`rfp_id`、`workflow_run_id` 及阶段所需的文档 ID、对象存储 key 或数量，而不是原文件正文。Topic 定义见 [`app/core/config.py`](app/core/config.py)。

#### 可靠性分别靠什么实现

1. **Transactional Outbox**：业务记录和待发事件同属一个 MySQL 事务，避免业务已经成功、却根本没有可投递事件。Kafka 发布成功但数据库还没标记 `PUBLISHED` 时可能重发，因此它不提供 exactly-once。实现见 [`app/infrastructure/messaging/outbox.py`](app/infrastructure/messaging/outbox.py)。
2. **手动提交 Offset**：业务处理完成后再提交。如果处理成功而 Offset 提交前进程崩溃，消息会重放。以 [`app/workers/requirement_worker.py`](app/workers/requirement_worker.py) 为例，它还处理分区再均衡和长任务超时。
3. **Consumed Event + 业务状态检查**：按 Consumer Group 和 `event_id` 记录已经处理的消息；各阶段还检查 RFP/Workflow 状态，避免重复生成。Consumed Event 的落库与阶段业务结果不是一个事务，因此不能只依赖前者。见 [`app/infrastructure/messaging/consumed_events.py`](app/infrastructure/messaging/consumed_events.py)。
4. **Redis 分布式锁**：限制同一 RFP 的同一阶段同时被多个执行者处理。锁采用过期时间、持有者 token、续租及释放时的持有者校验；它是并发保护，不替代业务幂等。见 [`app/infrastructure/locking/redis.py`](app/infrastructure/locking/redis.py)。
5. **失败重试**：可以通过 RFP 重试接口重新触发失败阶段，但这不是任意调用点的精确断点续跑。见 [`app/services/rfp.py`](app/services/rfp.py)。

当前 Requirement Worker 默认在**一个容器内启动 3 个进程**，同属于一个 Consumer Group；每个进程内部默认允许 2 个需求分块 LLM 请求并发。前者主要提升不同消息的消费能力，后者加快单个 RFP 的处理。Topic 分区数限制同一 Consumer Group 可同时活跃消费该 Topic 的进程数。见 [`app/workers/requirement_pool.py`](app/workers/requirement_pool.py) 与 [`app/core/config.py`](app/core/config.py)。

需求抽取会逐批保存部分结果，便于前端查看；但重试时会清除旧的部分 Requirement，再从该阶段重新抽取。面试中应说“阶段恢复/重做”，不要说“按 Chunk 精确续跑”。见 [`app/workflow/stages/extract_requirements.py`](app/workflow/stages/extract_requirements.py)。

### 3. 文档解析与增量知识库

#### PDF 解析与中间表示

PDF 处理调用 **MinerU 外部服务**，把其 OCR、版面、表格、公式等解析结果映射为 `DocumentIR`。`DocumentIR` 更接近原始文档页面与块信息，包括页面、阅读顺序和结构化元素；随后通过适配器转换成面向知识切块的 `StructuralDocument`。DOCX、Markdown 使用各自的解析路径，不应声称具有与 PDF 完全相同的版面信息。

对应代码：[`app/documents/pdf/mineru.py`](app/documents/pdf/mineru.py)、[`app/documents/pdf/models.py`](app/documents/pdf/models.py)、[`app/rag/hierarchical.py`](app/rag/hierarchical.py)。面试要说“接入 MinerU 并处理输出”，而不是“自行实现 OCR 模型”。

#### 为什么分 Parent/Child

小块更容易精确命中一项能力，但脱离上下文后可能看不出限制条件；大块上下文完整，却可能影响检索精度。因此采用 **Child 检索、Parent 扩展**：把 Child 向量写入 Qdrant，命中后按 Parent ID 从 MySQL 取得完整上下文，再交给能力判断。结构中尽量保留标题、页码、段落和表格相关信息。

当前默认配置约为 Parent 1200 tokens、Child 350 tokens、Child overlap 40 tokens。这些是可调参数，并不是最优性已经由实验验证。见 [`app/core/config.py`](app/core/config.py) 与 [`app/rag/retrieval.py`](app/rag/retrieval.py)。

#### 增量索引怎样工作

知识更新先检查解析后内容是否与原版本相同，再比较新旧 Child 的稳定标识、用于 embedding 的内容 Hash 与结构 Hash，分类为 `UNCHANGED`、`MOVED`、`MODIFIED`、`ADDED` 等。新增、修改块重新计算 embedding 并索引；未变化或仅位移的块复用向量，但可能更新 Qdrant payload；消失的块清理旧 Point。见 [`app/services/knowledge.py`](app/services/knowledge.py)。

更准确的说法是“**尽量只为新增或变化内容重算 embedding**”，不是“更新时只有新增或变化 Chunk 会发生任何操作”。MySQL、MinIO、Qdrant 也不存在单一跨系统事务；代码提供失败恢复，但不能声称绝对强一致。

### 4. Hybrid RAG 与证据审计

针对每条 Requirement，系统把需求转换成检索查询，在 Qdrant 中同时走 Dense 向量与 BM25 稀疏检索，经 RRF 融合得到候选 Child；可选用 `BAAI/bge-reranker-v2-m3` Cross-Encoder 重排，再按 Parent 去重，过滤非活跃知识文档并扩展 Parent 上下文。见 [`app/rag/vector_store.py`](app/rag/vector_store.py)、[`app/rag/reranker.py`](app/rag/reranker.py)、[`app/rag/retrieval.py`](app/rag/retrieval.py)。

- **Dense**：适合语义相近、但用词不同的需求与知识描述。
- **BM25**：适合产品名、协议名、标准名称和数字等词项匹配。
- **RRF**：按两路候选的排名融合，不要求两路原始分数可直接比较。
- **Cross-Encoder**：把需求和候选文本成对评分，通常只用于候选集精排，以控制计算成本。

能力判断除了完全支持、部分支持、不支持，还包括企业版限制、需要定制、需要人工复核等状态。系统保存候选 Evidence、检索或重排分数、选中引用等信息；引用校验会检查引用的 Point 是否来自给定候选集合。它让结论更可追溯，**不等于机器已证明每条引用在语义上一定支持结论**。见 [`app/workflow/stages/evaluate_capabilities.py`](app/workflow/stages/evaluate_capabilities.py)、[`app/agents/capability_citations.py`](app/agents/capability_citations.py)。

重排器在应用配置中默认关闭，但 Docker Compose 默认开启，且允许故障回退。面试中可说“Compose 默认尝试启用 BGE 重排，实际是否执行取决于配置和运行状态”。见 [`app/core/config.py`](app/core/config.py)、[`docker-compose.yml`](docker-compose.yml)。

### 5. Proposal、Web 工作台与人工审核

Proposal Agent 把 Requirement、能力状态、判断理由与有限条证据摘要组成输入，按需求分批生成逐条响应，然后基于这些响应生成总体章节。生成结果会校验需求 key：不允许缺失、额外或重复；必要时纠错或拆小批次。模型输出中的原始需求与能力状态会被数据库中的值校准，避免模型擅自改写。见 [`app/agents/proposal_generator.py`](app/agents/proposal_generator.py)、[`app/workflow/stages/generate_proposal.py`](app/workflow/stages/generate_proposal.py)。

最终 Markdown 保存到 MinIO，在 React 工作台预览。用户可以直接通过，也可以提出修改意见；修改意见会触发新版 Proposal 的生成。当前没有登录和审核人权限体系，**不要声称实现了角色权限管理**；也不要声称支持 DOCX/PDF 导出。前端进度为“阶段估算进度”，不是 LLM 任务真实完成百分比。见 [`app/services/proposal_review.py`](app/services/proposal_review.py)、[`web/src/App.tsx`](web/src/App.tsx)。

长 RFP 仍有一个边界：逐条响应虽然已经分批生成，最后生成总体章节时仍要传入所有逐条响应的汇总，极大规模下可能触及上下文窗口。后续可以增加分层摘要、按章节归并和 token 预算控制。

## 三、高频模拟问题与参考回答

### 1. 为什么用 Kafka，而不是 FastAPI `BackgroundTasks`？

RFP 解析和 LLM 调用耗时长，放在 API 进程里容易受到进程重启、部署和请求生命周期影响。Kafka 让 API 快速返回，各阶段能独立消费和扩容。但 Kafka 增加重复消息、Offset、积压等复杂度，所以需要 Outbox、幂等与监控。

### 2. Outbox 是否能保证消息只发送一次？

不能。它保证业务数据和“待发送事件”一起提交，避免业务成功却没有发送意图。Kafka 已接收消息、但数据库尚未标记已发布时如果崩溃，relay 可能再次发布。因此消费者必须能处理重复投递。

### 3. 为什么先处理业务，再提交 Offset？

如果先提交 Offset，之后业务失败，消息可能不会再来。先完成业务，再提交 Offset，崩溃时最多产生重放；重放由消费记录和业务状态检查处理。

### 4. `consumed_events` 与业务结果是不是同一事务？

不是。它有独立事务，因此“业务已成功但消费记录尚未写入”时可能重放。业务阶段的状态检查是另一道幂等保护。不能把整个系统说成严格的 exactly-once 事务处理。

### 5. Kafka 已经按 key 分区，为什么还需要 Redis 锁？

同一 Topic、同一 key 的顺序有帮助，但无法替代对重试、重放、再均衡以及不同事件导致同一阶段并发的保护。锁负责互斥，业务状态检查负责判断是否还要执行，两者各有作用。

### 6. Worker 处理到一半崩溃会发生什么？

未提交的消息可被重新投递。Redis 锁在失去续租后会过期，其他执行者可接手。阶段读取业务状态决定跳过或重做。需求抽取的部分结果可以显示，但目前不会从上一个成功 Chunk 精确继续。

### 7. 一个容器内 3 个需求 Worker，与单个 RFP 的分块并发有什么区别？

3 个进程属于消息级并发，主要处理多个 RFP；进程内部的受限异步并发用于同时请求多个文本块的抽取。前者受 Kafka 分区数限制，后者受 LLM 的速率、成本和上下文约束。

### 8. 长 RFP 是一次性送给 LLM 吗？

不是。解析文本按 token 预算分块，默认约 1000 tokens 一块、100 tokens 重叠，并限制总块数。各块输出再合并、去重与落库。这样降低单次调用超窗风险，但仍需关注边界信息和块数上限。见 [`app/agents/requirement_extractor.py`](app/agents/requirement_extractor.py)。

### 9. 为什么要 Parent/Child，而不是固定长度 Chunk？

只用大块会影响检索精度，只用小块会缺上下文。Child 寻找具体事实，Parent 恢复标题、限制条件和段落或表格背景，更适合把证据交给能力判断模型。

### 10. 你说的增量索引具体如何判断变化？

比较整份文档内容 Hash，再比较新旧 Child 的稳定 ID、embedding 内容 Hash 和结构 Hash。根据分类复用、更新或删除向量 Point，避免每次全量重算。必要时会有旧数据兼容的全量重建路径。

### 11. Dense、BM25、RRF、Rerank 分别解决什么？

Dense 解决语义召回，BM25 补充精确关键词，RRF 融合两路排名，Cross-Encoder 用更高计算成本对较少候选做精排。它们分别处理覆盖率、词项匹配和排序质量，而不是四种重复的检索方式。

### 12. 知识库里没有相关证据时，如何避免模型直接说“支持”？

应把这类情况交给待人工复核的状态，并在提示词和引用校验中约束结论。系统减少无依据判断，不承诺完全消除幻觉。面试中可以提出以人工标注的评测集检验误判率。

### 13. 如何保证 Proposal 没有漏掉某条需求？

每条需求有稳定的 `requirement_key`。分批生成后检查缺失、额外与重复 key；必要时纠错或进一步拆分。最终草稿也会核对完整 key 集合，并用业务库中的需求和能力状态校准模型输出。

### 14. 审核如何影响工作流？

通过时，更新 Proposal、RFP 和 Workflow 状态，并产生 `proposal.approved` 事件。提交修改意见或拒绝时，保存审核意见，再触发 Proposal Worker 基于原能力结果和反馈生成新版。当前审核没有用户身份鉴权。

### 15. 项目最需要改进什么？

第一，为检索和能力判断建立有标注的离线评测集，衡量召回率与错误支持率；第二，给超长 RFP 的最终总体章节加入分层摘要和 token 预算；第三，加强 MySQL、Qdrant、MinIO 跨系统更新的对账与补偿。没有实测数据时不要编造“准确率提升 X%”或“节省 Y 小时”。

## 四、简历措辞校准清单

- “可靠消费”是 **at-least-once + 幂等/状态检查**，不是 exactly-once。
- “失败阶段恢复”主要是**阶段重试或重做**，不是任意位置精确断点续跑。
- “仅重建新增或变化 Chunk”主要指**避免未变化内容重复生成 embedding**，复用块仍可能更新元数据。
- “MinerU 完成 OCR”指**接入外部解析服务并处理结果**，不是自行训练或实现 OCR。
- “BGE Cross-Encoder Rerank”受配置和运行状态影响，失败时可回退。
- “证据审计”使引用可追踪，不等于机器证明结论在语义上一定成立。
- “Agent 工作流”是当前项目的事件驱动编排，**不是 LangGraph 工作流**。
- 前端审核可直接使用，当前**没有登录、审核人区分或权限体系**。
- 最终交付物是 **Markdown**；当前不要介绍 DOCX/PDF 导出。

## 五、建议准备的现场演示

按“上传企业知识 → 上传 RFP → 查看阶段状态与 Requirement → 打开 Capability 的 Evidence → 预览 Markdown Proposal → 提交修改意见或审核通过”的顺序演示。提前准备一份可稳定处理的 RFP 和知识文档；若使用 PDF，确认 MinerU 凭据、LLM 服务与重排器运行环境可用。展示时区分“代码实现”“实际启用配置”和“尚未量化验证的效果”。
