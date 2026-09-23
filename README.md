# DealFlow RFP Agent

DealFlow 是一个基于 FastAPI、Kafka 和多个异步 Agent Worker 的 RFP 处理系统。

## 使用 Docker Compose 启动

1. 创建本地环境文件：

   ```powershell
   Copy-Item .env.example .env
   ```

2. 在 `.env` 中填写智谱与 MinerU API Key：

   ```dotenv
   LLM_API_KEY=你的智谱_API_Key
   MINERU_API_TOKEN=你的_MinerU_API_Token
   ```

   默认配置通过智谱的 OpenAI-compatible Chat Completions API 调用
   `glm-5.3-flash`，并使用 `embedding-3`（1024 维）生成知识库向量。也可以用
   `ZAI_API_KEY` 作为密钥变量名；`OPENAI_API_KEY` 仅作为旧配置的兼容别名。
   基础设施密码仅用于本地开发时可以保留默认值。

   未配置 `LLM_API_KEY` 时，API 与 RFP 文件解析 Worker 仍可启动；知识库、需求抽取、
   能力判断和 Proposal Worker 会输出说明后停止，以避免无意义的重启循环。
   未配置 `MINERU_API_TOKEN` 时，PDF 类型的 RFP、知识库上传及本地 PDF 解析测试会失败；
   DOCX、Markdown 和纯文本处理不受影响。

   从原先 1536 维向量配置升级时，默认 Qdrant collection 会切换到
   `dealflow_knowledge_glm`。旧 collection 不会被删除，但企业知识文档需要重新上传索引。

3. 构建并启动完整系统：

   ```powershell
   docker compose up --build -d
   ```

Compose 会依次启动 MySQL、Redis、Kafka、Qdrant 和 MinIO，创建 Kafka topics 与 MinIO
bucket，执行 Alembic 数据库迁移，最后启动 FastAPI、各业务 Worker、Outbox Relay 和 React Web
容器。

## 访问地址

- 业务工作台：[DealFlow](http://localhost:3000)（无需登录）
- 服务就绪检查：[Health](http://localhost:8000/health/ready)
- API 机器可读定义：[OpenAPI](http://localhost:8000/openapi.json)
- MinIO Console：[MinIO](http://localhost:9001)

Swagger `/docs` 和 ReDoc `/redoc` 已关闭，业务界面不展示自动生成的 Example Value、
模拟记录或预填示例。现有数据库记录和测试文档不会因此被删除。

## 工作台操作

先在「客户管理」创建客户，在「企业知识库」上传公司资料，再通过「新建 RFP」上传客户文件。
点击 RFP 查看需求、能力判断及证据、Markdown 方案。方案生成后可以直接通过审核，
也可以填写意见要求修改；Markdown 可直接下载，不生成 DOCX/PDF。

「方案与审核」默认以 Markdown 格式预览，支持标题、列表、引用、表格、任务列表和代码块，
原始 `.md` 下载保持不变。宽表格和代码块可横向滚动。预览不执行原始 HTML 或危险链接，
外部图片不自动加载，可通过「查看图片」手动打开。

页面每 5 秒刷新（浏览器标签页隐藏时暂停）。审核和重试后的状态也会同步到当前详情页。

## PDF 解析

PDF 统一通过 MinerU 云服务解析，使用逐页 `preproc_blocks` 转成 DocumentIR。
本地 PyMuPDF 仅用于文件预检、页面尺寸和页类型诊断，不再负责正文、OCR 或表格提取。
所有 PDF 都会上传至 MinerU，需要配置 `MINERU_API_TOKEN`；没有原生回退路径。由于 PDF
原文会离开本机并上传至 MinerU，接入真实企业文档前应先完成数据合规与敏感信息评估。

### 本地 PDF 解析测试接口

开发环境提供 `POST /dev/pdf/parse`。它不会访问任意服务器路径，而是接收本地上传的 PDF，
运行与 RFP、企业知识库相同的统一解析器，并下载一个 ZIP，内含：

- `*.document-ir.json`：完整 DocumentIR；
- `*.parsed.md`：按 MinerU 页序和 Block 阅读顺序展开的解析文本与表格 Markdown；
- `*.summary.json`：页面类型、实际路由、Block 数量和告警数量摘要。

PowerShell 测试命令：

```powershell
curl.exe -X POST "http://localhost:8000/dev/pdf/parse" `
  -F "file=@E:\edge下载\RAG_PDF文档处理技术方案.pdf;type=application/pdf" `
  -o "pdf-parse-result.zip"
```

接口仅在 `APP_ENV=development/dev/local/test/testing` 时开放，其他环境返回 `404`。上传大小受
`MAX_RFP_UPLOAD_SIZE_BYTES` 限制。解析模型由 `MINERU_MODEL=vlm|pipeline` 控制，旧
`PDF_VLM_ENABLED` 不再生效。

### 企业知识库结构化分块

PDF 知识文档优先使用 `DocumentIR` 分块：Chunker 按 Block 阅读顺序跟踪标题层级，在同一页、
同一章节内合并相邻文本和列表，并从索引中排除页眉、页脚。表格和公式作为独立语义单元；超长
Markdown 表格按数据行拆分，每个分块都会重复表头，Caption 会和紧随的表格或图片一起保留。
超长普通 Block 才回退到 `KNOWLEDGE_CHUNK_SIZE_CHARS` 与
`KNOWLEDGE_CHUNK_OVERLAP_CHARS` 控制的字符切分。DOCX 和旧纯文本继续使用原有按页标记、
空行边界的兼容策略。

用于 Embedding 和证据展示的 Chunk 会带上文档标题、版本及章节路径；Qdrant Payload 额外保存
`page_end`、`section_path`、`block_types`、`source_block_ids` 和 `parent_id`，Capability Agent
也会收到这些结构化检索信息。已存在的 Qdrant Point 不会自动重建；需要删除并重新上传旧知识
文档，才能使用新的结构化分块和 Payload。

## 删除客户、知识库与任务

客户卡片、知识库卡片、RFP 列表及任务详情提供删除按钮，必须二次确认。
本项目没有登录用户管理，这里的用户资料对应「客户管理」。删除接口为：

- `DELETE /customers/{customer_id}`
- `DELETE /knowledge/{document_id}`
- `DELETE /rfps/{rfp_id}`

成功返回 `204`（无响应体），不存在或重复删除返回 `404`。采用逻辑删除：记录和 MinIO 原文件
保留以便人工恢复，当前没有回收站或恢复接口。客户编码仍保留，不能重复使用。
RFP 项目编号只在同一客户的未删除任务中保持唯一；任务删除后可以复用原项目编号。
有关联的未删除任务时不能删除客户（`409`），请先删除其任务，不会隐式级联删除客户数据。

任务删除后，关联详情、方案、Markdown 下载、审核与重试接口均不可访问，待执行工作流会取消。
旧 Kafka 消息会被忽略，后台迟到的成功或失败结果不会复活任务。正在执行的阶段和外部模型请求无法保证即时取消，
可能仍产生费用；中途产生的 MinIO 文件也保留，不做物理清理。

知识库删除会按文档 ID 移除原 Qdrant collection 内的向量，之后不再用于新检索。
索引服务出错返回 `503`，文档保留，可再次删除；正在索引或解析时返回 `409`，需等待完成。
已生成方案以及已保存的历史证据不追溯修改，正在进行的判断可能仍使用此前已取出的证据。

## 失败重试与进度

`POST /rfps/{rfp_id}/retry` 只接受 `FAILED` 的 RFP。它保留已完成阶段，从失败阶段重新排队，
不会重新上传文件。非失败状态、已提交结果但状态不一致时返回 `409`；不存在的 RFP 返回 `404`。
每次手动重试增加 `attempt`，并在同一个数据库事务中创建 Outbox 事件。

| 失败阶段 | 重新投递的事件 |
| --- | --- |
| 文档解析 | `rfp.uploaded` |
| 需求抽取 | `rfp.completed` |
| 能力判断 | `rfp.requirements.extracted` |
| 方案生成 | `rfp.capabilities.evaluated` |

`GET /rfps/{rfp_id}/status` 增加 `stage_label`、`stage_started_at`、`elapsed_seconds`、
`progress_percent`、`attempt`、`is_terminal`。进度按阶段估算，不是 LLM token 进度或剩余时间预测；
人工审核等待时为 95%，通过后为 100%。迁移前的历史阶段时间仅作近似参考。

### Redis 锁看门狗

每个 RFP 工作流阶段使用独立的 Redis 锁。持锁期间，看门狗默认每 30 秒续租一次；对于较短
TTL，续租间隔自动收紧到 TTL 的三分之一。续租通过 Lua 原子校验随机 owner token 后再执行
`EXPIRE`，不会延长已经被其他 Worker 接管的锁。Redis 短暂不可用时，看门狗会在原租约到期前
快速重试；一旦确认 token 不匹配，或直到租约到期仍无法续租，就取消当前业务协程并让 Kafka
保留该消息等待重试。释放锁同样校验 owner token。

`REDIS_LOCK_WATCHDOG_ENABLED` 可以关闭续租，`REDIS_LOCK_WATCHDOG_INTERVAL_SECONDS` 控制正常
续租间隔。该机制避免长时间 OCR/LLM 调用超过固定 TTL，但不替代数据库幂等检查和事务锁。

### Outbox Relay

业务状态与待发送事件会在同一个 MySQL 事务中写入 `outbox_events`。请求或 Worker 提交事务后仍会
尝试即时发送，以降低正常链路延迟；独立 `outbox-relay` 容器持续扫描已到 `available_at` 的
`PENDING` 事件，负责 Kafka 暂时不可用或进程异常时的补偿投递。

Relay 每批使用 `SELECT ... FOR UPDATE SKIP LOCKED` 锁定记录，因此可以安全启动多个实例而不会
同时处理同一行。失败事件按 1、2、4 秒递增做指数退避，达到上限后固定间隔重试，不会因为达到
次数上限而丢弃。相关参数为 `OUTBOX_RELAY_POLL_INTERVAL_SECONDS`、
`OUTBOX_RELAY_BATCH_SIZE`、`OUTBOX_RELAY_INITIAL_BACKOFF_SECONDS` 和
`OUTBOX_RELAY_MAX_BACKOFF_SECONDS`。

该实现是至少一次投递：如果 Kafka 已确认消息、但更新 `PUBLISHED` 的数据库事务提交失败，Relay
会再次发送同一 `event_id`。消费者必须继续以业务状态和 `event_id` 做幂等保护，不能假设消息只
出现一次。

Kafka 消费者使用 `consumed_events` 表按 `(consumer_group, event_id)` 去重。每条有效消息先查询
是否已经消费；业务处理成功后写入消费记录，再提交 Kafka offset。若进程在写入消费记录之后、
提交 offset 之前退出，消息重放时会直接跳过业务处理并提交 offset。消费记录还保存 topic、
partition、offset、event type 和消费时间，便于审计。现有 RFP 阶段状态、数据库唯一约束和 Redis
锁仍然保留为第二道幂等保护。

消费记录不能阻止“外部 LLM 已返回、但业务结果尚未提交”这个窗口内的重复调用；进程此时崩溃，
恢复后仍需重新执行该阶段。若长期运行，应按业务保留周期归档或清理 `consumed_events`，清理周期
必须长于 Kafka 消息保留和可能的人工重放窗口。

## LLM 日志

日志事件为 `llm_request_started`、`llm_request_retrying`、`llm_schema_repair_requested`、`llm_request_completed` 和
`llm_request_failed`，包含 RFP ID、操作、模型、尝试序号、耗时、HTTP 状态、provider request ID
（供应商未返回时为空）、token 用量或错误类型。日志不记录提示词、模型输出、API Key 或供应商错误正文。

`LLM_MAX_RETRIES=2` 表示每次结构化调用最多额外重试两次网络/供应商错误，不等于手动 RFP 重试次数。
超时/连接错误、408、409、429 和 5xx 可以重试，401 不重试。
JSON 结构校验失败时，另外允许**一次结构纠正**：将原任务、原输出和安全的字段错误交回同一模型，
要求返回完整对象，再次执行相同的严格校验。仍不合格则失败；已完成且校验通过的 Chunk 会增量落库，失败重试时先清理这些部分结果。
同一 RFP 的需求抽取最多并发处理 2 个 Chunk（`REQUIREMENT_CHUNK_CONCURRENCY=2`），结果仍按原文 Chunk 顺序写入，避免需求编号跳动。
网络重试预算在初次生成和纠正之间共享：默认最多 4 次 HTTP 请求（首次生成 + 一次纠正 + 两次网络重试），
不会把预算乘成多轮调用；`LLM_MAX_RETRIES=0` 仍允许一次结构纠正。额外调用可能产生模型费用。
单次超时仍由 `LLM_TIMEOUT_SECONDS` 控制，多次尝试的总耗时可能超过它。

结构错误日志包含 `validation_error_count` 和 `validation_errors` 中的 `loc`（字段路径与数组下标）、
`type`、`msg`（安全错误原因），最多显示 20 条，截断时 `validation_errors_truncated=true`。
非 schema 字段名显示为 `<unknown_field>`，防止模型把正文写入键名后泄漏到日志。
`schema_repair_attempt=0/1` 区分初次生成与纠正，`finish_reason` 和 token 用量帮助排查输出截断。
RFP 状态接口仍只显示简短错误摘要；详细字段错误请查看对应 Worker 日志。

已有失败任务不会因升级自动重试。更新容器后，在工作台打开该 RFP 并点击重试，即可使用新逻辑。

## 本地前端开发

前端源代码位于 `web/src`，使用 React + TypeScript + Vite。Node 要求 20.19+ 或 22.12+。
在 `web` 目录执行 `npm ci`、`npm run dev`，开发代理会连接本机 8000 端口的 API。
如果容器 Web 已占用 3000，可用 `npm run dev -- --port 3001`。

- `npm run build`：TypeScript 检查与生产构建。

当前没有身份验证，仅用于可信的个人开发环境，请勿直接暴露到公网。

## 常用命令

```powershell
# 查看所有服务
docker compose ps

# 查看应用日志
docker compose logs -f api outbox-relay rfp-worker requirement-worker capability-worker proposal-worker

# 重新构建应用镜像
docker compose build api

# 停止服务但保留数据
docker compose down
```

如需同时删除 MySQL、Kafka、MinIO、Qdrant 和 Redis 的本地数据卷，可执行
`docker compose down -v`。该命令会永久删除本地项目数据。

## MinerU PDF 解析

PDF 统一使用 MinerU 云服务，输出仍是 DocumentIR v1.0。在 `.env` 设置：

```dotenv
MINERU_API_TOKEN=你的Token
MINERU_MODEL=vlm
MINERU_WAIT_SECONDS=1800
```

`MINERU_MODEL` 仅支持 `vlm` 或 `pipeline`，默认使用 `vlm`。

该方案同时适用于 RFP、企业知识库及 `/dev/pdf/parse`；DOCX/Markdown 不受影响。
转换使用 `layout.json` 的逐页 `preproc_blocks`，不采用可能错误跨页合并的
`para_blocks` 或 `full.md`。保留页码、缩放到源页面尺寸的 bbox、原始块和表格 HTML；
简单表格生成 Markdown，含合并单元格的复杂表格保留嵌入 HTML。
原始图片与 JSON ZIP 保存于 `LOCAL_ARTIFACT_EXPORT_DIR/mineru/<document-id>/<run>/result.zip`，
DocumentIR metadata 记录本地归档位置；图片路径是 ZIP 内引用，不是可公开访问的 URL。
这些原始 ZIP 尚未单独上传 MinIO，也不随知识库删除自动清理。

远程解析失败会明确报错，原生解析后端已移除；旧 `PDF_BACKEND`、`PDF_VLM_ENABLED`
及本地 OCR/Layout 配置不再生效。
云服务输出仍可能存在错字；本适配器并不修复 OCR 错字，也不自动拼接跨页续表。

容器部署需更新应用镜像并重新创建相关服务（无需重建 web 或数据库）：

```powershell
docker compose build api
docker compose up -d --force-recreate api rfp-worker knowledge-worker
```
