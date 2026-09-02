# Markdown 企业知识库接入

企业知识库支持上传 `.md` 和 `.markdown` 文件。RFP 上传仍然只接受 PDF 和 DOCX，Markdown 不会进入 RFP 工作流。

## 处理流程

```text
Markdown 文件
→ 文件扩展名和大小检查
→ UTF-8 解码与控制字符检查
→ Markdown 结构解析
→ 标题路径、正文、列表、表格和代码块
→ KnowledgeChunk
→ Embedding
→ Qdrant
```

原始 Markdown 文件和解析后的文本保存在 MinIO。Markdown 没有 PDF 页码和 bbox，因此 `page_count`、Qdrant Payload 中的 `page` 和 `page_end` 为 `null`，也不会生成 PDF `DocumentIR`。

## 结构化分块

解析器支持两种标题语法：

```markdown
# ATX 一级标题
## ATX 二级标题

Setext 一级标题
================

Setext 二级标题
----------------
```

标题不会单独生成向量，而是转换为正文 Chunk 的章节上下文：

```text
Document: 企业能力说明
Version: 1.2
Section: 产品能力 > 安全能力

系统支持 SAML 2.0 单点登录。
```

普通段落和列表可以在同一章节内组合。Markdown 表格和 fenced code block 作为独立语义单元，避免与前后正文混合；超过 Chunk 长度限制时，表格按数据行拆分并重复表头，代码块按行拆分并补齐围栏。

## Qdrant 数据

每个 Markdown Chunk 生成一个向量。当前结构化 Qdrant Payload 可以保存：

- `document_id`、标题、版本和分类；
- Chunk 文本和序号；
- `section_path`；
- `block_types`；
- `source_block_ids`；
- `parent_id`；
- `page` 和 `page_end`，对于 Markdown 固定为 `null`。

Markdown 图片链接不会被主动下载，图片自身也不会生成向量；图片的 alt 文本和所在 Markdown 段落可以作为普通文本参与索引。

## 上传示例

```powershell
curl.exe --fail-with-body -X POST "http://localhost:8000/knowledge" `
  -F "file=@C:\path\to\enterprise-guide.md;type=text/markdown" `
  -F "title=企业能力说明" `
  -F "category=product" `
  -F "version=1.0"
```

成功后，响应中的 `status` 应为 `READY`，`extra_data.qdrant_point_count` 表示实际写入 Qdrant 的 Chunk 数量。
