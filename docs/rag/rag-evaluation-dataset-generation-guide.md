# DealFlow RAG 评测数据集生成指南

## 1. 目标

本文件用于指导另一个 AI 为 DealFlow 构造一套较大规模、可重复、具有真实业务难度的 RAG 离线评测数据集。

AI 只负责生成两类源数据：

1. 企业知识库文档；
2. 与知识库事实对应的评测 Query 和相关性标签。

AI 不负责设计 Parent Chunk、Child Chunk、Chunk ID、向量或 Qdrant Point。文档解析、结构化切分、Embedding 和向量入库全部由项目现有代码完成。

```text
AI 生成的数据
  ├─ Markdown 企业知识文档
  └─ Query + 相关章节标签
             │
             ▼
项目运行时自动处理
  文档解析 → 结构化文档 → 父子切分 → Embedding → Qdrant → 检索评测
```

本任务不能为了获得特定 Chunk 数量而调整段落长度、标题数量或文档结构。Chunk 数量只能作为运行后的观测结果，不能作为数据生成目标。

## 2. 开始前检查

先阅读以下文件，确认当前数据格式和评测接口没有发生变化：

```text
app/rag/evaluation.py
app/rag/evaluate_cli.py
app/rag/evaluation_corpus.py
evals/retrieval/business_queries.jsonl
evals/retrieval/business_corpus.json
evals/retrieval/README.md
```

然后执行：

```powershell
git status --short
git log -3 --oneline
```

工作区中可能存在用户尚未提交的修改。只允许暂存和提交本任务创建的文件，不得覆盖、格式化、回滚或提交无关文件。

## 3. AI 的职责边界

### 3.1 必须完成

- 建立统一且自洽的虚构企业事实体系；
- 编写 20 份 Markdown 企业知识文档；
- 在文档中加入版本、套餐、数值和能力状态等真实检索干扰；
- 生成 105 条 Dev Query 和 45 条 Test Query；
- 为每条 Query 标注能够回答问题的真实文档章节；
- 校验文件、标题、事实、JSONL、标签和 Dev/Test 隔离；
- 使用当前项目运行完整检索评测；
- 分批进行本地 Git Commit。

### 3.2 禁止完成

- 不手工创建 Parent 或 Child；
- 不预测或编造 Parent ID、Child ID；
- 不生成向量文件；
- 不直接写入 Qdrant；
- 不把 Chunk 数量设为验收指标；
- 不根据理想 Chunk 边界反向编写文档；
- 不修改生产 RAG、Chunker、Embedding 或 Reranker 逻辑；
- 不为了提高指标而降低问题难度或扩大相关标签。

如果评测失败，应先区分是源数据问题还是系统问题。只有源数据问题可以在本任务内修正；系统问题只记录，不自行修改生产代码。

## 4. 数据集规模

第一版数据集的源数据规模固定为：

| 项目 | 目标 |
|---|---:|
| Markdown 知识文档 | 20 份 |
| 知识正文 | 约 298,000 Token，允许 ±10% |
| Query 总数 | 150 条 |
| Dev Query | 105 条 |
| Test Query | 45 条 |
| 多证据 Query | 至少 15 条 |
| Hard Query | 30 条 |
| Critical Query | 45 条 |

Token 必须使用项目配置的 `cl100k_base` 计算。不能用字符数、字数或文件大小代替 Token 统计。

Parent、Child 和 Qdrant Point 的实际数量可以在评测完成后记录，但不规定期望范围，也不影响数据集验收。

## 5. 交付目录

所有新文件放入独立目录，不覆盖已有的 20 条小型评测样本：

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

各文件作用：

| 文件 | 作用 |
|---|---|
| `knowledge/*.md` | 真正参与解析和检索的企业知识正文 |
| `corpus.json` | 告诉评测程序需要加载哪些知识文档 |
| `catalog.md` | 事实矩阵、文档规划和干扰关系 |
| `queries-dev.jsonl` | 可用于调试和调参的 Query |
| `queries-test.jsonl` | 冻结的最终测试 Query |
| `generation-log.md` | 生成批次、人工修订和已知限制 |
| `validation-summary.json` | 自动校验统计，不得手工伪造 |

## 6. 文件格式

本轮 20 份知识文档全部使用 UTF-8 Markdown。

这是为了单独评估知识内容、结构化切分和检索效果。PDF、DOCX 和扫描件会额外引入版面分析、OCR 和标题恢复误差，应当在后续单独建设“跨格式解析鲁棒性评测集”。不要把相同内容转换成多个格式后放入本数据集，否则会产生重复证据。

## 7. 知识文档规划

使用完全虚构的 DealFlow 企业产品资料。不得复制真实公司的私有资料，也不得复制受版权保护的完整文档。

| 编号 | 文件主题 | 目标 Token | 主要干扰关系 |
|---:|---|---:|---|
| 01 | 当前平台总览与套餐边界 | 18,000 | 与 02 的旧版本冲突 |
| 02 | 历史平台总览与旧套餐 | 14,000 | 旧 SLA、旧容量、已下线能力 |
| 03 | 身份认证与访问控制 | 14,000 | SAML、OIDC、SCIM、MFA、RBAC |
| 04 | 历史 IAM 与迁移说明 | 12,000 | 旧协议版本和迁移截止时间 |
| 05 | 加密、密钥和数据保护 | 15,000 | 平台密钥、专属密钥、客户管理密钥 |
| 06 | 审计日志与安全运营 | 15,000 | 不同日志类型的保留期 |
| 07 | 合规、隐私与认证 | 18,000 | ISO、SOC、GDPR、等保的适用范围 |
| 08 | 可用性与服务等级 | 16,000 | 不同套餐的 SLA |
| 09 | 备份、恢复与灾难恢复 | 16,000 | 备份周期、保留期、RTO、RPO |
| 10 | SaaS、专属租户与本地部署 | 15,000 | 标准能力和定制能力边界 |
| 11 | 网络连接与安全边界 | 14,000 | IP 白名单、VPN、专线、PrivateLink |
| 12 | 数据驻留与跨区域复制 | 14,000 | 主数据、备份和日志所在区域 |
| 13 | API、Webhook 与服务账号 | 16,000 | 速率限制、幂等和鉴权方式 |
| 14 | CRM、ERP 与协作平台集成 | 16,000 | 原生连接器和专业服务集成 |
| 15 | 性能、容量与上传限制 | 14,000 | 并发、RPS、文件大小和页数 |
| 16 | RFP 与 Proposal 工作流 | 15,000 | 草稿、审核、批准和 Markdown 导出 |
| 17 | 知识库与增量更新 | 15,000 | MySQL、MinIO、Qdrant 的职责和删除一致性 |
| 18 | 支持计划与事件响应 | 14,000 | P1、P2、P3 响应时间和服务时段 |
| 19 | 实施、迁移与培训服务 | 14,000 | 标准交付和付费专业服务 |
| 20 | 限制项、弃用项与路线图 | 13,000 | 已支持、定制支持和计划支持 |

目标总量约为 298,000 Token。单份文档允许偏差 ±15%，总量必须位于 268,200～327,800 Token。

## 8. 先建立事实矩阵

生成正文前，先在 `catalog.md` 中为每个领域定义事实：

```text
事实 ID
事实描述
适用套餐
生效版本或时间
能力状态
来源文档
来源章节路径
容易混淆的错误事实
是否用于 Critical Query
```

事实 ID 只用于数据集维护，不写入最终 Query，也不作为 Chunk ID。

建议状态词统一为：

```text
标准支持
仅指定套餐支持
需要额外配置
需要定制开发
由专业服务交付
路线图计划
已经弃用
明确不支持
```

事实矩阵必须先确定，再写知识文档和 Query。不能先生成问题，再临时向正文中补答案。

## 9. Markdown 知识文档规范

每份知识文档必须满足：

1. 只有一个唯一的一级标题；
2. 使用二级和三级标题表达自然业务层级；
3. 标题服务于可读性和业务结构，而不是服务于预期 Chunk 数量；
4. 每个章节包含明确、可验证的事实；
5. 数字必须包含单位、适用范围和例外条件；
6. 版本信息必须包含生效时间和替代关系；
7. 套餐能力必须明确适用于哪个套餐；
8. 表格和列表中的关键事实也应有必要的自然语言解释；
9. 不得把评测 Query 原句直接复制进正文；
10. 不得用大量同义句重复填充 Token；
11. 同一事实在不同文件中出现时必须说明主从关系或引用关系；
12. 不写“请检索”“标准答案”“相关 Query”等评测提示。

示例：

```markdown
# DealFlow Identity and Access Control Guide

## Enterprise Single Sign-On

Enterprise tenants can connect an identity provider through SAML 2.0 or OpenID Connect. The Business plan includes OpenID Connect but does not include automated SAML metadata rotation.

### Certificate rotation

SAML signing certificates can overlap for seven days during rotation. Automatic metadata refresh runs every six hours for Enterprise tenants.
```

Query 开始标注后，不得随意重命名文档一级标题或被引用的章节标题，否则相关章节标签会失效。

## 10. 检索难度设计

评测难度应来自业务事实之间的相似性，而不是故意写得含糊或破坏文档结构。

### 10.1 数字干扰

例如在不同章节中分别设置：

```text
审计日志保留 180 天
应用运行日志保留 30 天
备份保留 35 天
安全事件摘要保留 365 天
```

询问审计日志时，其他数字构成合理干扰。

### 10.2 套餐干扰

```text
Business：99.9% SLA
Enterprise：99.95% SLA
Dedicated：99.99% SLA
```

Query 必须写清套餐或部署模式，相关标签只指向能够回答该条件的章节。

### 10.3 当前版本与历史版本

历史文档必须明确写出：

```text
Document status: superseded
Effective period: 2024-01-01 to 2025-06-30
Replaced by: 当前文档标题
```

询问“当前”“最新”或“现行”的 Query 应指向当前文档；询问历史迁移规则时才指向历史文档。

### 10.4 能力状态干扰

“路线图计划”“需要定制”和“标准支持”是不同结论。正文和标签必须保留这种差别，不能把未来计划当成现有能力。

### 10.5 相近概念干扰

至少覆盖以下概念对：

```text
RTO / RPO
认证日志 / 审计日志
数据驻留 / 备份区域
API 限流 / 并发用户数
身份认证 / 用户同步
原生连接器 / REST API 集成
删除 / 归档 / 停用
当前能力 / 历史能力 / 路线图能力
```

## 11. Query 设计

生成 150 条 Query，固定分布如下：

| 主要类型 | 数量 | 说明 |
|---|---:|---|
| 直接业务需求 | 55 | 明确询问产品能力或限制 |
| 同义改写 | 25 | 不直接复用正文句子和章节标题 |
| Hard Negative 区分 | 25 | 需要区分数字、套餐、版本或状态 |
| 多证据查询 | 15 | 至少需要两个不同章节共同回答 |
| 中英混合和缩写 | 15 | SLA、RTO、RPO、SAML、SCIM 等 |
| 精确数字和期限 | 15 | 保留期、响应时间、容量或频率 |
| 合计 | 150 | 每条只归入一个主要类型 |

难度分布：

```text
easy:   45
medium: 75
hard:   30
```

`critical=true` 固定为 45 条，重点覆盖安全、合规、数据驻留、灾备、关键容量和删除一致性。

每条 Query 应像真实的 RFP 条款、采购问卷或技术澄清问题，并满足：

- 不引用文档编号或章节名称；
- 不直接复制正文答案；
- 数字问题保留单位和适用范围；
- Hard Query 能解释相似事实为什么不是正确答案；
- 多证据 Query 的标签覆盖所有必要章节；
- 不通过刻意堆砌冷僻词制造虚假难度。

不合格示例：

```text
请检索 Identity and Access Management 章节。
```

合格示例：

```text
员工从企业目录离职后，账号是否能在无需管理员手工操作的情况下自动停用？
```

## 12. Query JSONL 格式

每行必须是一个完整 JSON 对象，不使用 Markdown 代码围栏，也不能跨行。

```json
{"query_id":"iam-saml-current-001","query":"当前 Enterprise 套餐必须支持 SAML 2.0 单点登录。","category":"security","difficulty":"medium","critical":true,"relevant":[{"title":"DealFlow Identity and Access Control Guide","section_path":["DealFlow Identity and Access Control Guide","Enterprise Single Sign-On"],"relevance":3}]}
```

字段要求：

| 字段 | 要求 |
|---|---|
| `query_id` | 全局唯一，小写 kebab-case，含义稳定 |
| `query` | 真实业务需求或问题，不写答案 |
| `category` | 使用统一的小写分类 |
| `difficulty` | `easy`、`medium` 或 `hard` |
| `critical` | 布尔值 |
| `relevant` | 至少包含一个相关章节标签 |
| `title` | 与 `corpus.json` 及 Markdown 一级标题完全一致 |
| `section_path` | 与 Markdown 标题路径完全一致 |
| `relevance` | 正整数，推荐 1～3 |

相关性等级：

```text
3：直接回答核心问题的必要证据
2：完成回答所需的补充证据
1：有帮助但不影响核心结论
```

相关标签描述的是源文档章节，不是预先生成的 Parent 或 Child。评测运行时，系统会根据章节路径判断检索结果是否相关。

当前评测器要求每条 Query 至少有一个 `relevant` 标签，所以本轮不能生成无答案 Query。无答案能力应在评测器支持 `expected_no_answer` 后另建数据集。

## 13. Corpus Manifest 格式

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

- `document_key` 全局唯一且稳定；
- `path` 相对于 `corpus.json`；
- `title` 与对应 Markdown 的一级标题一致；
- `category` 使用小写 kebab-case；
- 历史文档必须填写明确版本；
- Manifest 包含且只包含本次生成的 20 份文档。

## 14. Dev/Test 划分

最终生成：

```text
queries-dev.jsonl   105 条
queries-test.jsonl   45 条
```

必须按照 category、difficulty、Query 类型和 critical 分层划分，不能简单地取前 105 条。

同一事实的轻微改写不能分别进入 Dev 和 Test。例如“SAML 单点登录”和“通过 SAML 接入 IdP”如果意图和目标证据相同，就必须位于同一集合。

Test 集完成校验后冻结。后续可以根据 Dev 调参，但不能根据 Test 的失败项反复修改问题、正文或标签。

## 15. 分批执行步骤

### 阶段 A：事实与文档规划

1. 创建目录；
2. 建立 `catalog.md`；
3. 确定事实、版本、套餐和干扰关系；
4. 检查 20 份文档之间是否存在矛盾；
5. 提交一次 Git Commit。

### 阶段 B：生成知识文档

每批生成 4～5 份文档。每批完成后：

1. 检查文件编码；
2. 检查一级标题是否唯一；
3. 检查事实是否与 `catalog.md` 一致；
4. 检查是否包含无意义扩写或 Query 泄漏；
5. 使用 `cl100k_base` 统计 Token；
6. 只提交本批新增的数据文件。

文档生成阶段不运行或调整 Chunker，也不检查 Parent/Child 是否达到某个数量。

建议提交信息：

```text
testdata(rag): add security evaluation corpus
testdata(rag): add operations evaluation corpus
testdata(rag): add integration evaluation corpus
```

### 阶段 C：生成 Dev Query

从事实矩阵选择目标事实，生成并标注 105 条 Dev Query。先有事实和证据，再写 Query，不能反向向知识库补答案。

### 阶段 D：生成并冻结 Test Query

生成 45 条 Test Query，使用不同于 Dev 的事实组合、表达方式和干扰关系。完成泄漏检查后单独提交。

### 阶段 E：源数据校验

校验以下内容：

```text
知识文件数量
Token 总量和各文件 Token
Markdown 一级标题唯一性
Manifest 文件路径
Manifest title 与一级标题一致性
JSONL 逐行可解析
Query 数量和分布
query_id 唯一性
relevance 为正整数
每个 section_path 对应真实标题路径
每条 Query 至少有一个相关标签
Dev/Test 无重复或高相似意图泄漏
```

### 阶段 F：运行系统评测

系统会自动完成解析、切分、Embedding、Qdrant 入库和检索。这一阶段可以记录 Parent、Child、Qdrant Point 的实际数量，便于以后比较配置变化，但不能据此反向修改文档以满足某个数量目标。

## 16. 自动校验要求

`validation-summary.json` 至少包含：

```json
{
  "document_count": 20,
  "total_tokens": 0,
  "document_tokens": {},
  "dev_query_count": 105,
  "test_query_count": 45,
  "difficulty_counts": {},
  "critical_count": 45,
  "multi_evidence_count": 0,
  "duplicate_query_ids": [],
  "missing_manifest_files": [],
  "title_mismatches": [],
  "invalid_section_paths": [],
  "dev_test_leakage_candidates": []
}
```

`total_tokens` 等数值必须由校验程序计算后写入，不能照抄示例。

章节标签的源数据校验可以根据 Markdown 标题树确认 `section_path` 是否存在。运行完整评测后，如果系统产生以下统计，可作为附加观测字段记录：

```text
observed_parent_count
observed_child_count
observed_qdrant_point_count
```

这些字段没有目标范围，不参与通过或失败判断。

## 17. 防止评测结果虚高

如果 Dense、Hybrid 和 Hybrid + Reranker 都获得接近满分的结果，优先检查：

- Query 是否直接复制正文句子；
- 文档中是否缺少相近概念；
- 是否缺少当前版本和历史版本干扰；
- 是否缺少相近数值和套餐差异；
- 相关章节标签是否标得过宽；
- 多证据 Query 是否真的需要多个章节；
- Dev/Test 是否存在相同事实的改写泄漏。

不要通过控制 Chunk 数量制造难度，也不要为追求预设分数而修改正确标签。评测的目标是产生可解释的方案差异，不是得到好看的固定分数。

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

使用 `run` 覆盖命令时，必须把 `python ...` 作为服务命令传入，不能把整条命令写成一个带引号的字符串。

## 19. 最终验收标准

源数据必须同时满足：

- 20 份知识文档全部存在并写入 Manifest；
- 总 Token 为 268,200～327,800；
- 文档事实与 `catalog.md` 一致；
- 所有标题、路径和文档标识合法且唯一；
- Dev 正好 105 条，Test 正好 45 条；
- Easy 45、Medium 75、Hard 30；
- Critical 正好 45；
- 多证据 Query 至少 15 条；
- 所有 Query ID 唯一；
- 每个相关标签指向真实存在的源文档章节；
- Dev/Test 不存在重复意图泄漏；
- 没有 Query 原句泄漏、无意义扩写和事实冲突。

系统验证必须满足：

- Dense、Hybrid、Hybrid + Reranker 均能完整运行；
- 生成 `summary.json`、`query-details.jsonl` 和 `report.html`；
- 记录运行时实际产生的文档、Parent、Child 和 Qdrant Point 数量；
- Chunk 数量只报告，不作为验收门槛；
- 不修改生产检索或切分逻辑来迎合数据集；
- 不覆盖或提交用户的无关修改；
- 每个生成批次均有独立的本地 Git Commit。

## 20. 可直接交给另一个 AI 的任务指令

复制以下内容到新的对话窗口：

```text
请先完整读取并严格执行：
E:\study2\LLM Internship\RFP-Agent\docs\rag\rag-evaluation-dataset-generation-guide.md

在 evals/retrieval/large_v1 下构造 DealFlow RAG 大规模评测数据集。你的工作是编写 20 份总计约 30 万 Token 的 Markdown 企业知识文档、corpus.json、事实目录、105 条 Dev Query、45 条冻结 Test Query 和源数据校验结果。

你只负责源知识文档和评测 Query，不得手工设计 Parent、Child、Chunk ID、向量或 Qdrant Point，不得为了达到某个 Chunk 数量反向修改文档结构。解析、父子切分、Embedding 和 Qdrant 入库必须交给项目现有代码执行。运行后可以报告实际 Chunk 数量，但它不是生成目标或验收条件。

开始前先检查当前评测代码和 Git 工作区。严格匹配现有 corpus manifest 与 JSONL Schema，不生成无答案 Query，不修改生产 RAG 逻辑，不覆盖或提交工作区里的无关修改。按指南分批生成和校验，每完成一批都进行本地 Git Commit。最后运行隔离评测，报告源文档 Token、Query 分布、标签有效性、Dev/Test 泄漏检查、运行时观测统计和三种检索模式的指标，并列出所有提交哈希。
```
