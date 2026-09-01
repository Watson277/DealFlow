# DealFlow — Agentic RFP & Sales Automation Platform

## 1. 项目定位

DealFlow 是一个面向 B2B 企业销售与售前团队的 RFP 自动化处理平台。

系统通过三个 Agent 完成长文档 RFP 的需求提取、企业能力匹配和 Proposal 生成，并结合 RAG、消息队列、缓存、对象存储与关系数据库，实现可追踪、可异步执行的完整业务流程。

核心流程：

```text
RFP 上传
→ 文档解析
→ Requirement 提取
→ 企业知识检索
→ Capability 判断
→ Proposal 生成
→ 人工审核
→ Deal 归档
```

---

## 2. 技术栈

### Agent / LLM

- **LangGraph**：三 Agent 工作流编排、状态管理、条件路由、Checkpoint
- **LangChain**：LLM、Prompt、Retriever、Embedding 等组件封装
- **OpenAI / DeepSeek / Qwen**：Agent 推理
- **Pydantic**：Agent Structured Output

### RAG

- **Qdrant**：企业知识库向量数据库
- **BGE-M3 / OpenAI Embedding**：文档向量化
- **PyMuPDF**：PDF 解析
- **python-docx**：DOCX 解析
- **Reranker**：检索结果重排序

### Backend

- **FastAPI**：REST API / SSE
- **MySQL 8**：业务数据持久化
- **SQLAlchemy 2**：ORM
- **Alembic**：数据库迁移
- **Redis**：任务状态缓存、LLM/RAG Cache、分布式锁
- **Kafka**：异步任务与事件驱动
- **MinIO**：RFP、知识库文档、Proposal 文件存储
- **Docker Compose**：本地开发与服务编排

### Frontend

- **React + TypeScript**：RFP 上传、任务进度、能力矩阵、Proposal 审核

---

## 3. 三 Agent 设计

### 3.1 RFP Analyst Agent

职责：从原始 RFP 中提取和标准化客户需求。

主要能力：

- Requirement Extraction
- Requirement Decomposition
- Requirement Normalization
- 分类与去重
- Mandatory Requirement 识别
- 来源页码记录

输出示例：

```json
{
  "requirement_id": "REQ001",
  "category": "security",
  "requirement": "Support SAML 2.0",
  "mandatory": true,
  "source_page": 13
}
```

### 3.2 Capability Agent

职责：基于企业知识库判断每条 Requirement 是否能够满足。

处理流程：

```text
Requirement
→ Query Rewrite
→ Qdrant Retrieval
→ Metadata Filtering
→ Reranking
→ Evidence
→ Capability Judgment
```

能力状态：

```text
SUPPORTED
PARTIALLY_SUPPORTED
UNSUPPORTED
ENTERPRISE_ONLY
REQUIRES_CUSTOMIZATION
NEED_REVIEW
```

输出示例：

```json
{
  "requirement_id": "REQ003",
  "status": "UNSUPPORTED",
  "confidence": 0.95,
  "reason": "Current platform only supports SaaS and private cloud.",
  "evidence": [
    {
      "document": "Deployment Guide",
      "version": "3.2",
      "page": 17
    }
  ]
}
```

### 3.3 Proposal Agent

职责：将 Requirement、Capability Result 和 Evidence 转换为正式 Proposal。

输入：

```text
Requirements
+
Capability Results
+
Evidence
+
Customer Information
+
Proposal Template
```

主要生成：

- Executive Summary
- Requirement Response Matrix
- Technical Solution
- Security & Compliance
- SLA
- Deployment
- Risks & Gaps
- Commercial Notes

最终文件保存至 MinIO。

---

## 4. LangGraph Workflow

```text
START
  │
  ▼
parse_document
  │
  ▼
analyst_agent
  │
  ▼
save_requirements
  │
  ▼
capability_agent
  │
  ▼
aggregate_capability
  │
  ▼
proposal_agent
  │
  ▼
save_proposal
  │
  ▼
HUMAN_REVIEW
  │
  ├── Reject → proposal_agent
  │
  └── Approve
          │
          ▼
         END
```

其中：

- `analyst_agent`
- `capability_agent`
- `proposal_agent`

为 LLM Agent。

其余节点为普通业务代码。

---

## 5. LangGraph State

```python
class RFPState(TypedDict):
    rfp_id: str
    document_text: str
    requirements: list[Requirement]
    capability_results: list[CapabilityResult]
    proposal: Proposal | None
    stage: str
    errors: list[str]
```

三个 Agent 通过统一 State 传递结构化结果。

---

## 6. 后端架构

```text
                     React Web
                         │
                    HTTP / SSE
                         │
                         ▼
                      FastAPI
                         │
         ┌───────────────┼───────────────┐
         │               │               │
         ▼               ▼               ▼
       MySQL           MinIO           Kafka
     业务数据          文件存储          消息队列
                                           │
                                           ▼
                                      Worker Pool
                                           │
                                           ▼
                                        LangGraph
                                           │
                    ┌──────────────────────┼──────────────────────┐
                    ▼                      ▼                      ▼
             Analyst Agent        Capability Agent        Proposal Agent
                                          │
                                          ▼
                                        Qdrant
                                          │
                                   Enterprise RAG
                                          │
                                          ▼
                                        MinIO

                         Redis
                  Cache / Status / Lock
```

---

## 7. FastAPI

FastAPI 只负责同步 API，不直接执行长时间 Agent Workflow。

主要职责：

- 接收 RFP
- 参数校验
- 保存文件
- 写入 MySQL
- 发送 Kafka 消息
- 返回任务 ID
- 查询任务状态
- 提供审核接口

典型接口：

```text
POST /rfps
GET  /rfps/{id}
GET  /rfps/{id}/status
GET  /rfps/{id}/requirements

POST /knowledge
GET  /proposals/{id}
GET  /proposals/{id}/markdown
POST /proposals/{id}/reviews
GET  /proposals/{id}/reviews
```

`POST /proposals/{id}/reviews` 接受 `APPROVED`、`REJECTED` 或
`CHANGES_REQUESTED`。审核通过后以 MinIO 中的 Markdown 作为最终交付物；驳回或要求修改时，
审核意见会重新触发 Proposal Agent，生成下一个 Markdown 版本。当前个人项目模式不包含登录与
审核人角色，接口可直接访问，审核记录不绑定用户。

---

## 8. Kafka 与 Worker

Kafka 用于将长耗时 Agent Workflow 从 API 服务中解耦。

流程：

```text
Client
  ↓
FastAPI
  ↓
保存 MinIO
  ↓
写入 MySQL
  ↓
发送 Kafka
  ↓
返回 202 Accepted
```

Worker 独立消费 Kafka 消息并执行：

```text
Kafka
  ↓
Worker
  ↓
LangGraph
  ↓
3-Agent Workflow
```

第一版 Topic：

```text
rfp.uploaded
rfp.completed
rfp.failed
```

可通过增加 Worker 数量实现任务级并行处理。

---

## 9. Redis

Redis 主要承担：

- RFP 任务状态缓存
- LLM / RAG 结果缓存
- 分布式锁
- 幂等控制

示例：

```text
rfp:123:status
lock:rfp:123
```

---

## 10. MySQL

核心表：

```text
users
customers
rfps
requirements
capability_results
proposals
documents
workflow_runs
```

主要关系：

```text
Customer
   │
   └── RFP
        │
        ├── Requirement
        │       │
        │       └── CapabilityResult
        │
        └── Proposal
```

---

## 11. MinIO

MinIO 存储大文件：

```text
dealflow/

├── knowledge/
│   ├── product/
│   ├── security/
│   ├── sla/
│   └── historical_rfp/
│
├── rfp/
│   ├── RFP001.pdf
│   └── RFP002.docx
│
└── proposal/
    ├── RFP001_v1.md
    └── RFP001_v2.md
```

MySQL 仅保存文件元数据与 `object_key`。

---

## 12. Qdrant

Qdrant 存储企业知识库的 Chunk、Embedding 与 Metadata。

示例：

```json
{
  "document_id": "DOC001",
  "title": "Deployment Guide",
  "version": "3.2",
  "page": 17,
  "category": "deployment",
  "status": "ACTIVE",
  "text": "StellarCloud supports SaaS..."
}
```

Capability Agent 基于 Requirement 进行向量检索，并通过 Metadata Filtering 过滤过期或不相关文档。

---

## 13. 推荐项目目录

```text
dealflow/
│
├── app/
│   ├── api/
│   │   ├── rfp.py
│   │   ├── knowledge.py
│   │   └── proposal.py
│   │
│   ├── agents/
│   │   ├── analyst.py
│   │   ├── capability.py
│   │   └── proposal.py
│   │
│   ├── workflow/
│   │   ├── graph.py
│   │   ├── state.py
│   │   └── nodes.py
│   │
│   ├── rag/
│   │   ├── indexer.py
│   │   ├── retriever.py
│   │   ├── embedding.py
│   │   └── reranker.py
│   │
│   ├── workers/
│   │   └── rfp_worker.py
│   │
│   ├── services/
│   │   ├── document_service.py
│   │   ├── kafka_service.py
│   │   ├── redis_service.py
│   │   └── minio_service.py
│   │
│   ├── repositories/
│   │   ├── rfp_repository.py
│   │   ├── requirement_repository.py
│   │   └── proposal_repository.py
│   │
│   ├── models/
│   ├── schemas/
│   └── main.py
│
├── scripts/
│   ├── generate_mock_data.py
│   └── build_knowledge_base.py
│
├── tests/
├── alembic/
├── docker-compose.yml
└── README.md
```

---

## 14. 核心架构总结

```text
Python + FastAPI
LangGraph + LangChain
Qdrant + RAG
MySQL + SQLAlchemy
Redis
Kafka
MinIO
Docker Compose
React + TypeScript
```

整体架构：

> FastAPI 负责同步 API，Kafka + Worker 将长耗时 Agent Workflow 异步化；LangGraph 编排 RFP Analyst、Capability、Proposal 三个 Agent；Capability Agent 基于 Qdrant 企业知识库完成 Evidence-based RAG；MySQL 保存业务数据，Redis 管理缓存与分布式协调，MinIO 管理原始 RFP、企业知识文档和最终 Proposal。
