# DealFlow RAG 大规模评测集生成指南

## 1. 文档用途

本文件是交给 AI 执行的数据集建设说明。目标是为 DealFlow 当前的父子 Chunk、Dense + BM25、RRF 和 Cross Encoder 重排链路构造一套可重复、可标注、具有真实检索难度的离线评测集。

本次只生成评测数据，不修改生产 RAG 逻辑。发现评测器不支持某种标签时，应记录问题并停止扩大数据，不得自行改变检索语义。

## 2. 开始前必须完成的检查

执行者必须先阅读以下文件，确认当前实现没有变化：

```text
app/rag/evaluation.py
app/rag/evaluate_cli.py
app/rag/evaluation_corpus.py
app/rag/hierarchical.py
evals/retrieval/business_queries.jsonl
evals/retrieval/business_corpus.json
evals/retrieval/README.md
```

同时执行：

```powershell
git status --short
git log -3 --oneline
```

工作区可能存在用户尚未提交的其他修改。只能暂存和提交本任务新增的数据集文件，不得覆盖、格式化或提交无关文件。

## 3. 建设目标

第一版大型评测集固定为：

| 项目 | 目标值 |
|---|---:|
| 知识文档 | 20 份 |
| 知识正文 | 约 298,000 Token，允许 ±10% |
| Parent Chunk | 目标 250～350 个 |
| Child Chunk | 目标 800～1,200 个 |
| Qdrant Point | 与 Child 数量一致 |
| Query | 150 条 |
| Dev Query | 105 条 |
| Test Query | 45 条 |
| 多证据 Query | 至少 15 条 |
| Hard Query | 30 条 |
| Critical Query | 45 条 |

这里的 Token 必须使用项目配置的 `cl100k_base` 统计，不能用字符数估算后直接声称达标。

## 4. 数据集目录

所有新文件放在独立目录，不覆盖现有 20 条冒烟样本：

```text
evals/retrieval/large_v1/
├── corpus.json
├── catalog.md
├── generation-log.md
├── knowledge/
│   ├── 01-platform-overview-current.md
│   ├── 02-platform-overview-legacy.md
│   └── ...
├── queries-dev.jsonl
├── queries-test.jsonl
└── validation-summary.json
```

`catalog.md` 记录每份文档的主题、版本、目标 Token 和干扰关系。`generation-log.md` 记录生成批次、人工修订点和已知限制。`validation-summary.json` 由校验步骤生成，不得手工伪造。

## 5. 本轮文件格式约束

核心检索评测的 20 份文档全部使用 UTF-8 Markdown。

原因：当前 Markdown 适配器能稳定保留标题形成的 `section_path`；当前 DOCX 适配器主要按段落处理，尚未可靠恢复 Word 标题层级；PDF 还会引入 OCR 和版面识别变量。本轮目的是单独测量 Chunk、召回和重排质量，不应把解析误差混入主指标。

PDF、DOCX、扫描件应在后续建立独立的“跨格式鲁棒性评测集”，不能用转换后的重复内容混入本评测集，否则会制造重复证据并污染排序指标。

## 6. 20 份知识文档规划

使用虚构的 DealFlow 企业产品资料。所有事实只需在数据集内部一致，不得复制真实公司的私有资料或受版权保护的完整文档。

| 编号 | 文件主题 | 目标 Token | 主要干扰关系 |
|---:|---|---:|---|
| 01 | 当前平台总览与套餐边界 | 18,000 | 与 02 的旧版本冲突 |
| 02 | 历史平台总览与旧套餐 | 14,000 | 旧 SLA、旧容量、已下线能力 |
| 03 | 身份认证与访问控制 | 14,000 | SAML、OIDC、SCIM、MFA、RBAC 相近概念 |
| 04 | 历史 IAM 与迁移说明 | 12,000 | 旧协议版本和迁移截止时间 |
| 05 | 加密、密钥和数据保护 | 15,000 | 平台密钥、专属密钥、客户管理密钥 |
| 06 | 审计日志与安全运营 | 15,000 | 审计日志、应用日志、访问日志保留期不同 |
| 07 | 合规、隐私与认证 | 18,000 | ISO、SOC、GDPR、等保适用范围不同 |
| 08 | 可用性与服务等级 | 16,000 | 99.9%、99.95%、99.99% 套餐差异 |
| 09 | 备份、恢复与灾难恢复 | 16,000 | 备份周期、保留期、RTO、RPO 易混淆 |
| 10 | SaaS、专属租户与本地部署 | 15,000 | 标准能力与定制能力边界 |
| 11 | 网络连接与安全边界 | 14,000 | IP 白名单、VPN、专线、PrivateLink |
| 12 | 数据驻留与跨区域复制 | 14,000 | 主数据、备份、日志所在区域不同 |
| 13 | API、Webhook 与服务账号 | 16,000 | 速率限制、幂等、鉴权方式 |
| 14 | CRM、ERP 与协作平台集成 | 16,000 | 原生连接器与专业服务集成区别 |
| 15 | 性能、容量与上传限制 | 14,000 | 并发用户、RPS、文件大小、页数 |
| 16 | RFP 与 Proposal 工作流 | 15,000 | 草稿、审核、批准、导出状态不同 |
| 17 | 知识库、Chunk 与增量更新 | 15,000 | MySQL、MinIO、Qdrant 职责容易混淆 |
| 18 | 支持计划与事件响应 | 14,000 | P1/P2/P3 响应时间和服务时段不同 |
| 19 | 实施、迁移与培训服务 | 14,000 | 标准交付与付费专业服务区别 |
| 20 | 限制项、弃用项与路线图 | 13,000 | “已支持”“定制支持”“计划支持”干扰 |

目标总量为约 298,000 Token。单份文档允许偏差 ±15%，总量偏差必须控制在 ±10%。

## 7. Markdown 文档结构规范

每份文件必须满足：

1. 只有一个一级标题，且一级标题必须唯一。
2. 使用二级、三级标题组织业务章节。
3. 每个二级章节聚焦一个可独立检索的主题。
4. 每个章节包含明确事实，而不是宣传性空话。
5. 数字、版本、限制、套餐、例外条件必须写清楚。
6. 可以使用表格和列表，但关键事实也要有自然语言说明。
7. 不得把评测 Query 原句复制进正文。
8. 同一事实不能在大量文档中无差别重复。

示例：

```markdown
# DealFlow Identity and Access Control Guide

## Enterprise Single Sign-On

Enterprise tenants can connect an identity provider using SAML 2.0 or OpenID Connect. The standard Business plan supports OpenID Connect but does not include SAML metadata rotation automation.

### Certificate rotation

SAML signing certificates can overlap for seven days during rotation. Automatic metadata refresh runs every six hours.
```

章节标题必须稳定。一旦开始标注 Query，不得随意重命名标题，否则 `section_path` 标签会失效。

## 8. Hard Negative 设计

大型数据集的重点不是增加文字量，而是增加“看起来相关但答案不正确”的内容。至少设计以下干扰：

### 8.1 数字干扰

```text
审计日志：180 天
应用运行日志：30 天
备份：35 天
安全事件摘要：365 天
```

Query 询问审计日志时，其他三个数字都是 Hard Negative。

### 8.2 套餐干扰

```text
Business：99.9% SLA
Enterprise：99.95% SLA
Dedicated：99.99% SLA
```

Query 必须写明套餐，不能把所有 SLA 章节都标成同等相关。

### 8.3 当前版本与历史版本

历史文档必须明确包含：

```text
Document status: superseded
Effective period: 2024-01-01 to 2025-06-30
Replaced by: 当前文档标题
```

部分 Query 应明确询问“当前”“最新”“现行”，相关标签只指向当前文档。另一些 Query 可以询问历史迁移规则，并把历史文档标为相关。

### 8.4 能力状态干扰

正文中要明确区分：

```text
标准支持
仅 Enterprise 支持
需要定制开发
专业服务交付
路线图计划
明确不支持
已经弃用
```

“路线图计划”不能被写成当前已经支持。

### 8.5 概念相近干扰

必须覆盖：

```text
RTO 与 RPO
认证日志与审计日志
数据驻留与备份区域
API 限流与并发用户数
身份认证与用户同步
原生连接器与 REST API 集成
Parent 正文与 Child 向量
删除、归档与停用
```

## 9. Query 数量和分布

生成 150 条 Query，固定分布如下：

| 类型 | 数量 | 说明 |
|---|---:|---|
| 直接业务需求 | 55 | 含明确产品能力或限制 |
| 同义改写 | 25 | 正文不出现 Query 原句 |
| Hard Negative 区分 | 25 | 必须依靠数字、套餐、版本或状态区分 |
| 多证据查询 | 15 | 至少需要两个不同章节 |
| 中英混合、缩写 | 15 | SLA、RTO、RPO、SAML、SCIM 等 |
| 精确数字和期限 | 15 | 保留期、响应时间、容量或频率 |
| 合计 | 150 | 每条只归入一个主要类型 |

难度固定为：

```text
easy:   45
medium: 75
hard:   30
```

`critical=true` 固定 45 条，优先覆盖安全、合规、数据驻留、灾备、关键容量和删除一致性。

## 10. 当前 Query JSONL 格式

每行必须是一个完整 JSON 对象，不能使用 Markdown 代码围栏，不能跨行。

```json
{"query_id":"iam-saml-current-001","query":"当前 Enterprise 套餐必须支持 SAML 2.0 单点登录。","category":"security","difficulty":"medium","critical":true,"relevant":[{"title":"DealFlow Identity and Access Control Guide","section_path":["DealFlow Identity and Access Control Guide","Enterprise Single Sign-On"],"relevance":3}]}
```

字段规则：

| 字段 | 规则 |
|---|---|
| `query_id` | 全局唯一，小写 kebab-case，语义稳定 |
| `query` | 真实 RFP 需求或采购问题，不写答案 |
| `category` | 使用统一小写分类 |
| `difficulty` | `easy`、`medium` 或 `hard` |
| `critical` | 布尔值 |
| `relevant` | 至少一个相关标签 |
| `title` | 必须与 `corpus.json` 中的 title 完全一致 |
| `section_path` | 必须与 Markdown 标题层级完全一致 |
| `relevance` | 正整数，推荐 1～3 |

相关性等级：

```text
3：直接回答 Query 的核心证据
2：回答所必需的补充证据
1：有帮助但不影响核心结论
```

同一个 Query 不要为了提高 Recall 人为标注大量弱相关章节。

## 11. 当前评测器的重要限制

当前 `load_evaluation_cases` 要求每条 Query 至少有一个 `relevant` 标签。因此本轮不得加入无答案 Query，也不能使用空数组表示无答案。

无答案评测应等待评测器正式支持 `expected_no_answer` 和相应指标后单独建设。不得用不存在的标题或伪造章节模拟无答案，否则会把标签错误当成系统错误。

当前匹配逻辑是：

```text
candidate.title 大小写无关相等
并且
candidate.section_path 以标签 section_path 开头
```

因此：

- 文档 title 必须唯一；
- 不要使用空 `section_path`；
- 标签最好定位到二级或三级标题；
- Query 标注后不得修改标题路径；
- 一个标签应尽量只匹配一个 Parent。

## 12. Corpus Manifest 格式

`corpus.json` 示例：

```json
{
  "documents": [
    {
      "document_key": "dealflow-iam-current-v2",
      "path": "knowledge/03-identity-access-current.md",
      "title": "DealFlow Identity and Access Control Guide",
      "category": "security",
      "version": "2.0"
    }
  ]
}
```

要求：

- `document_key` 全局唯一，修改显示标题时也保持稳定；
- `path` 相对于 `corpus.json`；
- `title` 与对应 Markdown 一级标题一致；
- `category` 使用小写 kebab-case；
- 历史文档必须有明确版本号；
- Manifest 必须包含且只包含这次评测的 20 份文件。

## 13. Dev/Test 划分

最终生成：

```text
queries-dev.jsonl   105 条
queries-test.jsonl   45 条
```

划分必须按 category、difficulty、query type 和 critical 分层，不能简单取前 105 条。

同一事实的轻微改写不能分别进入 Dev 和 Test，否则会造成信息泄漏。例如“SAML 单点登录”和“通过 SAML 接入 IdP”如果证据和意图完全相同，应放在同一集合。

Test 集生成并检查完成后冻结。后续调参只能查看 Dev 的逐 Query 结果，不能根据 Test 失败项持续修改查询或相关标签。

## 14. 推荐生成流程

### 阶段 A：建立事实矩阵

先创建 `catalog.md`，为每个领域定义：

```text
事实 ID
当前事实
适用套餐
生效版本
证据文档和章节
容易混淆的错误事实
是否用于 Critical Query
```

没有事实矩阵之前，不得直接批量生成 150 条 Query。

### 阶段 B：分批生成知识文档

每批生成 4～5 份文档。每批完成后：

1. 检查标题唯一性；
2. 检查事实是否与 catalog 一致；
3. 统计 Token；
4. 运行结构化切分；
5. 检查 Parent 和 Child 数量；
6. 提交一次 Git Commit。

建议提交格式：

```text
testdata(rag): add security evaluation corpus
testdata(rag): add operations evaluation corpus
testdata(rag): add integration evaluation corpus
```

### 阶段 C：生成 Dev Query

先生成 105 条 Dev Query。每条 Query 必须从事实矩阵选择目标事实，再进行自然语言改写，不能先写问题再临时寻找答案。

### 阶段 D：生成并冻结 Test Query

Test Query 使用未被 Dev 覆盖的事实组合、表达方式或干扰关系。生成后单独提交，后续不得因模型结果不好而偷偷修改标签。

### 阶段 E：自动校验

至少检查：

```text
文件数量
Token 总量
Query 数量
query_id 唯一性
标题唯一性
Manifest 路径存在
JSONL 每行可解析
relevance 为正整数
每个标签能解析到真实章节
每个 Query 至少一个相关标签
Dev/Test 无重复和高相似泄漏
Parent/Child 数量达到目标
```

## 15. 标签校验方法

不要只用字符串搜索判断 `section_path`。必须调用项目真实解析和切分代码：

```text
DocumentParser
MarkdownStructureAdapter
HierarchicalKnowledgeChunker
```

校验器应为每个标签输出匹配 Parent 数量：

```text
query_id
label title
label section_path
matched_parent_count
matched_parent_ids
```

验收要求：

- 每个相关标签至少匹配一个 Parent；
- 建议 90% 以上标签只匹配一个 Parent；
- 匹配多个 Parent 时必须人工确认这些 Parent 都属于同一目标章节；
- 匹配为 0 时必须修正文档标题、章节路径或标签，不能跳过。

## 16. Query 质量要求

每条 Query 必须满足：

1. 像真实 RFP 条款、采购问卷或技术澄清问题。
2. 不包含“根据文档第几节”等人工提示。
3. 不直接复制章节标题。
4. 不把答案写进问题之外的元数据。
5. 至少一部分 Query 使用业务语言而非产品术语。
6. 数字 Query 必须保留单位、比较关系和适用范围。
7. 多证据 Query 的相关标签必须覆盖所有必要证据。
8. Hard Query 必须能说明为什么某个相似章节不是正确答案。

不合格示例：

```text
请检索 Identity and Access Management 章节。
```

合格示例：

```text
员工从企业目录离职后，账号应在无需管理员手工操作的情况下自动停用。
```

## 17. 防止数据集虚高

如果 Dense、Hybrid 和 Reranker 在 Dev/Test 上继续全部满分，不得直接宣布检索质量优秀。应优先检查：

- 文档数量是否真的达到 20；
- 是否每个主题只有一个明显章节；
- Query 是否复制了正文关键词；
- 是否缺少旧版本和近似数字；
- Top 5 是否因为 Parent 总数太少而必然命中；
- 多证据 Query 是否真正需要两个章节；
- 标签是否过宽，例如只标一级标题。

第一版合理目标不是满分，而是让不同方案产生可解释差异。可接受的初始表现大致为：

```text
Dense MRR@5：             0.65～0.85
Hybrid MRR@5：            0.70～0.90
Hybrid + Reranker MRR@5： 0.75～0.93
Recall@5：                0.75～0.95
```

该范围只是数据难度检查，不是最终质量门禁。

## 18. 运行评测

Dev：

```powershell
docker compose -f docker-compose.rag-eval.yml run --rm rag-eval `
  python -m app.rag.evaluate_cli `
  --isolated `
  --mode all `
  --dataset evals/retrieval/large_v1/queries-dev.jsonl `
  --corpus-manifest evals/retrieval/large_v1/corpus.json `
  --top-k 5 `
  --candidate-k 30 `
  --report-dir evals/retrieval/reports/large-v1-dev
```

Test：

```powershell
docker compose -f docker-compose.rag-eval.yml run --rm rag-eval `
  python -m app.rag.evaluate_cli `
  --isolated `
  --mode all `
  --dataset evals/retrieval/large_v1/queries-test.jsonl `
  --corpus-manifest evals/retrieval/large_v1/corpus.json `
  --top-k 5 `
  --candidate-k 30 `
  --report-dir evals/retrieval/reports/large-v1-test
```

注意：当前 Compose 将报告目录挂载到宿主机。使用 `run` 覆盖命令时，必须把 `python ...` 作为服务命令传入，不能把整个命令写成一个带引号的字符串。

## 19. 最终验收标准

交付前必须同时满足：

- 20 份知识文档全部存在且在 Manifest 中；
- 总 Token 为 268,200～327,800；
- Parent 为 250～350；
- Child 为 800～1,200；
- Dev 正好 105 条，Test 正好 45 条；
- Easy 45、Medium 75、Hard 30；
- Critical 正好 45；
- 多证据 Query 至少 15 条；
- 所有 Query ID 唯一；
- 所有相关标签至少匹配一个 Parent；
- Dev/Test 无重复意图泄漏；
- Dense、Hybrid、Hybrid + Reranker 均可完整运行；
- 生成 `summary.json`、`query-details.jsonl` 和 `report.html`；
- 没有覆盖或提交用户的无关修改；
- 每批修改都已经提交本地 Git。

## 20. 可直接交给新对话 AI 的任务指令

将下面内容连同本文件路径交给新对话：

```text
请读取并严格执行：
E:\study2\LLM Internship\RFP-Agent\docs\rag\rag-evaluation-dataset-generation-guide.md

在 evals/retrieval/large_v1 下构造 DealFlow RAG 大规模评测集。先检查当前代码和 Git 工作区，再建立事实矩阵，按批次生成 20 份约 30 万 Token 的 Markdown 企业知识文档，随后生成 105 条 Dev Query 和 45 条冻结 Test Query，并使用项目真实 Parser、结构化适配器和父子 Chunker 完成自动校验。

必须严格匹配当前 corpus manifest 与 JSONL Schema；不得生成无答案 Query；不得修改生产 RAG 逻辑；不得覆盖或提交工作区中的无关修改。每完成一个批次都要进行本地 Git Commit。最后运行隔离评测，报告文档数、Token、Parent、Child、Query、标签匹配、Dev/Test 泄漏检查和三种检索模式的指标，并给出所有提交哈希。
```
