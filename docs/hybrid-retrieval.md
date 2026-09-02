# 企业知识库混合检索

## 在线流程

```text
Requirement(category + normalized_text)
               │
               ├───────────────┐
               ▼               ▼
       Dense Child Top 40   BM25 Child Top 40
               │               │
               └───────┬───────┘
                       ▼
              Qdrant RRF Top 30
                       │
                       ▼
             按 document_id + parent_id
             分组并保留最高排名 Child
                       │
                       ▼
              MySQL 加载有效 Parent
                       │
                       ▼
             最终 Parent Evidence Top 5
                       │
                       ▼
                Capability Agent
```

Dense 和 BM25 两个 Prefetch 都使用 `status=ACTIVE` Payload Filter，失效 Point 不参与任一路候选召回。MySQL 的 `documents.status=READY` 仍作为最终一致性校验。

Qdrant V2 Collection 使用两个命名向量：

- `dense`：GLM `embedding-3` 生成的 1024 维向量；
- `bm25`：Qdrant `qdrant/bm25` 生成的 Sparse Vector，使用 `multilingual` tokenizer，并关闭英文默认 stemming 和 stopwords。

两路分数不直接线性相加。Qdrant Query API 使用 Reciprocal Rank Fusion，根据各自排名生成统一候选顺序。

## Parent 分组

Qdrant Point 仍然只保存 Child。RRF 之后按 `document_id + parent_id` 去重，融合排名最高的 Child 成为该 Parent 的 `matched_child_text`。随后从 MySQL 批量加载 Parent 正文。这样同一 Parent 的多个 Child 不会占满最终 Top-K，同时保留最精确的命中位置。

## 配置

```text
QDRANT_COLLECTION=dealflow_knowledge_v2
QDRANT_DENSE_VECTOR_NAME=dense
QDRANT_SPARSE_VECTOR_NAME=bm25
QDRANT_BM25_MODEL=qdrant/bm25
QDRANT_DENSE_PREFETCH_TOP_K=40
QDRANT_SPARSE_PREFETCH_TOP_K=40
QDRANT_HYBRID_FUSION_TOP_K=30
QDRANT_SEARCH_TOP_K=5
QDRANT_SCORE_THRESHOLD=0.25
```

`QDRANT_SCORE_THRESHOLD` 只应用于 Dense Prefetch。RRF 分数与余弦相似度不在同一尺度，因此不使用该阈值裁剪融合结果。

## 评测

`evals/retrieval` 保存固定知识文档、带标签查询和运行说明。Dense 基线与 Hybrid 使用相同查询、Embedding 模型、Parent 展开逻辑和 Top-K，确保对比只反映检索策略变化。

当前指标：

- Hit Rate@K：至少一个相关 Parent 是否被召回；
- Recall@K：标注相关 Parent 中被召回的比例；
- MRR@K：第一个相关 Parent 的倒数排名。

评测标签使用文档标题和章节路径，不依赖每次上传生成的 `document_id`。
