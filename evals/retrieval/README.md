# RAG 检索评测

评测器支持三条检索链路：

- `dense`：Dense 向量召回；
- `hybrid`：Dense 与 BM25 召回后使用 RRF 融合；
- `hybrid_reranker`：Hybrid 候选经过 `bge-reranker-v2-m3` 重排。

指标包括 Hit Rate@K、Recall@K、MRR@K、nDCG@K、平均耗时和 P95 耗时。报告同时保存每条 Query 的候选 Parent、命中 Child、召回分和重排分。

## 数据

- `business_knowledge.md`：固定企业能力知识文档；
- `business_corpus.json`：隔离语料清单；
- `business_queries.jsonl`：20 条业务查询，包含难度、关键查询和分级相关性；
- `sample_queries.jsonl`：原有 8 条回归样本；
- `baseline-2026-09-02.json`：原有 Dense/Hybrid 实测基线。

每个相关标签支持 `relevance`，正整数越大表示相关性越强：

```json
{
  "query_id": "iam-saml",
  "query": "平台必须支持 SAML 2.0 单点登录。",
  "category": "security",
  "difficulty": "easy",
  "critical": true,
  "relevant": [
    {
      "title": "DealFlow Enterprise Platform Capability Handbook",
      "section_path": [
        "DealFlow Enterprise Platform Capability Handbook",
        "Identity and Access Management"
      ],
      "relevance": 3
    }
  ]
}
```

## 推荐：Docker 隔离评测

下面的命令只启动独立 Qdrant 和一次性评测容器，不连接开发用 MySQL、MinIO 或正式 Qdrant Collection。临时 Collection 在评测结束后自动删除，报告写入 `evals/retrieval/reports/latest`。

首次或代码变更后构建并运行：

```powershell
docker compose -f docker-compose.rag-eval.yml up `
  --build `
  --abort-on-container-exit `
  --exit-code-from rag-eval

docker compose -f docker-compose.rag-eval.yml down
```

镜像没有变化时可以省略 `--build`。Cross Encoder 使用 GPU，并复用主项目的 `dealflow-huggingface-cache` 模型缓存卷，不会为评测重复下载同一个模型。该共享卷只保存模型文件，不包含业务数据。

## 本机隔离评测

也可以复用正在运行的 Qdrant 服务，但使用自动生成的临时 Collection：

```powershell
uv run python -m app.rag.evaluate_cli `
  --isolated `
  --mode all `
  --dataset evals/retrieval/business_queries.jsonl `
  --corpus-manifest evals/retrieval/business_corpus.json `
  --top-k 5 `
  --candidate-k 30 `
  --reranker-device cuda `
  --report-dir evals/retrieval/reports/latest
```

`--keep-collection` 可以保留临时 Collection 供人工检查。指定 `--collection` 时，如果同名 Collection 已存在，评测器会拒绝覆盖。

## 评测已有开发知识库

不传 `--isolated` 时，评测器沿用原来的行为：查询当前配置的 Qdrant Collection，并从 MySQL 展开 Parent。

```powershell
uv run python -m app.rag.evaluate_cli `
  --mode both `
  --dataset evals/retrieval/sample_queries.jsonl `
  --top-k 5 `
  --output evals/retrieval/latest-results.json
```

评测结果目录包含：

```text
summary.json         完整运行元数据和指标
query-details.jsonl  逐模式、逐 Query 候选明细
report.html          可直接打开的可视化报告
```
