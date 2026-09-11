# PDF 处理技术文档：MinerU → DocumentIR

更新时间：2026-09-11。实现依据：`e5a4de1`。

本文描述当前代码，而非未来设计。此前关于 PyMuPDF 原生提取、Tesseract、OpenCV 版面分析、TSR、Block Fusion 和本地多进程解析的文档属于历史方案，不再代表当前处理流程。

## 1. 目标与边界

RFP 和企业知识库共用一个 PDF 处理模块：将 PDF 交给 MinerU 云服务解析，再转换成项目统一的 DocumentIR v1.0。

PDF 模块只负责解析与格式适配，不负责需求抽取、能力判断、知识切分、Embedding 或向量检索。DOCX 和 Markdown 仍走各自的既有解析逻辑，不上传 MinerU。

当前只有 MinerU 一个 PDF 解析后端，没有原生回退路径，也不再使用 `PDF_BACKEND` 开关。缺少 Token、网络失败或结果格式不符合要求时，明确返回错误。

## 2. 总体流程

```text
RFP PDF / 企业知识库 PDF / 开发测试接口
                    |
                    v
             DocumentParser.parse
                    |
                    v
        本地预检：有效性、加密、页数、大小
                    |
                    v
       MinerU：申请上传 URL → 上传 PDF
                    |
                    v
           轮询任务 → 下载结果 ZIP
                    |
                    v
               layout.json
                    |
                    v
          按 pdf_info 页面顺序转换
                    |
       preproc_blocks + discarded_blocks
                    |
                    v
     类型映射 / 文本提取 / 表格转换 / bbox 缩放
                    |
                    v
          BlockIR → PageIR → DocumentIR
                    |
                    v
       本地保留原始 ZIP，返回 ParsedDocument
                    |
           +--------+---------+
           |                  |
           v                  v
     RFP 后续流程        知识库后续流程
     需求抽取等          结构化切分、索引等
```

本地仍使用 PyMuPDF 做预检、读取源页面尺寸，以及根据文本和图片覆盖情况计算页类型。这里读取的原生文本仅用于诊断，不作为最终正文来源。

原生页、扫描页、混合页均提交 MinerU。本地的 `text / scanned / mixed / empty` 分类只作为元数据，不再决定不同解析路径。MinerU 服务内部的 OCR、版面检测和模型调度不由本项目实现或控制。

## 3. 预检与远程任务

### 3.1 本地预检

在上传前检查 PDF 是否有效、是否加密、是否有页面，以及页数是否超过 `PDF_MAX_PAGES`。

- 适配器文件大小上限：200 MiB。
- 默认页数上限：500 页。
- HTTP 上传入口另有大小限制；开发测试接口默认受 50 MiB 的 `MAX_RFP_UPLOAD_SIZE_BYTES` 限制。实际允许大小取入口与适配器限制中更严格者。

以上是当前代码限制，不代表云服务未来的全部配额或限制。

### 3.2 MinerU 调用顺序

基础地址固定为 `https://mineru.net/api/v4`。

| 步骤 | 调用 | 作用 |
| --- | --- | --- |
| 1 | `POST /file-urls/batch` | 创建单文件批次，获取上传 URL |
| 2 | `PUT <上传 URL>` | 上传完整 PDF |
| 3 | `GET /extract-results/batch/{batch_id}` | 查询任务状态 |
| 4 | `GET <full_zip_url>` | 下载完成结果 |

请求默认使用 `model_version=vlm`、`language=ch`，开启表格和公式解析。`MINERU_MODEL` 也可设置为 `pipeline`。

轮询间隔最多 5 秒；轮询等待预算默认 1800 秒，从上传结束后开始计算。API 请求超时为 60 秒，上传/下载请求超时为 120 秒。轮询预算不是严格的整个处理过程超时，不能用它代替端到端耗时限制。

Authorization 只发送给 MinerU API，不附带到上传和结果存储 URL。存储 URL 必须使用 HTTPS，客户端不跟随重定向。

结果 ZIP 采用内存缓冲，限制为 256 MiB；其中唯一的根目录 `layout.json` 最大为 64 MiB。不批量解压 ZIP，因此这里不会将 ZIP 内任意路径写入文件系统。并发解析仍会增加内存占用。

## 4. 为什么使用 preproc_blocks

MinerU 返回 Markdown、内容列表、layout JSON、原始模型 JSON 和裁剪图片等产物。

已有表格 PDF 实测发现：最终 Markdown 和后处理内容列表会把不相关的跨页表格拼接在一起，而 `layout.json` 的逐页 `preproc_blocks` 仍保留独立表格内容。

因此适配器：

- 使用 `pdf_info[].preproc_blocks` 作为转换输入。
- 将 `discarded_blocks` 追加到该页，尽可能保留页眉、页脚等内容。
- 不使用 `para_blocks`、`full.md` 或 `content_list` 作为正文事实来源。
- 不自动拼接跨页续表，也不额外执行原生/OCR 多通道融合。

这能绕开已观察到的后处理误合并，但不能保证原始块没有识别错误。

## 5. DocumentIR 转换规则

### 5.1 页面、顺序与坐标

首先校验远程页数与源 PDF 一致，且 `page_idx` 按 0 开始连续排列，每页必须包含 `preproc_blocks`。

DocumentIR 页码从 1 开始。块按返回列表顺序编号，追加的 discarded 块位于后面；当前不进行额外的多栏阅读顺序恢复。

块 ID 形式为 `p{页码}-mineru-{序号}`，用于本次 IR 内定位，不承诺文档修改后的跨版本稳定身份。

`layout.json` 的 bbox 依据其 `page_size` 缩放到源 PDF 页面尺寸：

```text
x_source = x_layout / layout_width  × source_width
y_source = y_layout / layout_height × source_height
```

不要套用其他 MinerU 文件的坐标规则：本次实测中 content_list 使用 0～1000，model 使用 0～1，而 layout 使用页面单位。当前适配器只处理 layout。

DocumentIR 校验页面顺序、块 ID 唯一性、阅读顺序唯一性和坐标边界。特殊旋转、裁剪页面的转换效果仍需要更多样本验证。

### 5.2 类型映射

| MinerU 类型 | DocumentIR 类型 |
| --- | --- |
| title、text、list | TITLE、TEXT、LIST |
| table、image | TABLE、IMAGE |
| interline_equation | FORMULA |
| header | HEADER |
| footer、page_number | FOOTER |
| table_caption、image_caption | CAPTION |
| table_footnote、footnote | FOOTNOTE |

所有 MinerU 块的 `source` 标为 `derived`，用 metadata 中的 `provider=mineru` 标识来源，不凭空判断每个块是否经过 OCR。

### 5.3 内容保存

- 普通文字：递归读取嵌套块，行内拼接 span，行间换行，写入 `text` 和 `raw_text`。
- 表格：提取 HTML，生成可读单元格文本；简单表格生成管道 Markdown。第一行作为 Markdown 表头，这是一种展示约定，不是额外的表头语义识别。
- 复杂表格：发现 rowspan/colspan 等合并单元格时，`table_markdown` 保留嵌入 HTML，避免用简单管道表格丢失合并关系。
- 公式：内容写入 `latex`，不再调用第二个模型校正。
- 图片：保留块、bbox 和原始图片路径；当前不生成独立公开图片 URL，也不额外执行图片描述模型。
- 每个块保留 `metadata.raw_block`；表格另保留 `metadata.table_html`，图片路径保存在 `metadata.image_paths`。

`raw_text` 是适配器拼接后的文本，并非完整服务响应；完整原始信息应查看 `raw_block` 和原始 ZIP。

未知类型有文字时按 TEXT 保存并记录警告；没有可用文字时不创建文本块，但将原始块保存在警告 details 中。

### 5.4 统一返回对象

```text
ParsedDocument
├─ text：按页、块顺序拼接，表格优先使用 table_markdown
├─ page_count
├─ pdf：PDFDocument 解析结果
└─ document_ir：DocumentIR v1.0
   ├─ document_id、source_filename、checksum_sha256
   ├─ parser_version = mineru-preproc-1.0
   ├─ document_type、status、warnings
   ├─ pages[]：页面尺寸、类型、blocks、warnings
   └─ metadata：provider、provider_version、cross_page_merge 等
```

`text` 不是原始 MinerU Markdown，也不显式插入页码标题；需要准确定位时应使用 DocumentIR 的页码和 bbox。

## 6. 产物与存储

| 产物 | 当前保存位置与用途 |
| --- | --- |
| 原始上传 PDF | 由既有业务上传流程保存，作为源文件 |
| 统一 DocumentIR JSON | 业务层保存至 MinIO，供追溯和后续结构化处理 |
| 解析文本 | 业务层保存至 MinIO，供既有后续流程使用 |
| 文档状态和对象键 | MySQL 保存业务元数据，并非将整个 ZIP 存入数据库 |
| MinerU 原始结果 ZIP | 解析器写入本地目录，包含原始 JSON、Markdown 和裁剪图片 |

DocumentIR 标准对象键为 `documents/{document_id}/parsed/document-ir.v1.json`；更新流程以业务层实际记录的对象键为准。

原始 ZIP 路径：

```text
LOCAL_ARTIFACT_EXPORT_DIR/
└─ mineru/<document_id>/<随机运行ID>/result.zip
```

DocumentIR metadata 保存 `local_artifact_archive`，并标记 `asset_reference_scope=mineru_result_zip`。图片路径属于归档中的引用，不是 MinIO URL；定位时应对照 ZIP 内实际目录。

当前原始 ZIP 的保存不受 `LOCAL_ARTIFACT_EXPORT_ENABLED` 开关控制。写盘失败会导致本次解析失败。ZIP 尚未单独上传 MinIO，也没有随知识库删除自动清理的机制，需要管理磁盘占用。容器中的归档路径依赖数据目录挂载，跨机器读取时不可直接照搬本地路径。

## 7. 错误与状态

- 文件损坏、加密或超出页数限制：预检失败，不上传。
- Token 缺失：报配置错误，不尝试本地正文提取。
- 远程 failed、超时、HTTP 错误、结果结构不符合约定：解析失败。
- 未映射块或非空源页没有可用块：记录警告，IR 状态为 `partial_success`。
- 没有警告：IR 状态为 `succeeded`，但这不代表 OCR 准确率为 100%。
- 统一解析入口发现最终文本为空：仍会报错，不将空正文视为有效业务文档。

远程异常对外包装为异常类型，避免直接输出含签名 URL 的异常消息。当前适配器没有跨重试的任务续接和批次持久化；业务重试可能重新上传。

## 8. 配置、部署与测试

```dotenv
MINERU_API_TOKEN=你的Token
MINERU_MODEL=vlm
MINERU_WAIT_SECONDS=1800
PDF_MAX_PAGES=500
```

旧的 `PDF_BACKEND`、OCR、Layout、TSR、VLM 和本地页并行参数不再用于选择解析路径。切换到本方案意味着完整 PDF 会传给外部云服务，敏感资料上传前应确认数据使用要求。

重新构建并更新实际负责解析的服务：

```powershell
docker compose build api
docker compose up -d --force-recreate api rfp-worker knowledge-worker
```

开发测试接口只在开发类环境开放，接收上传文件，不让服务器读取用户指定的任意路径：

```powershell
curl.exe --fail-with-body -X POST "http://localhost:8000/dev/pdf/parse" `
  -F "file=@C:\Users\Steven Watson\Desktop\pdf\表格.pdf;type=application/pdf" `
  -o "mineru-pdf-result.zip"
```

下载包包含 DocumentIR JSON、适配器生成的 Markdown 和 summary JSON。这与本地保存的 MinerU 原始 ZIP 是两份不同的产物。

针对性回归命令：

```powershell
uv run pytest tests/test_mineru_backend.py tests/test_hierarchical_chunking.py tests/documents/pdf/test_models.py -q
```

最近一次上述测试结果为 28 项通过，覆盖模拟远程交互、Token 隔离、页数与坐标校验、接口、DocumentIR 和切分。该结果不是所有历史原生解析测试通过，也不替代真实云服务质量评测。

## 9. 代码位置

| 文件 | 职责 |
| --- | --- |
| `app/documents/parser.py` | PDF、DOCX、Markdown 统一入口 |
| `app/documents/pdf/mineru.py` | 云服务调用、逐页转换、本地 ZIP 归档 |
| `app/documents/pdf/preflight.py` | PDF 预检 |
| `app/documents/pdf/quality.py` | 页类型和质量元数据，不执行解析路由 |
| `app/documents/pdf/models.py` | DocumentIR / PageIR / BlockIR 定义与校验 |
| `app/documents/pdf/serialization.py` | IR 序列化及标准存储键 |
| `app/documents/pdf/bundle.py` | 开发测试下载包 |
| `app/api/routes/pdf_test.py` | 开发测试接口 |
| `app/workflow/stages/parse_rfp.py` | RFP 业务层调用与产物存储 |
| `app/services/knowledge.py` | 企业知识库调用、存储与后续切分 |

## 10. 当前限制与后续方向

当前没有自动错字修复、可靠跨页续表拼接、独立图片服务、云任务断点恢复、原始 ZIP 生命周期管理或 PDF 解析专用并发队列。

后续优先使用真实 PDF 验证中文、英文标识符、表格、公式、图片页与旋转页；先确认转换契约和内容质量，再考虑扩展功能。不要将 MinerU 返回文件数量或 `succeeded` 状态等同于解析准确率。
