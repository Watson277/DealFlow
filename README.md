# DealFlow RFP Agent

DealFlow 是一个基于 FastAPI、Kafka 和多个异步 Agent Worker 的 RFP 处理练手项目。

## 使用 Docker Compose 启动

1. 创建本地环境文件：

   ```powershell
   Copy-Item .env.example .env
   ```

2. 在 `.env` 中填写智谱 API Key：

   ```dotenv
   LLM_API_KEY=你的智谱_API_Key
   ```

   默认配置通过智谱的 OpenAI-compatible Chat Completions API 调用
   `glm-5.3-flash`，并使用 `embedding-3`（1024 维）生成知识库向量。也可以用
   `ZAI_API_KEY` 作为密钥变量名；`OPENAI_API_KEY` 仅作为旧配置的兼容别名。
   基础设施密码仅用于本地开发时可以保留默认值。

   未配置密钥时，API 与 RFP 文件解析 Worker 仍可启动；需求抽取、能力判断和 Proposal
   Worker 会输出说明后停止，以避免无意义的重启循环。

   从原先 1536 维向量配置升级时，默认 Qdrant collection 会切换到
   `dealflow_knowledge_glm`。旧 collection 不会被删除，但企业知识文档需要重新上传索引。

3. 构建并启动完整系统：

   ```powershell
   docker compose up --build -d
   ```

Compose 会依次启动 MySQL、Redis、Kafka、Qdrant 和 MinIO，创建 Kafka topics 与 MinIO
bucket，执行 Alembic 数据库迁移，最后启动 FastAPI、四个 Worker 和 React Web 容器。

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

## PDF 原生解析、OCR 与版面分析

PDF 进入后续工作流前会先完成文件预检，拒绝损坏、加密、无页面或超过
`PDF_MAX_PAGES` 的文件。解析器使用 PyMuPDF 提取原生文本块、图片位置、字体信息和 bbox，
并按页计算有效字符数、乱码率以及文本/图片覆盖率，得到 `text`、`scanned`、`mixed` 或
`empty` 页面类型。结构化结果通过 `ParsedDocument.pdf` 提供，原有带页码标记的纯文本输出保持兼容。

路由粒度严格是单页。`text` 页使用 PyMuPDF 原生文字、图片与 `find_tables`；`scanned` 和
`mixed` 页先渲染，再通过 OpenCV Layout Detection 划分文字区、表格区和图片区。文字区调用
Tesseract 区域 OCR，表格区使用网格 TSR 后逐单元格 OCR，图片区可选择调用兼容
Chat Completions 的 VLM。VLM 默认关闭，只有显式设置 `PDF_VLM_ENABLED=true` 才会把检测出的
图片裁剪发送到外部模型。相关参数位于 `.env` 的 `PDF_LAYOUT_DETECTION_*`、`PDF_OCR_*`、
`PDF_TSR_*` 和 `PDF_VLM_*`。

多通道结果先经过 Block Fusion，再生成 `PageIR`：通过 bbox、IoU 与文本相似度消除 Native/OCR
重复，表格结构覆盖表格区域内的普通文字，冲突时优先保留 `native text > OCR`。之后共享版面
分析器恢复多栏阅读顺序，并标记 `title`、`list`、`header`、`footer`、`footnote` 与
`caption`。全部页面处理完成后，才汇总 `page_types[]` 得到 `DocumentIR.document_type`；每页实际
路由和融合统计也会写入 IR metadata，便于排障和追溯。

页提取支持受控多进程并行。达到 `PDF_PAGE_PARALLEL_MIN_PAGES` 后，页面按轮询方式分配给最多
`PDF_PAGE_WORKERS` 个进程；每个进程独立打开 PDF，避免跨线程共享 PyMuPDF 对象。页面即使乱序
完成，也会在父进程中按 `page_number` 排序后再执行文档级版面分析。短文档、自定义 Provider、
启用 VLM 或进程池异常时自动使用串行路径。并行状态和降级原因记录在
`DocumentIR.metadata.page_extraction`。

### 本地 PDF 解析测试接口

开发环境提供 `POST /dev/pdf/parse`。它不会访问任意服务器路径，而是接收本地上传的 PDF，
运行与 RFP、企业知识库相同的统一解析器，并下载一个 ZIP，内含：

- `*.document-ir.json`：完整 DocumentIR；
- `*.parsed.md`：按页组织的可读解析文本和表格 Markdown；
- `*.summary.json`：页面类型、实际路由、Block 数量和告警数量摘要。

PowerShell 测试命令：

```powershell
curl.exe -X POST "http://localhost:8000/dev/pdf/parse" `
  -F "file=@E:\edge下载\RAG_PDF文档处理技术方案.pdf;type=application/pdf" `
  -o "pdf-parse-result.zip"
```

接口仅在 `APP_ENV=development/dev/local/test/testing` 时开放，其他环境返回 `404`。上传大小受
`MAX_RFP_UPLOAD_SIZE_BYTES` 限制。VLM 是否调用仍由 `PDF_VLM_ENABLED` 控制。

## 删除客户、知识库与任务

客户卡片、知识库卡片、RFP 列表及任务详情提供删除按钮，必须二次确认。
本项目没有登录用户管理，这里的用户资料对应「客户管理」。删除接口为：

- `DELETE /customers/{customer_id}`
- `DELETE /knowledge/{document_id}`
- `DELETE /rfps/{rfp_id}`

成功返回 `204`（无响应体），不存在或重复删除返回 `404`。采用逻辑删除：记录和 MinIO 原文件
保留以便人工恢复，当前没有回收站或恢复接口。客户编码仍保留，不能重复使用。
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

## LLM 日志

日志事件为 `llm_request_started`、`llm_request_retrying`、`llm_schema_repair_requested`、`llm_request_completed` 和
`llm_request_failed`，包含 RFP ID、操作、模型、尝试序号、耗时、HTTP 状态、provider request ID
（供应商未返回时为空）、token 用量或错误类型。日志不记录提示词、模型输出、API Key 或供应商错误正文。

`LLM_MAX_RETRIES=2` 表示每次结构化调用最多额外重试两次网络/供应商错误，不等于手动 RFP 重试次数。
超时/连接错误、408、409、429 和 5xx 可以重试，401 不重试。
JSON 结构校验失败时，另外允许**一次结构纠正**：将原任务、原输出和安全的字段错误交回同一模型，
要求返回完整对象，再次执行相同的严格校验。仍不合格则失败，需求抽取不会写入部分或不合格的结果。
网络重试预算在初次生成和纠正之间共享：默认最多 4 次 HTTP 请求（首次生成 + 一次纠正 + 两次网络重试），
不会把预算乘成多轮调用；`LLM_MAX_RETRIES=0` 仍允许一次结构纠正。额外调用可能产生模型费用。
单次超时仍由 `LLM_TIMEOUT_SECONDS` 控制，多次尝试的总耗时可能超过它。

结构错误日志包含 `validation_error_count` 和 `validation_errors` 中的 `loc`（字段路径与数组下标）、
`type`、`msg`（安全错误原因），最多显示 20 条，截断时 `validation_errors_truncated=true`。
非 schema 字段名显示为 `<unknown_field>`，防止模型把正文写入键名后泄漏到日志。
`schema_repair_attempt=0/1` 区分初次生成与纠正，`finish_reason` 和 token 用量帮助排查输出截断。
RFP 状态接口仍只显示简短错误摘要；详细字段错误请查看对应 Worker 日志。

已有失败任务不会因升级自动重试。更新容器后，在工作台打开该 RFP 并点击重试，即可使用新逻辑。

## 本地前端开发与测试

前端源代码位于 `web/src`，使用 React + TypeScript + Vite。Node 要求 20.19+ 或 22.12+。
在 `web` 目录执行 `npm ci`、`npm run dev`，开发代理会连接本机 8000 端口的 API。
如果容器 Web 已占用 3000，可用 `npm run dev -- --port 3001`。

- `npm run build`：TypeScript 检查与生产构建。
- `npm test`：浏览器交互测试，接口响应仅在测试中拦截，不访问真实 LLM、不写入业务数据。
  Windows 使用本机 Edge；其他系统先运行 `npx playwright install chromium`。
- 根目录 `uv run pytest -q -m "not integration"`：不依赖基础设施的后端测试。
- 设置 `RUN_INTEGRATION_TESTS=1` 后执行 `uv run pytest -q tests/integration/test_rfp_retry.py`：
  使用本机 MySQL 验证重试与恢复，仅清理该测试创建的记录，不发出 Kafka/LLM 请求。

当前没有身份验证，仅用于可信的个人开发环境，请勿直接暴露到公网。

## 常用命令

```powershell
# 查看所有服务
docker compose ps

# 查看应用日志
docker compose logs -f api rfp-worker requirement-worker capability-worker proposal-worker

# 重新构建应用镜像
docker compose build api

# 停止服务但保留数据
docker compose down
```

如需同时删除 MySQL、Kafka、MinIO、Qdrant 和 Redis 的本地数据卷，可执行
`docker compose down -v`。该命令会永久删除本地项目数据。
