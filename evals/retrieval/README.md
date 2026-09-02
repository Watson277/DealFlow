# 检索评测

该目录提供一份固定企业知识文档和 8 条带相关章节标签的中英文混合查询，用于比较 Dense 与 Hybrid 检索。评测单位是 Parent，指标包括 Hit Rate@K、Recall@K 和 MRR@K。

## 准备数据

启动应用后，通过知识库接口上传 `enterprise_knowledge.md`：

```powershell
curl.exe --fail-with-body -X POST "http://localhost:8000/knowledge" `
  -F "title=DealFlow Retrieval Evaluation Knowledge" `
  -F "category=retrieval-eval" `
  -F "version=1.0" `
  -F "file=@evals/retrieval/enterprise_knowledge.md;type=text/markdown"
```

## 运行基线和混合检索评测

```powershell
uv run python -m app.rag.evaluate_cli `
  --dataset evals/retrieval/sample_queries.jsonl `
  --mode both `
  --top-k 5 `
  --output evals/retrieval/latest-results.json
```

`dense` 使用当前 Embedding 模型建立可比较基线；`hybrid` 使用相同 Dense 向量与 Qdrant BM25 多语言 Sparse Vector，通过 RRF 融合。评测文件按标题和章节路径匹配相关 Parent，因此测试文档可以使用任意 `document_id`。

`latest-results.json` 是本机运行产物，不应作为固定指标提交。正式调参前应扩展数据集，并把人工确认的相关 Parent 加入标签。

`baseline-2026-09-02.json` 记录首次 V2 实测结果：Dense 的 MRR@5 为 `0.9167`，Hybrid RRF 的 MRR@5 为 `1.0`；两者的 Hit Rate@5 和 Recall@5 均为 `1.0`。该小样本只用于防止功能回退，不能替代更大规模的业务评测集。
