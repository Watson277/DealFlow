# 企业知识库结构化父子 Chunk

## 目标

PDF 和 Markdown 保留各自的解析能力，但在知识索引阶段转换成统一的结构文档，随后由同一个父子切分器处理。DOCX 也通过纯文本适配器接入该链路，避免原有能力回退。

```text
PDF DocumentIR ── PDFStructureAdapter ─────┐
                                           ├─ StructuralDocument
Markdown ─────── MarkdownStructureAdapter ─┤          │
                                           │          ▼
DOCX text ────── DocxStructureAdapter ─────┘  HierarchicalKnowledgeChunker
                                                      │
                                                      ▼
                                            KnowledgeChunkBundle v1
                                               ├─ ParentChunk
                                               └─ ChildChunk
```

## 统一数据结构

`StructuralDocument` 和最终的 `KnowledgeChunkBundle` 与来源格式无关。格式差异只保留在 `location`：

- PDF：`page_start`、`page_end`、`block_ids`、`bboxes`；
- Markdown：`line_start`、`line_end`、`block_ids`；
- DOCX：`paragraph_start`、`paragraph_end`、`block_ids`。

每个 Parent 包含完整章节上下文，每个 Child 通过 `parent_id` 指向唯一 Parent。ID 使用 `document_id + section_path + sequence` 生成确定性 UUID，不会因不同文档存在同名章节而冲突。

原始展示文本和向量文本分开保存：

- `text`：保持原始内容，用于引用和展示；
- `embedding_text`：附加 Document、Version 和 Section 上下文，仅用于 Embedding。

## 切分规则

默认配置：

```text
KNOWLEDGE_PARENT_CHUNK_SIZE_CHARS=4000
KNOWLEDGE_CHILD_CHUNK_SIZE_CHARS=1200
KNOWLEDGE_CHILD_OVERLAP_CHARS=120
```

Parent 不跨章节路径合并，普通段落在达到 Parent 上限时拆分。Child 只能在自己的 Parent 内生成；普通长文本优先在段落、句号或换行处切分，仅长文本使用 overlap。

表格、代码、图片和公式属于原子结构：

- 表格独立成为 Parent，过大时按行生成 Child，并重复表头；
- 代码块独立成为 Parent，过大时保留围栏并按代码行生成 Child；
- PDF Caption 与紧随其后的表格或图片绑定；
- PDF 页眉、页脚不进入知识 Chunk。

## 保存与检索

统一结果保存到 MinIO：

```text
documents/{document_id}/chunks/knowledge-chunks.v1.json
```

Document 的 `extra_data` 会记录：

- `chunks_object_key`；
- `chunk_schema_version`；
- `parent_chunk_count`；
- `child_chunk_count`；
- `qdrant_point_count`。

Qdrant 只为 Child 保存向量。Child payload 同时保存 `parent_id`、来源位置和 Parent 正文。检索时扩大候选范围，按 `document_id + parent_id` 去重，然后把命中的 Child 展开为 Parent 上下文交给 Capability Agent；`matched_child_text` 仍被保留用于解释命中原因。

```text
需求向量
  → Child 候选召回
  → 按 Parent 去重
  → Child 展开为 Parent
  → 活跃知识文档过滤
  → Capability 判断
```

当前 Parent 正文随 Child payload 保存，避免检索阶段额外访问 MySQL 或 MinIO。若未来文档规模显著增大，可把 Parent 正文迁移到独立数据库表或缓存中，Qdrant payload 只保留 `parent_id`。
