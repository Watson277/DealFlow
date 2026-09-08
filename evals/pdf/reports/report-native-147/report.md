# 原生 PDF 文本提取 CER 对比

Ground Truth 按页对齐；CER 计算前执行 Unicode NFKC，并删除全部空白字符。
普通基线直接读取 PyMuPDF 文本块并按几何边界去除页眉页脚；DealFlow 使用 DocumentIR 阅读顺序，并排除被识别为页眉或页脚的 Block。

## 结果

| 范围 | 方法 | Micro CER | Macro CER | 页面 CER P50 | 页面 CER P95 | 完全匹配页 | 空白页准确率 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 全部 147 页 | Direct PyMuPDF | 28.95% | 20.94% | 10.75% | 100.00% | 2.72% | 100.00% |
| 全部 147 页 | DealFlow DocumentIR | 3.91% | 4.78% | 1.88% | 17.79% | 2.72% | 100.00% |
| 已复核子集 | Direct PyMuPDF | 32.26% | 21.82% | 8.29% | 100.00% | 3.57% | 100.00% |
| 已复核子集 | DealFlow DocumentIR | 1.66% | 2.59% | 0.90% | 9.84% | 3.57% | 100.00% |

## 对比

- Micro CER 绝对变化（普通方法减 DealFlow）：25.03%
- Micro CER 相对变化：86.48%

## DealFlow 最差页面

| 页码 | CER | 真值字符数 | 预测字符数 | 真值复核状态 |
| ---: | ---: | ---: | ---: | --- |
| 147 | 40.82% | 49 | 69 | visually_spot_checked |
| 67 | 33.31% | 1261 | 1300 | needs_manual_review |
| 57 | 28.04% | 731 | 759 | needs_manual_review |
| 39 | 20.52% | 970 | 1001 | needs_manual_review |
| 84 | 19.84% | 756 | 764 | needs_manual_review |
| 69 | 19.26% | 675 | 701 | needs_manual_review |
| 83 | 18.55% | 744 | 773 | needs_manual_review |
| 81 | 17.96% | 952 | 979 | needs_manual_review |
| 68 | 17.39% | 719 | 731 | needs_manual_review |
| 74 | 16.73% | 544 | 532 | needs_manual_review |
| 52 | 16.46% | 723 | 729 | needs_manual_review |
| 85 | 15.64% | 748 | 775 | needs_manual_review |
| 51 | 15.43% | 797 | 821 | needs_manual_review |
| 56 | 15.16% | 739 | 745 | needs_manual_review |
| 11 | 14.38% | 939 | 944 | auto_verified |

## 结论

DealFlow 通过字体感知的 TeX OT1 映射修复恢复原生英文文本，并通过原生表格质量门过滤图表线条误检；其 Micro CER 低于 Direct PyMuPDF 基线。
