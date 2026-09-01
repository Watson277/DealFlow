# PDF 技术处理架构示意图

本文只描述统一 PDF 解析模块。RFP 与企业知识库共用这条解析链路，输出统一的
`DocumentIR JSON`；需求抽取、知识库切分、向量化等下游逻辑不在本文范围内。

## 1. 总体流程

```mermaid
flowchart TD
    A[PDF 文件] --> B[文件预检 Preflight]
    B --> B1{是否有效}
    B1 -- 否 --> BX[拒绝处理并返回稳定错误码]
    B1 -- 是 --> C[打开 PDF 并获取总页数]

    C --> D[读取第 N 页]
    D --> E[页面质量检测]
    E --> F{Page Type}

    F -- Native Text --> G[原生页处理路径]
    F -- Scanned or Mixed --> H[扫描或混合页处理路径]
    F -- Empty --> I[记录空页告警]

    G --> J[Block Fusion]
    H --> J
    I --> K[PageIR]
    J --> K

    K --> L[版面语义与阅读顺序分析]
    L --> M[最终 PageIR]
    M --> N{还有下一页吗}
    N -- 是 --> D
    N -- 否 --> O[汇总 page_types]
    O --> P[确定 Document Type]
    P --> Q[生成并保存 DocumentIR JSON]
    Q --> R[RFP 或企业知识库下游流程]
```

文件预检负责检查：

- 文件是否为有效 PDF；
- 是否加密；
- 是否包含页面；
- 页面数量是否超过限制；
- 文件元数据与校验和是否可读取。

## 2. 单页路由与多模态处理

路由粒度是“页”，不是“整份文档”。同一个 PDF 的不同页面可以进入不同路径。

```mermaid
flowchart LR
    A[当前 PDF 页面] --> B[提取原生文字和图片候选]
    B --> C[计算字符数 乱码率 文字覆盖率 图片覆盖率]
    C --> D{页面分类}

    subgraph NativeRoute[原生文字页路径]
        N1[PyMuPDF get_text] --> N4[Native TEXT Blocks]
        N2[PyMuPDF image info] --> N5[Native IMAGE Blocks]
        N3[PyMuPDF find_tables] --> N6[Native TABLE Blocks]
    end

    subgraph MultimodalRoute[扫描页或混合页路径]
        S1[页面渲染] --> S2[Layout Detection]
        S2 --> S3{区域类型}
        S3 -- Text Region --> S4[区域 OCR]
        S3 -- Table Region --> S5[TSR 表格结构识别]
        S5 --> S6[Cell OCR]
        S3 -- Image Region --> S7[VLM 可选]
        S4 --> S8[OCR TEXT Blocks]
        S6 --> S9[Scanned TABLE Blocks]
        S7 --> S10[IMAGE Blocks 与描述]
    end

    D -- Native Text --> N1
    D -- Native Text --> N2
    D -- Native Text --> N3
    D -- Scanned or Mixed --> S1

    B -. Mixed 页保留原生文字候选 .-> F[Block Fusion]
    N4 --> F
    N5 --> F
    N6 --> F
    S8 --> F
    S9 --> F
    S10 --> F
    F --> P[PageIR]
```

页面类型及其处理方式：

| 页面类型 | 判断特征 | 处理路径 |
| --- | --- | --- |
| `text` | 原生文字充足，图片覆盖率较低 | PyMuPDF 原生提取 |
| `scanned` | 几乎没有可靠原生文字，页面主要由图像构成 | 页面渲染、版面检测、区域 OCR/TSR/VLM |
| `mixed` | 同时存在可靠原生文字和较大图片区域 | 保留原生候选，同时运行区域 OCR/TSR/VLM |
| `empty` | 没有有效文字，也没有实质图片内容 | 生成空 PageIR 并记录告警 |

## 3. Block Fusion

多个通道的结果不能直接拼接，必须先消除重复与冲突。

```mermaid
flowchart TD
    A[Native TEXT] --> E[Block Fusion]
    B[OCR TEXT] --> E
    C[TABLE] --> E
    D[IMAGE or VLM] --> E

    E --> F[bbox 与 IoU 匹配]
    F --> G[文本归一化与相似度判断]
    G --> H[表格区域覆盖判断]
    H --> I{发生冲突}

    I -- Native 与 OCR 重复 --> J[保留 Native Text]
    I -- 表格与普通文字重叠 --> K[保留结构化 TABLE]
    I -- 图片区域重复 --> L[保留质量更高的 IMAGE]
    I -- 无冲突 --> M[全部保留]

    J --> N[唯一且可追溯的 Blocks]
    K --> N
    L --> N
    M --> N
    N --> O[PageIR]
```

当前主要优先级：

```text
结构化 TABLE > 表格区域内的普通文字
Native Text > OCR Text
高置信度结果 > 低置信度结果
内容完整的结果 > 内容残缺的结果
```

被丢弃块的 ID、冲突数量和去重统计会保存在页面 metadata 中。

## 4. PageIR 后处理与 DocumentIR 汇总

```mermaid
flowchart TD
    A[融合后的 Blocks] --> B[识别标题 列表 页眉 页脚 脚注 题注]
    B --> C[检测单栏或多栏]
    C --> D[恢复阅读顺序]
    D --> E[合并连续段落和标题]
    E --> F[最终 PageIR]

    F --> G[PageIR 1]
    F --> H[PageIR 2]
    F --> I[PageIR N]
    G --> J[DocumentIR Builder]
    H --> J
    I --> J

    J --> K[汇总 page_types]
    K --> L{文档类型}
    L -- 全部为 text --> M[text_based]
    L -- 全部为 scanned --> N[scanned]
    L -- 类型混合 --> O[mixed]

    M --> P[DocumentIR JSON]
    N --> P
    O --> P
```

统一输出保存以下核心信息：

- 文档 ID、文件名、SHA-256、解析器版本；
- 文档级类型与处理状态；
- 每一页的页面类型、实际路由、尺寸和置信度；
- 每个 Block 的类型、来源、bbox、阅读顺序、文字或表格 Markdown；
- OCR、Layout、TSR、VLM 与 Block Fusion 的处理 metadata；
- 可追溯的告警、降级路径和失败原因。

## 5. 模块对应关系

| 技术模块 | 当前代码位置 |
| --- | --- |
| 逐页分类与路由 | `app/documents/pdf/native.py`、`quality.py` |
| Layout Detection | `app/documents/pdf/layout/detection.py` |
| 区域 OCR | `app/documents/pdf/ocr.py` |
| TSR 与 Cell OCR | `app/documents/pdf/layout/tsr.py` |
| 图片区域 VLM | `app/documents/pdf/vision.py` |
| Block Fusion | `app/documents/pdf/fusion.py` |
| 版面语义与阅读顺序 | `app/documents/pdf/layout/analyzer.py` |
| DocumentIR 模型与序列化 | `app/documents/pdf/models.py`、`serialization.py` |

