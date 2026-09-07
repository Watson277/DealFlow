# DealFlow 技术架构说明

> 文档状态：与当前仓库代码同步
>
> 项目版本：0.1.0
>
> 最后更新：2026-09-07

## 1. 项目定位

DealFlow 是一个个人练手性质的 B2B RFP（Request for Proposal）自动化处理系统。它接收客户 RFP 文档和企业知识文档，通过异步工作流完成文档解析、需求抽取、企业能力判断、Proposal 生成和人工审核，并在 Web 页面中展示全过程及最终 Markdown 方案。

当前核心流程如下：

```text
客户与 RFP 建档
    ↓
RFP 文件上传到 MinIO
    ↓
解析 PDF / DOCX，保存文本和 DocumentIR
    ↓
LLM 抽取结构化 Requirements
    ↓
Qdrant 混合检索企业知识 + Reranker
    ↓
LLM 生成 Capability 判断与证据引用
    ↓
LLM 生成 Markdown Proposal
    ↓
人工审核
    ├── APPROVED → 结束
    └── REJECTED / CHANGES_REQUESTED → 生成下一版本
```

当前项目不包含登录、权限、审核人区分，也不导出 DOCX/PDF Proposal。最终交付物是 Markdown。

## 2. 架构结论

当前实际运行架构是 **FastAPI + Kafka + 独立 Worker**，不是 LangGraph 工作流：

```text
React Web / REST Client
          │ HTTP
          ▼
      FastAPI API
          │
          ├── MySQL：业务状态和事务数据
          ├── MinIO：原始文件、解析产物、Proposal
          └── Outbox Event
                  │
                  ▼
          Kafka + Outbox Relay
                  │
   ┌──────────────┼─────────────────────────────┐
   ▼              ▼              ▼              ▼
RFP Worker  Requirement Worker  Capability Worker  Proposal Worker
   │              │              │              │
文档解析       LLM 需求抽取    Qdrant RAG + LLM   LLM 方案生成
                                  │
                             Redis 分布式锁
```

`langgraph`、`langchain`、`langchain-openai` 和 `sse-starlette` 仍在 Python 依赖中，但当前业务代码没有用它们编排工作流或提供 SSE。任务进度由前端轮询 REST 状态接口获取。

## 3. 技术栈

| 层次 | 技术 | 当前用途 |
| --- | --- | --- |
| 后端语言 | Python 3.11–3.12 | API、Worker、文档处理、RAG |
| Web API | FastAPI、Uvicorn | REST 接口、校验、健康检查 |
| 数据校验 | Pydantic 2、pydantic-settings | API、事件、LLM 结构化输出、配置 |
| ORM / 迁移 | SQLAlchemy 2 Async、Alembic | MySQL 异步访问和数据库版本管理 |
| 关系数据库 | MySQL 8.4 | 业务事实来源、状态、审计、Outbox |
| 消息系统 | Kafka 3.9.1（KRaft）、aiokafka | 异步阶段解耦、任务分发、领域事件 |
| 协调 | Redis 7 | RFP 各阶段分布式锁及锁续期 |
| 对象存储 | MinIO | 原文、解析文本、DocumentIR、Chunk、Markdown |
| 向量数据库 | Qdrant 1.19 | Dense + BM25 Sparse 混合检索 |
| LLM SDK | OpenAI Python SDK | OpenAI-compatible Chat Completions 和 Embeddings |
| 默认模型 | GLM-5.3-Flash | 需求抽取、能力判断、Proposal 生成 |
| 默认嵌入模型 | embedding-3，1024 维 | 企业知识 Child Chunk 向量化 |
| Reranker | BAAI/bge-reranker-v2-m3 | Cross-Encoder 本地重排，可使用 NVIDIA GPU |
| PDF | PyMuPDF、OpenCV、Tesseract | 原生文本、版面、表格、OCR、DocumentIR |
| DOCX | python-docx | RFP/知识文档文本提取 |
| 前端 | React 18、TypeScript 5、Vite 8 | 单页工作台 |
| Markdown | react-markdown、remark-gfm | 安全渲染 Proposal 与 GFM |
| 图标 | lucide-react | 前端图标 |
| Web 容器 | Nginx | 静态文件和反向代理 |
| 测试/质量 | pytest、pytest-asyncio、Playwright、Ruff、mypy | 单元、集成、浏览器和静态检查 |
| 容器编排 | Docker Compose | 一次启动完整本地环境 |

## 4. 代码分层

```text
RFP-Agent/
├── app/
│   ├── agents/                 # 三个 LLM Agent 与 Capability 引用处理
│   ├── api/
│   │   ├── dependencies.py     # FastAPI 依赖注入
│   │   └── routes/             # health/customers/rfps/knowledge/proposals/dev
│   ├── core/                   # 配置、异常、结构化日志
│   ├── db/                     # AsyncEngine、Session、ORM Base
│   ├── documents/
│   │   ├── parser.py           # PDF/DOCX/Markdown 统一入口
│   │   └── pdf/                # PDF 预检、OCR、版面、表格、融合、IR
│   ├── infrastructure/
│   │   ├── locking/            # Redis 分布式锁
│   │   ├── messaging/          # Kafka、Outbox、Consumed Event
│   │   └── storage/            # MinIO 和本地调试产物导出
│   ├── llm/                    # Chat Completions、JSON 修复与校验
│   ├── models/                 # SQLAlchemy 模型
│   ├── proposals/              # Markdown 渲染
│   ├── rag/                    # 切块、Embedding、Qdrant、重排、评测
│   ├── repositories/           # 数据访问层
│   ├── schemas/                # API、事件和 Agent 数据契约
│   ├── services/               # API 用例与业务事务
│   ├── workers/                # Kafka 消费者和 Outbox Relay
│   ├── workflow/stages/        # 四个可独立重试的流水线阶段
│   └── main.py                 # FastAPI 入口
├── alembic/                    # 数据库迁移
├── docs/                       # 架构和设计资料
├── tests/                      # 后端单元/集成测试
├── web/                        # React 前端、Nginx、Playwright
├── data/processed-documents/   # 可选的本地解析产物镜像
├── Dockerfile                  # Python 应用镜像
├── docker-compose.yml          # 完整运行拓扑
└── pyproject.toml              # Python 依赖和工具配置
```

分层职责：Route 只处理 HTTP；Service 组织业务用例和事务；Repository 隔离 SQL；Workflow Stage 执行一个异步阶段；Worker 负责消费、加锁、幂等和提交 Kafka offset；Agent 只负责模型输入输出；RAG 和 Documents 各自封装知识检索与文档解析。

## 5. 运行服务与端口

| Compose 服务 | 容器/镜像 | 宿主机端口 | 作用 |
| --- | --- | --- | --- |
| `web` | `dealflow-web:local` | 3000 | React/Nginx 工作台 |
| `api` | `dealflow-app:local` | 8000 | FastAPI |
| `mysql` | `mysql:8.4` | 3307 | 业务数据库 |
| `redis` | `redis:7-alpine` | 6380 | 分布式锁，AOF 持久化 |
| `kafka` | `apache/kafka:3.9.1` | 9092 | 单节点 KRaft Broker |
| `qdrant` | `qdrant/qdrant:v1.19.0` | 6333/6334 | HTTP/gRPC 向量服务 |
| `minio` | `minio/minio:latest` | 9000/9001 | S3 API/管理台 |
| `migration` | 应用镜像 | 无 | Alembic 升级和增量索引回填 |
| `kafka-init` | Kafka 镜像 | 无 | 创建 8 个 Topic |
| `minio-init` | MinIO Client | 无 | 创建 Bucket |
| `outbox-relay` | 应用镜像 | 无 | 重发待投递 Outbox 事件 |
| 5 个业务 Worker | 应用镜像 | 无 | 知识入库及 RFP 四阶段处理 |

MySQL、Redis、Kafka、Qdrant、MinIO 和 Hugging Face 模型缓存均使用命名卷。RFP Worker、Knowledge Worker 和 API 还可把处理产物挂载到宿主机 `data/processed-documents`。

## 6. RFP 主工作流

### 6.1 创建任务

`POST /rfps` 接收客户 ID、任务信息以及 PDF/DOCX。API 校验文件和客户，将原文件写入 MinIO，并在同一个 MySQL 事务中创建：

- `rfps`：任务及当前状态；
- `documents`：RFP 原文元数据与对象键；
- `workflow_runs`：本次完整流程及 correlation ID；
- `outbox_events`：`rfp.uploaded` 事件。

接口立即返回 `202 Accepted`，耗时处理不占用 HTTP 请求。

### 6.2 四个异步阶段

| 阶段 | Worker | 输入事件 | 主要操作 | 成功事件 |
| --- | --- | --- | --- | --- |
| `parse_document` | RFP Worker | `rfp.uploaded` | 下载、解析、保存 Markdown/Text 与 DocumentIR | `rfp.completed` |
| `extract_requirements` | Requirement Worker | `rfp.completed` | 分段调用 LLM，去重并落库 Requirements | `rfp.requirements.extracted` |
| `evaluate_capabilities` | Capability Worker | `rfp.requirements.extracted` | RAG、重排、LLM 判断、证据审计 | `rfp.capabilities.evaluated` |
| `generate_proposal` | Proposal Worker | `rfp.capabilities.evaluated` | 汇总客户、需求、能力和证据，生成 Markdown | `proposal.generated` |

`rfp.completed` 仅表示“RFP 文档解析完成”，并不表示整个任务完成。Proposal 生成后，RFP 进入 `REVIEW_PENDING / human_review`。

### 6.3 状态与进度

RFP 的主要状态包括 `UPLOADED`、`QUEUED`、`PROCESSING`、`REVIEW_PENDING`、`APPROVED`、`FAILED` 和 `ARCHIVED`。`current_stage`、`stage_started_at`、`processing_started_at`、`completed_at`、`error_message` 和 Workflow Run 的 `attempt` 用于展示进度、耗时和失败原因。

`GET /rfps/{rfp_id}/status` 返回阶段标签、进度百分比、阶段耗时、重试次数及是否终态。当前前端定时轮询该接口，不使用 WebSocket 或 SSE。

### 6.4 失败与重试

任一阶段失败时，系统原子更新 RFP/Workflow Run，并写入 `rfp.failed`。`POST /rfps/{rfp_id}/retry` 只允许重试 `FAILED` 任务，会根据数据库已有产物从失败阶段恢复：

- 尚未解析：重新发送 `rfp.uploaded`；
- 已有解析文本：从 `rfp.completed` 恢复；
- 已有 Requirements：从 `rfp.requirements.extracted` 恢复；
- 已有 Capability：从 `rfp.capabilities.evaluated` 恢复。

## 7. LLM 与 Agent

### 7.1 接口方式

`StructuredChatClient` 基于 OpenAI Python SDK 调用 OpenAI-compatible `chat.completions`。默认配置为：

```text
LLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4/
LLM_MODEL=glm-5.3-flash
```

密钥可通过 `LLM_API_KEY`、`ZAI_API_KEY` 或兼容的 `OPENAI_API_KEY` 提供。Embedding 也通过同一兼容客户端调用 `/embeddings`。

### 7.2 结构化输出保障

三类 Agent 均要求 JSON 结构化输出，并使用 Pydantic 严格校验。模型输出不符合 Schema 时，系统会：

1. 提取可能被 Markdown 代码块包裹的 JSON；
2. 规范化可修复字段；
3. 把具体校验错误反馈给模型执行修复重试；
4. 达到重试上限后将阶段标为失败，保留可读错误。

### 7.3 Agent 职责

- **Requirement Extraction Agent**：对长文本分块，提取 requirement key、类别、原文、规范化文本、是否强制、页码、引用、置信度，并在入库前去重。
- **Capability Agent**：读取每条 Requirement 的候选知识证据，输出支持状态、置信度、理由、定制说明和选中引用。
- **Proposal Agent**：按客户、需求、Capability 与审核意见生成结构化草稿，再由确定性 Markdown Renderer 输出最终文件。

Capability 状态为 `SUPPORTED`、`PARTIALLY_SUPPORTED`、`UNSUPPORTED`、`ENTERPRISE_ONLY`、`REQUIRES_CUSTOMIZATION` 或 `NEED_REVIEW`。没有有效知识证据时不会臆测支持，而是写入 `NEED_REVIEW`。

## 8. 文档处理

### 8.1 格式支持

- RFP 上传：PDF、DOCX；
- 企业知识库：PDF、DOCX、MD、MARKDOWN；
- 单文件默认最大 50 MiB；
- 加密 PDF、空文件和不支持的格式会被拒绝。

统一解析器把不同来源转成文本；PDF 还会产生结构化 `DocumentIR`，保留页码、块类型、坐标、阅读顺序、来源和警告。

### 8.2 PDF Pipeline

```text
预检
  → PyMuPDF 原生提取
  → 页面质量/扫描类型判断
  → 页面图像版面区域检测
  → 必要时 Tesseract OCR
  → 原生表格提取或扫描表格结构识别（TSR）
  → 可选 VLM 图像区域分析
  → Native/OCR/Table/VLM Block 去重融合
  → 标题、段落、列表、页眉页脚等语义与阅读顺序
  → DocumentIR JSON + Markdown/Text
```

PDF 处理支持页面级并行、页数上限、乱码比例判断、图片覆盖率路由、OCR DPI/语言/超时、表格最大单元格数和融合阈值配置。VLM 默认关闭，启用后使用 OpenAI-compatible 多模态接口。

开发环境提供 `POST /dev/pdf/parse`，上传 PDF 后返回包含 `DocumentIR JSON`、解析 Markdown 和摘要的 ZIP；非开发环境返回 404。

## 9. 企业知识库与 RAG

### 9.1 异步知识入库

`POST /knowledge` 先保存原文件和 `knowledge.ingestion.requested`，返回 `202`。Knowledge Worker 随后执行：

```text
解析文档
  → 转换为统一 StructuralDocument
  → 层级切块 Parent / Child
  → Child Embedding
  → Qdrant Dense + Sparse 索引
  → Parent、Child 索引元数据写入 MySQL
  → 解析文本、DocumentIR、Chunk Bundle 写入 MinIO
  → Document 状态 READY
```

系统使用 SHA-256 检测重复知识文件。`PUT /knowledge/{id}` 支持替换文档并做增量索引：稳定 ID、内容哈希、结构哈希和 embedding 哈希用于识别新增、更新、移动和删除的 Chunk，尽量只重算变化内容。迁移容器启动时运行 `app.rag.backfill_incremental`，为旧数据补齐增量索引信息。

### 9.2 结构化层级切块

PDF、Markdown 和 DOCX 先被适配成来源无关的结构节点，保留：

- 标题层级和 section path；
- 页码/行号/段落号；
- PDF block ID 与 bounding box；
- 段落、列表、表格、代码、图片、公式、标题等节点类型。

Parent Chunk 保存完整上下文，默认上限 1200 tokens；Child Chunk 用于检索，默认上限 350 tokens、重叠 40 tokens。表格和代码块按结构切分，避免普通字符截断破坏内容。

### 9.3 混合检索与重排

Qdrant Collection 默认是 `dealflow_knowledge_v2`，包含命名 Dense 向量 `dense` 和 Sparse BM25 向量 `bm25`。查询过程为：

1. 用 Requirement 生成 Dense Embedding；
2. Dense 与 Sparse 分别预取候选；
3. Qdrant 使用 RRF 融合；
4. 可选 `bge-reranker-v2-m3` Cross-Encoder 对 Child 候选重排；
5. 按 Parent 去重，再从 MySQL 展开 Parent 全文；
6. 过滤已删除/归档知识文档；
7. 把检索证据交给 Capability Agent。

Compose 默认启用 GPU Reranker，并为 Capability Worker 申请一张 NVIDIA GPU；配置允许切换 `auto/cuda/cpu`。如果本地模型失败且允许 fallback，则退回 RRF 排序。

### 9.4 引用与评测

每次 Capability 判断把所有候选证据和最终选中证据写入 `capability_evidence`，保留文档、版本、页码、section、片段、Child 命中、检索模式、检索分数、重排分数、排名和选择顺序。`citation_audit` 记录引用校验结果，确保模型只能引用实际检索到的证据。

`app/rag/evaluate_cli.py` 和评测语料支持离线评估检索质量，包括候选命中、排序质量和延迟报告，用于调整 top-k、阈值、切块和 Reranker。

## 10. Kafka 事件设计

所有 Topic 在 Compose 中创建为 3 个分区、复制因子 1。RFP 事件以 `rfp_id` 为消息 key，知识事件以 `document_id` 为 key，保证同一实体尽量进入同一分区。

| Topic | 生产者 | 消费者 | 核心内容/触发时机 |
| --- | --- | --- | --- |
| `rfp.uploaded` | RFP API、重试服务 | RFP Worker | 文件上传和业务落库完成；含 rfp/document/workflow/correlation ID |
| `rfp.completed` | RFP Stage、重试服务 | Requirement Worker | **文档解析完成**；含 parsed text object key |
| `rfp.requirements.extracted` | Requirement Stage、重试服务 | Capability Worker | Requirements 已落库；含 document/workflow ID、数量 |
| `rfp.capabilities.evaluated` | Capability Stage、审核修订、重试服务 | Proposal Worker | Capability 已落库；含数量；修订时还带 Proposal/审核意见 |
| `proposal.generated` | Proposal Stage | 当前无消费者 | Proposal 版本和 Markdown 已生成，作为通知事件 |
| `proposal.approved` | 审核服务 | 当前无消费者 | 审核通过；含 Proposal 版本和 Markdown object key |
| `rfp.failed` | 四个 RFP Stage | 当前无消费者 | 任一阶段失败；含失败 stage 和 error code |
| `knowledge.ingestion.requested` | Knowledge API | Knowledge Worker | 原始知识文件已保存；含 document ID |

事件是 UTF-8 JSON，公共字段包括 `event_id`、`event_type`、`occurred_at`，再附加对应实体 ID 和阶段数据。事件 Schema 使用 Pydantic 校验；无效消息会记录日志并提交 offset，避免永久阻塞分区。

### 10.1 Transactional Outbox

业务状态和对应 `outbox_events` 在同一个 MySQL 事务提交，避免“数据库成功但消息未创建”。提交后系统立即尝试发布 Kafka；失败时事件保持 `PENDING`。独立 `outbox-relay` 持续扫描到期事件，通过行锁认领并按指数退避重试，成功后标记 `PUBLISHED`。

默认 Relay 参数：1 秒轮询、每批 50 条、1 秒起始退避、最多 300 秒。此设计提供 **at-least-once** 投递，不承诺 exactly-once。

### 10.2 消费幂等与 Offset

每个 Worker 使用独立 consumer group，并关闭自动提交。成功处理后才手动提交 offset。处理期间崩溃会导致消息再次投递，因此系统组合使用：

- `consumed_events`：以 `(consumer_group, event_id)` 和 `(consumer_group, topic, partition, offset)` 唯一约束记录已完成消息；
- MySQL 唯一约束和状态检查：防止重复写入业务结果；
- Redis 分布式锁：防止同一 RFP 同一阶段并发执行；
- Kafka key：维持同一实体的分区顺序。

因此允许重复投递，但业务结果保持幂等。

## 11. Redis 分布式锁

Redis 当前只承担分布式锁，不用于任务状态缓存、LLM 缓存或 RAG 缓存。任务状态的事实来源始终是 MySQL。

各 Worker 在处理 RFP 阶段前按 RFP/阶段构造锁键，通过原子 `SET NX EX` 获取锁。锁值包含本次持有者 token，释放时用 Lua 脚本校验 token，防止误删其他 Worker 的锁。Watchdog 定期续期长时间的 LLM、OCR 或 Reranker 任务；默认续期间隔 30 秒，各阶段 TTL 可配置。

获取不到锁时，消费者不会把该消息当成成功处理，而会让分区回到相同 offset 后再试。

## 12. MySQL 数据模型

MySQL 是业务状态、流程状态和审计记录的唯一事实来源。主表如下：

| 表 | 作用 |
| --- | --- |
| `customers` | 客户基本资料，支持软删除 |
| `users` | 预留用户模型；当前无认证和登录流程 |
| `rfps` | RFP 元数据、状态、阶段、时间、错误、乐观锁版本 |
| `documents` | RFP/知识文件、MinIO object key、哈希、解析产物和扩展元数据 |
| `workflow_runs` | 每次 FULL/REPROCESS/PROPOSAL_REVISION 运行及 attempt |
| `requirements` | 结构化需求、来源、层级、置信度、指纹和原始模型输出 |
| `knowledge_chunks` | 可展开的 Parent Chunk 正文和来源定位 |
| `knowledge_child_indexes` | Child/Qdrant point、顺序和增量更新哈希 |
| `capability_results` | 每条需求在一次 Workflow Run 中的能力判断 |
| `capability_evidence` | 检索候选、入选引用、排名、分数和来源审计 |
| `proposals` | Proposal 版本、状态、结构化内容和 Markdown object key |
| `proposal_reviews` | 匿名审核决定和意见 |
| `outbox_events` | 待发布/已发布消息及重试信息 |
| `consumed_events` | Worker 已成功消费事件的幂等记录 |

主要关系：

```text
Customer 1 ── N RFP
RFP      1 ── N Document / WorkflowRun / Requirement / Proposal
Requirement 1 ── N CapabilityResult
WorkflowRun 1 ── N CapabilityResult / Proposal
CapabilityResult 1 ── N CapabilityEvidence
Document 1 ── N KnowledgeChunk / KnowledgeChildIndex / CapabilityEvidence
Proposal 1 ── N ProposalReview
```

Alembic 管理所有表、索引、约束和后续演进。`rfps.row_version` 用于 SQLAlchemy 乐观并发控制。

## 13. MinIO 与本地产物

MinIO Bucket 默认名为 `dealflow`。它保存：

- RFP 与知识库原始文件；
- 解析后的 Text/Markdown；
- PDF `DocumentIR` JSON；
- 层级 Chunk Bundle JSON；
- 每个版本的 Proposal Markdown。

MySQL 只保存元数据和 object key，不把大文本文件塞进关系表。`LocalArtifactExporter` 可把解析 Markdown、IR 和 Chunk Bundle 同步到宿主机 `data/processed-documents`，便于本地检查；它不是权威存储，关闭后不影响主流程。

Proposal 模型中仍保留 `docx_object_key`、`pdf_object_key` 兼容字段，但当前代码只写 `markdown_object_key`，不执行 DOCX/PDF 导出。

## 14. 人工审核

Proposal 生成后状态为 `REVIEW_PENDING`。`POST /proposals/{proposal_id}/reviews` 接受：

- `APPROVED`：Proposal/RFP/Workflow Run 结束，发送 `proposal.approved`；
- `CHANGES_REQUESTED`：保存意见并发送新的 `rfp.capabilities.evaluated`，Proposal Worker 生成下一版本；
- `REJECTED`：保存拒绝意见，并按修订流程生成下一版本。

后续版本会把旧 Proposal 标为 `SUPERSEDED`。审核接口无需登录，审核记录没有 reviewer 字段，适合当前个人项目范围。

## 15. REST API

### 健康检查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/health/live` | 进程存活，不检查依赖 |
| GET | `/health`、`/health/ready` | 检查 MySQL、Redis、Kafka、Qdrant、MinIO |

### 客户

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/customers` | 创建客户 |
| GET | `/customers` | 分页/搜索客户 |
| GET | `/customers/{customer_id}` | 客户详情 |
| DELETE | `/customers/{customer_id}` | 软删除；有未删除 RFP 时返回 409 |

### RFP

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/rfps` | 上传 PDF/DOCX 并异步创建任务，返回 202 |
| GET | `/rfps` | 分页、客户/状态/关键字过滤 |
| GET | `/rfps/{rfp_id}` | 任务、文档和 Workflow Run 详情 |
| GET | `/rfps/{rfp_id}/status` | 状态、进度、耗时、错误和 attempt |
| POST | `/rfps/{rfp_id}/retry` | 从失败阶段重试，返回 202 |
| GET | `/rfps/{rfp_id}/requirements` | 需求列表 |
| GET | `/rfps/{rfp_id}/capabilities` | 能力判断、证据和引用审计 |
| GET | `/rfps/{rfp_id}/proposals` | Proposal 版本列表 |
| DELETE | `/rfps/{rfp_id}` | 软删除、取消活动 Run 和待发事件 |

### 企业知识库

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/knowledge` | 上传 PDF/DOCX/MD/MARKDOWN，异步索引，返回 202 |
| PUT | `/knowledge/{document_id}` | 替换文档并增量重建索引 |
| GET | `/knowledge` | 知识文档列表 |
| GET | `/knowledge/{document_id}` | 文档、解析和索引状态 |
| DELETE | `/knowledge/{document_id}` | 删除 Qdrant points 并将文档归档 |

### Proposal

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/proposals/{proposal_id}` | Proposal 详情 |
| GET | `/proposals/{proposal_id}/markdown` | 返回 `text/markdown` 原文 |
| POST | `/proposals/{proposal_id}/reviews` | 匿名审核 |
| GET | `/proposals/{proposal_id}/reviews` | 审核历史 |

FastAPI 当前关闭 Swagger UI 和 ReDoc（`/docs`、`/redoc`），但保留 `/openapi.json`。Web/API 均无需身份认证。

## 16. 前端架构

前端是 React + TypeScript 单页工作台，包含：

- 总览、RFP 任务、企业知识库、客户管理；
- RFP 与知识文件点击选择或拖放上传；
- 搜索、状态、阶段进度、耗时、失败错误和重试；
- Requirement、Capability、Evidence、Proposal 版本详情；
- Proposal 审核及审核意见；
- 客户、RFP、知识文档删除；
- Markdown 页面内预览和原文获取。

Proposal 使用 `react-markdown + remark-gfm` 渲染表格、列表、链接、代码等 GFM 内容，并启用 `skipHtml`，不会把模型返回的原始 HTML 直接注入页面。前端生产构建由 Nginx 托管并代理后端请求。

## 17. 配置体系

所有运行配置由 `pydantic-settings` 读取 `.env` 和环境变量。`.env.example` 是本地模板，不应提交真实 API Key 或生产密码。配置大类包括：

- APP、日志、CORS；
- MySQL、Redis、Kafka、Outbox；
- MinIO、Qdrant Collection、Dense/Sparse 检索；
- LLM base URL、模型、超时、采样、重试、最大输出；
- Embedding 模型、维度、批量；
- Parent/Child 切块与 tokenizer；
- Reranker 模型、设备、batch、截断和 fallback；
- PDF 预检、OCR、版面、TSR、VLM、融合和并行；
- 各工作流阶段的 Redis 锁 TTL；
- 本地产物导出。

没有 LLM/ZAI/OpenAI Key 时，Knowledge、Requirement、Capability 和 Proposal Worker 会输出提示后退出；基础设施、API 和 RFP 文档解析仍可启动。

## 18. 启动、迁移与运维

完整环境启动：

```powershell
Copy-Item .env.example .env
# 编辑 .env，至少设置 LLM_API_KEY 或 ZAI_API_KEY
docker compose up --build -d
docker compose ps
```

启动依赖顺序由健康检查控制：基础设施就绪后，`kafka-init` 创建 Topic、`minio-init` 创建 Bucket、`migration` 执行 `alembic upgrade head` 和增量索引回填，随后 API 与 Worker 启动。

常用入口：

```text
Web              http://localhost:3000
API              http://localhost:8000
OpenAPI JSON     http://localhost:8000/openapi.json
MinIO Console    http://localhost:9001
Qdrant HTTP      http://localhost:6333
```

常用日志命令：

```powershell
docker compose logs -f api outbox-relay rfp-worker knowledge-worker requirement-worker capability-worker proposal-worker
```

`docker compose down` 保留数据卷；`docker compose down -v` 会永久删除本项目的 MySQL、Kafka、MinIO、Qdrant、Redis 和模型缓存数据，执行前必须确认。

## 19. 测试与质量保障

后端测试分为不依赖外部服务的单元测试和需要运行基础设施的 integration 测试，覆盖 API/Service/Repository、四阶段 Workflow、Outbox Relay、Consumed Event、Redis 锁、Qdrant、RAG、引用审计、文档解析和 PDF Pipeline。

```powershell
# 后端单元测试
uv run pytest -q -m "not integration"

# 代码检查
uv run ruff check .
uv run mypy app

# 前端构建与浏览器测试
Set-Location web
npm run build
npm test
```

Playwright 测试会拦截 API，不访问真实 LLM，也不写业务数据库。集成测试需显式设置 `RUN_INTEGRATION_TESTS=1`，避免误用本地服务。

结构化日志使用 `structlog`：开发环境可读输出，非开发环境 JSON 输出。排查卡住任务时应同时查看 `/rfps/{id}/status`、对应 Worker 日志、`outbox_events`、`consumed_events` 和 Kafka consumer group 状态。

## 20. 删除与数据生命周期

- 删除 RFP：软删除 RFP，将状态改为 `ARCHIVED`，取消未完成 Workflow Run，并把该 RFP 尚未发布的 Outbox 标记失败；历史业务数据和 MinIO 文件暂不物理清除。
- 删除客户：软删除；必须先删除其所有活动 RFP。
- 删除知识文档：解析/索引过程中禁止删除；先删除相关 Qdrant points，成功后将 Document 标为 `ARCHIVED/DELETED`，MySQL/MinIO 留作记录。
- Kafka 和 Outbox 是事件历史的一部分；当前没有自动保留期和归档清理任务。

## 21. 安全性与当前边界

当前实现面向本地个人开发，不是生产安全配置：

- 没有身份认证、授权、租户隔离和审核人追踪；
- Kafka 使用 PLAINTEXT，MySQL/Redis/MinIO 使用本地开发密码；
- MinIO、数据库和中间件端口直接暴露给宿主机；
- Compose 是单机部署，Kafka 复制因子为 1，无高可用；
- 没有病毒扫描、内容安全审核、限流和集中密钥管理；
- 事件投递语义为 at-least-once，需依赖幂等设计；
- 目前没有 `rfp.failed`、`proposal.generated`、`proposal.approved` 的下游通知消费者；
- 依赖中虽有 LangGraph/LangChain/SSE，但当前没有接入，不能据此声称已具备图编排、Checkpoint 或实时推送。

若走向生产，应优先增加认证授权、Secret 管理、TLS/SASL、网络隔离、对象生命周期、备份恢复、监控告警、Kafka 多副本、死信策略和清理任务。

## 22. 一句话总结

DealFlow 当前是一个以 **MySQL 为事实来源、MinIO 保存文件、Kafka + Outbox 驱动异步阶段、Redis 防止并发重复、Qdrant 混合 RAG 提供可审计证据、GLM-5.3-Flash 通过 Chat Completions 完成三类 Agent 推理、React 展示并审核 Markdown Proposal** 的完整本地容器化 RFP 自动化系统。
