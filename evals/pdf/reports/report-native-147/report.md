# 原生 PDF 文本提取 CER 对比

Ground Truth 按页对齐；CER 计算前执行 Unicode NFKC，并删除全部空白字符。
普通基线直接读取 PyMuPDF 文本块并按几何边界去除页眉页脚；DealFlow 使用 DocumentIR 阅读顺序，并排除被识别为页眉或页脚的 Block。

## 结果

| 范围 | 方法 | Micro CER | Macro CER | 页面 CER P50 | 页面 CER P95 | 完全匹配页 | 空白页准确率 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 全部 147 页 | Direct PyMuPDF | 28.94% | 20.93% | 10.75% | 100.00% | 2.72% | 100.00% |
| 全部 147 页 | DealFlow DocumentIR | 33.04% | 26.55% | 14.09% | 100.15% | 2.72% | 100.00% |
| 已复核子集 | Direct PyMuPDF | 32.28% | 21.84% | 8.29% | 100.00% | 3.57% | 100.00% |
| 已复核子集 | DealFlow DocumentIR | 34.92% | 26.32% | 11.92% | 100.21% | 3.57% | 100.00% |

## 对比

- Micro CER 绝对变化（普通方法减 DealFlow）：-4.10%
- Micro CER 相对变化：-14.18%

## DealFlow 最差页面

| 页码 | CER | 真值字符数 | 预测字符数 | 真值复核状态 |
| ---: | ---: | ---: | ---: | --- |
| 89 | 175.80% | 529 | 1004 | auto_verified |
| 62 | 100.65% | 764 | 1360 | needs_manual_review |
| 136 | 100.46% | 1754 | 1762 | auto_verified |
| 143 | 100.33% | 896 | 899 | auto_verified |
| 138 | 100.33% | 1800 | 1806 | auto_verified |
| 137 | 100.26% | 1892 | 1897 | auto_verified |
| 142 | 100.26% | 1922 | 1927 | auto_verified |
| 140 | 100.16% | 1872 | 1875 | visually_spot_checked |
| 133 | 100.13% | 1566 | 1572 | auto_verified |
| 135 | 100.11% | 1767 | 1769 | auto_verified |
| 139 | 100.06% | 1734 | 1735 | auto_verified |
| 141 | 100.00% | 1922 | 1922 | auto_verified |
| 145 | 98.58% | 1694 | 1711 | auto_verified |
| 134 | 98.35% | 1698 | 1704 | auto_verified |
| 146 | 95.19% | 1642 | 1645 | auto_verified |

## 结论

该文档存在损坏的 TeX CMR 字体到 Unicode 映射，拉丁字母、数字和标点会被暴露为无关的 CJK 码位。DealFlow 当前仍把这些页面分类为原生文本页并保留错误字符；版面分析只能调整 Block 结构，不能修复字符映射。
