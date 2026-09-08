"""Compare direct PyMuPDF extraction with DealFlow DocumentIR using page CER."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import time
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pymupdf


EXCLUDED_DOCUMENT_IR_TYPES = {"header", "footer"}


@dataclass(frozen=True, slots=True)
class PageScore:
    page_number: int
    ground_truth_characters: int
    prediction_characters: int
    edit_distance: int
    cer: float
    exact_match: bool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--ground-truth", type=Path, required=True)
    parser.add_argument("--document-ir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def normalize_for_cer(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    return "".join(character for character in normalized if not character.isspace())


def levenshtein_distance(first: str, second: str) -> int:
    """Return exact Levenshtein distance using Myers' bit-vector algorithm."""

    if not first:
        return len(second)
    if not second:
        return len(first)
    if len(first) > len(second):
        first, second = second, first

    width = len(first)
    mask = (1 << width) - 1
    highest_bit = 1 << (width - 1)
    character_masks: dict[str, int] = {}
    for index, character in enumerate(first):
        character_masks[character] = character_masks.get(character, 0) | (1 << index)

    positive = mask
    negative = 0
    score = width
    for character in second:
        equal = character_masks.get(character, 0)
        vertical = equal | negative
        horizontal = (((equal & positive) + positive) ^ positive) | equal
        positive_horizontal = negative | ~(horizontal | positive)
        negative_horizontal = positive & horizontal
        if positive_horizontal & highest_bit:
            score += 1
        elif negative_horizontal & highest_bit:
            score -= 1
        positive_horizontal = ((positive_horizontal << 1) | 1) & mask
        negative_horizontal = (negative_horizontal << 1) & mask
        positive = (negative_horizontal | ~(vertical | positive_horizontal)) & mask
        negative = positive_horizontal & vertical
    return score


def _load_ground_truth(path: Path) -> list[dict[str, Any]]:
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    expected = list(range(1, len(records) + 1))
    actual = [int(record["page_number"]) for record in records]
    if actual != expected:
        raise ValueError("ground truth pages must be contiguous and one-indexed")
    return records


def _direct_pymupdf_pages(pdf_path: Path) -> tuple[list[str], float]:
    started = time.perf_counter()
    output: list[str] = []
    flags = pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES
    with pymupdf.open(pdf_path) as document:
        for page_number, page in enumerate(document, start=1):
            data = page.get_text("dict", sort=True, flags=flags)
            top_limit = page.rect.height * 0.075
            bottom_limit = page.rect.height * 0.925
            blocks: list[str] = []
            for block in data.get("blocks", []):
                if block.get("type") != 0:
                    continue
                x0, y0, x1, y1 = block.get("bbox", (0.0, 0.0, 0.0, 0.0))
                del x0, x1
                if page_number != 1 and (y0 < top_limit or y1 >= bottom_limit):
                    continue
                lines: list[str] = []
                for line in block.get("lines", []):
                    line_text = "".join(str(span.get("text", "")) for span in line.get("spans", []))
                    if line_text.strip():
                        lines.append(line_text.rstrip())
                if lines:
                    blocks.append("\n".join(lines))
            output.append("\n\n".join(blocks))
    return output, time.perf_counter() - started


def _document_ir_pages(path: Path) -> list[str]:
    document = json.loads(path.read_text(encoding="utf-8"))
    pages = sorted(document["pages"], key=lambda page: int(page["page_number"]))
    output: list[str] = []
    for page in pages:
        content: list[str] = []
        for block in sorted(page.get("blocks", []), key=lambda value: int(value["reading_order"])):
            if block.get("type") in EXCLUDED_DOCUMENT_IR_TYPES:
                continue
            if block.get("table_markdown"):
                content.append(str(block["table_markdown"]))
            elif block.get("text"):
                content.append(str(block["text"]))
        output.append("\n\n".join(content))
    return output


def _page_score(page_number: int, truth: str, prediction: str) -> PageScore:
    normalized_truth = normalize_for_cer(truth)
    normalized_prediction = normalize_for_cer(prediction)
    distance = levenshtein_distance(normalized_truth, normalized_prediction)
    if normalized_truth:
        cer = distance / len(normalized_truth)
    else:
        cer = 0.0 if not normalized_prediction else 1.0
    return PageScore(
        page_number=page_number,
        ground_truth_characters=len(normalized_truth),
        prediction_characters=len(normalized_prediction),
        edit_distance=distance,
        cer=cer,
        exact_match=normalized_truth == normalized_prediction,
    )


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _summary(scores: list[PageScore], extraction_seconds: float | None) -> dict[str, Any]:
    total_truth = sum(score.ground_truth_characters for score in scores)
    total_distance = sum(score.edit_distance for score in scores)
    blank_scores = [score for score in scores if score.ground_truth_characters == 0]
    return {
        "pages": len(scores),
        "ground_truth_characters": total_truth,
        "prediction_characters": sum(score.prediction_characters for score in scores),
        "edit_distance": total_distance,
        "micro_cer": total_distance / total_truth if total_truth else 0.0,
        "macro_cer": statistics.fmean(score.cer for score in scores) if scores else 0.0,
        "median_page_cer": _percentile([score.cer for score in scores], 0.50),
        "p95_page_cer": _percentile([score.cer for score in scores], 0.95),
        "exact_page_rate": (
            sum(score.exact_match for score in scores) / len(scores) if scores else 0.0
        ),
        "blank_page_accuracy": (
            sum(score.prediction_characters == 0 for score in blank_scores) / len(blank_scores)
            if blank_scores
            else None
        ),
        "extraction_seconds": extraction_seconds,
    }


def _evaluate(
    ground_truth: list[dict[str, Any]], predictions: list[str], extraction_seconds: float | None
) -> tuple[list[PageScore], dict[str, Any]]:
    if len(ground_truth) != len(predictions):
        raise ValueError(
            f"page count mismatch: ground truth={len(ground_truth)}, prediction={len(predictions)}"
        )
    scores = [
        _page_score(int(record["page_number"]), str(record["text"]), predictions[index])
        for index, record in enumerate(ground_truth)
    ]
    reviewed_indexes = [
        index
        for index, record in enumerate(ground_truth)
        if record.get("review_status") != "needs_manual_review"
    ]
    reviewed_scores = [scores[index] for index in reviewed_indexes]
    return scores, {
        "all_pages": _summary(scores, extraction_seconds),
        "reviewed_subset": _summary(reviewed_scores, extraction_seconds),
    }


def _percentage(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:.2f}%"


def _report_markdown(report: dict[str, Any], details: list[dict[str, Any]]) -> str:
    lines = [
        "# 原生 PDF 文本提取 CER 对比",
        "",
        "Ground Truth 按页对齐；CER 计算前执行 Unicode NFKC，并删除全部空白字符。",
        "普通基线直接读取 PyMuPDF 文本块并按几何边界去除页眉页脚；DealFlow 使用 DocumentIR 阅读顺序，并排除被识别为页眉或页脚的 Block。",
        "",
        "## 结果",
        "",
        "| 范围 | 方法 | Micro CER | Macro CER | 页面 CER P50 | 页面 CER P95 | 完全匹配页 | 空白页准确率 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    method_labels = {
        "pymupdf_direct": "Direct PyMuPDF",
        "dealflow_document_ir": "DealFlow DocumentIR",
    }
    for scope in ("all_pages", "reviewed_subset"):
        for method, label in method_labels.items():
            metrics = report["methods"][method][scope]
            lines.append(
                "| "
                + " | ".join(
                    [
                        "全部 147 页" if scope == "all_pages" else "已复核子集",
                        label,
                        _percentage(metrics["micro_cer"]),
                        _percentage(metrics["macro_cer"]),
                        _percentage(metrics["median_page_cer"]),
                        _percentage(metrics["p95_page_cer"]),
                        _percentage(metrics["exact_page_rate"]),
                        _percentage(metrics["blank_page_accuracy"]),
                    ]
                )
                + " |"
            )
    lines.extend(
        [
            "",
            "## 对比",
            "",
            f"- Micro CER 绝对变化（普通方法减 DealFlow）：{_percentage(report['comparison']['absolute_micro_cer_change'])}",
            f"- Micro CER 相对变化：{_percentage(report['comparison']['relative_micro_cer_change'])}",
            "",
            "## DealFlow 最差页面",
            "",
            "| 页码 | CER | 真值字符数 | 预测字符数 | 真值复核状态 |",
            "| ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in sorted(
        details, key=lambda value: value["dealflow_document_ir"]["cer"], reverse=True
    )[:15]:
        score = row["dealflow_document_ir"]
        lines.append(
            f"| {row['page_number']} | {_percentage(score['cer'])} | "
            f"{score['ground_truth_characters']} | {score['prediction_characters']} | "
            f"{row['review_status']} |"
        )
    lines.extend(
        [
            "",
            "## 结论",
            "",
            "该文档存在损坏的 TeX CMR 字体到 Unicode 映射，拉丁字母、数字和标点会被暴露为无关的 CJK 码位。DealFlow 当前仍把这些页面分类为原生文本页并保留错误字符；版面分析只能调整 Block 结构，不能修复字符映射。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    ground_truth = _load_ground_truth(args.ground_truth)
    direct_pages, direct_seconds = _direct_pymupdf_pages(args.pdf)
    dealflow_pages = _document_ir_pages(args.document_ir)

    direct_scores, direct_summary = _evaluate(ground_truth, direct_pages, direct_seconds)
    dealflow_scores, dealflow_summary = _evaluate(ground_truth, dealflow_pages, None)
    direct_micro = direct_summary["all_pages"]["micro_cer"]
    dealflow_micro = dealflow_summary["all_pages"]["micro_cer"]
    absolute_change = direct_micro - dealflow_micro
    report = {
        "dataset": {
            "source_filename": args.pdf.name,
            "pages": len(ground_truth),
            "ground_truth": str(args.ground_truth),
            "ground_truth_quality": "silver",
        },
        "methods": {
            "pymupdf_direct": direct_summary,
            "dealflow_document_ir": dealflow_summary,
        },
        "comparison": {
            "absolute_micro_cer_change": absolute_change,
            "relative_micro_cer_change": (
                absolute_change / direct_micro if direct_micro else 0.0
            ),
        },
    }
    details: list[dict[str, Any]] = []
    for index, record in enumerate(ground_truth):
        details.append(
            {
                "page_number": record["page_number"],
                "review_status": record.get("review_status"),
                "review_flags": record.get("review_flags", []),
                "pymupdf_direct": asdict(direct_scores[index]),
                "dealflow_document_ir": asdict(dealflow_scores[index]),
            }
        )

    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    with (args.output / "page-details.jsonl").open("w", encoding="utf-8", newline="\n") as target:
        for detail in details:
            target.write(json.dumps(detail, ensure_ascii=False) + "\n")
    (args.output / "report.md").write_text(
        _report_markdown(report, details), encoding="utf-8", newline="\n"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
