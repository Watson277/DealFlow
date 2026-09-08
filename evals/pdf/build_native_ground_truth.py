"""Build a reviewable, page-aligned native-PDF text ground truth dataset.

The extractor intentionally uses Poppler's ``pdftohtml`` instead of the
application's PyMuPDF parser.  It also repairs the TeX OT1 font mapping defect
present in the report used by the PDF extraction benchmark.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree


OT1_SPECIAL = {
    0x00: "Γ",
    0x01: "Δ",
    0x02: "Θ",
    0x03: "Λ",
    0x04: "Ξ",
    0x05: "Π",
    0x06: "Σ",
    0x07: "Υ",
    0x08: "Φ",
    0x09: "Ψ",
    0x0A: "Ω",
    0x0B: "ff",
    0x0C: "fi",
    0x0D: "fl",
    0x0E: "ffi",
    0x0F: "ffl",
    0x10: "ı",
    0x11: "ȷ",
    0x12: "`",
    0x13: "´",
    0x14: "ˇ",
    0x15: "˘",
    0x16: "¯",
    0x17: "˚",
    0x18: "¸",
    0x19: "ß",
    0x1A: "æ",
    0x1B: "œ",
    0x1C: "ø",
    0x1D: "Æ",
    0x1E: "Œ",
    0x1F: "Ø",
    0x22: "”",
    0x27: "’",
    0x3C: "¡",
    0x3E: "¿",
    0x5C: "“",
    0x5E: "ˆ",
    0x5F: "˙",
    0x60: "‘",
    0x7B: "–",
    0x7C: "—",
    0x7D: "˝",
    0x7E: "˜",
    0x7F: "¨",
}

OT1_FONT_PREFIXES = ("CMR", "CMBX", "CMTI", "CMSL", "CMSS", "SFRM")
WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class TextItem:
    top: int
    left: int
    width: int
    height: int
    font_family: str
    text: str

    @property
    def right(self) -> int:
        return self.left + self.width


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--xml-cache", type=Path)
    parser.add_argument("--expected-pages", type=int)
    parser.add_argument("--verified-blank-pages", nargs="*", type=int, default=[])
    parser.add_argument("--spot-checked-pages", nargs="*", type=int, default=[])
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def decode_ot1_text(text: str, font_family: str) -> tuple[str, int]:
    if not font_family.startswith(OT1_FONT_PREFIXES):
        return text, 0
    output: list[str] = []
    repaired = 0
    for character in text:
        codepoint = ord(character)
        if not 0x9000 <= codepoint <= 0x907F:
            output.append(character)
            continue
        slot = codepoint - 0x9000
        output.append(OT1_SPECIAL.get(slot, chr(slot)))
        repaired += 1
    return "".join(output), repaired


def run_pdftohtml(pdf_path: Path, xml_path: Path) -> None:
    executable = shutil.which("pdftohtml")
    if executable is None:
        raise RuntimeError("pdftohtml is required to build the independent ground truth")
    xml_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            executable,
            "-xml",
            "-nodrm",
            "-enc",
            "UTF-8",
            "-noframes",
            str(pdf_path),
            str(xml_path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )


def _font_family(raw_family: str) -> str:
    return raw_family.rsplit("+", maxsplit=1)[-1]


def _page_items(
    page: ElementTree.Element,
    fonts: dict[str, str],
) -> tuple[list[TextItem], int]:
    positions_by_value: dict[tuple[str, str], list[tuple[int, int, int, int]]] = {}
    items: list[TextItem] = []
    repaired_count = 0
    for node in page.findall("text"):
        source_text = "".join(node.itertext())
        family = fonts.get(node.attrib.get("font", ""), "unknown")
        text, repaired = decode_ot1_text(source_text, family)
        item = TextItem(
            top=int(node.attrib["top"]),
            left=int(node.attrib["left"]),
            width=int(node.attrib["width"]),
            height=int(node.attrib["height"]),
            font_family=family,
            text=text,
        )
        value_key = (item.font_family, item.text)
        positions = positions_by_value.setdefault(value_key, [])
        if any(
            abs(item.top - top) <= 2
            and abs(item.left - left) <= 2
            and abs(item.width - width) <= 1
            and abs(item.height - height) <= 1
            for top, left, width, height in positions
        ):
            continue
        positions.append((item.top, item.left, item.width, item.height))
        repaired_count += repaired
        items.append(item)
    return _remove_overlapped_text_runs(items), repaired_count


def _remove_overlapped_text_runs(items: list[TextItem]) -> list[TextItem]:
    """Drop per-glyph duplicates when the PDF also exposes a full text run."""

    removed: set[int] = set()
    composites = sorted(
        (index for index, item in enumerate(items) if len(item.text) > 1),
        key=lambda index: len(items[index].text),
        reverse=True,
    )
    for composite_index in composites:
        if composite_index in removed:
            continue
        composite = items[composite_index]
        contained = [
            index
            for index, item in enumerate(items)
            if index != composite_index
            and index not in removed
            and abs(item.top - composite.top) <= 2
            and composite.left - 2 <= item.left
            and item.right <= composite.right + 2
        ]
        contained.sort(key=lambda index: items[index].left)
        if "".join(items[index].text for index in contained) == composite.text:
            removed.update(contained)
    return [item for index, item in enumerate(items) if index not in removed]


def _group_lines(items: list[TextItem], tolerance: int = 10) -> list[list[TextItem]]:
    lines: list[list[TextItem]] = []
    for item in sorted(items, key=lambda value: (value.top, value.left)):
        for line in reversed(lines[-4:]):
            anchor = min(value.top for value in line)
            if abs(item.top - anchor) <= tolerance:
                line.append(item)
                break
        else:
            lines.append([item])
    return sorted(lines, key=lambda line: min(value.top for value in line))


def _join_line(items: list[TextItem]) -> str:
    ordered = sorted(items, key=lambda value: (value.left, value.top))
    parts: list[str] = []
    previous: TextItem | None = None
    for item in ordered:
        if previous is not None:
            gap = item.left - previous.right
            if gap > max(4, min(previous.height, item.height) // 4):
                parts.append(" ")
        parts.append(item.text)
        previous = item
    return "".join(parts).strip()


def _evaluation_text(items: list[TextItem], page_number: int, page_height: int) -> str:
    content = items
    if page_number != 1:
        top_margin = round(page_height * 0.075)
        bottom_margin = round(page_height * 0.925)
        content = [item for item in items if top_margin <= item.top < bottom_margin]
    lines = [_join_line(line) for line in _group_lines(content)]
    return "\n".join(line for line in lines if line).strip()


def normalize_for_cer(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    return WHITESPACE_RE.sub("", normalized)


def _review_flags(items: list[TextItem], text: str) -> list[str]:
    flags: list[str] = []
    families = {item.font_family for item in items}
    if any(family.startswith(("CMMI", "CMSY", "CMEX", "MSBM")) for family in families):
        flags.append("MATH_CONTENT")
    if "�" in text:
        flags.append("REPLACEMENT_CHARACTER")
    if not normalize_for_cer(text):
        flags.append("EMPTY_EVALUATION_TEXT")
    return flags


def build_dataset(
    pdf_path: Path,
    xml_path: Path,
    output: Path,
    *,
    verified_blank_pages: frozenset[int] = frozenset(),
    spot_checked_pages: frozenset[int] = frozenset(),
) -> dict[str, object]:
    root = ElementTree.parse(xml_path).getroot()
    fonts = {
        node.attrib["id"]: _font_family(node.attrib.get("family", "unknown"))
        for node in root.iter("fontspec")
    }
    pages: list[dict[str, object]] = []
    markdown_sections: list[str] = []
    plain_sections: list[str] = []
    repaired_total = 0
    flag_counts: Counter[str] = Counter()

    for page in root.findall("page"):
        page_number = int(page.attrib["number"])
        page_height = int(page.attrib["height"])
        items, repaired_count = _page_items(page, fonts)
        text = _evaluation_text(items, page_number, page_height)
        flags = _review_flags(items, text)
        visually_verified_blank = (
            page_number in verified_blank_pages and flags == ["EMPTY_EVALUATION_TEXT"]
        )
        if visually_verified_blank:
            flags = []
        repaired_total += repaired_count
        flag_counts.update(flags)
        if visually_verified_blank:
            review_status = "visually_verified_blank"
        elif flags:
            review_status = "needs_manual_review"
        elif page_number in spot_checked_pages:
            review_status = "visually_spot_checked"
        else:
            review_status = "auto_verified"
        pages.append(
            {
                "page_number": page_number,
                "text": text,
                "normalized_character_count": len(normalize_for_cer(text)),
                "review_status": review_status,
                "review_flags": flags,
            }
        )
        markdown_sections.append(f"## Page {page_number}\n\n{text}")
        plain_sections.append(f"--- Page {page_number} ---\n{text}")

    output.mkdir(parents=True, exist_ok=True)
    with (output / "ground-truth.jsonl").open("w", encoding="utf-8", newline="\n") as target:
        for record in pages:
            target.write(json.dumps(record, ensure_ascii=False) + "\n")
    (output / "ground-truth.md").write_text(
        "# report.pdf PDF extraction ground truth\n\n" + "\n\n".join(markdown_sections) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (output / "ground-truth.txt").write_text(
        "\n\n".join(plain_sections) + "\n", encoding="utf-8", newline="\n"
    )
    with (output / "review.csv").open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.writer(target)
        writer.writerow(
            ["page_number", "review_status", "normalized_character_count", "review_flags"]
        )
        for record in pages:
            writer.writerow(
                [
                    record["page_number"],
                    record["review_status"],
                    record["normalized_character_count"],
                    "|".join(record["review_flags"]),
                ]
            )

    manifest: dict[str, object] = {
        "dataset_version": "1.0.0-silver",
        "source_filename": pdf_path.name,
        "source_sha256": sha256_file(pdf_path),
        "page_count": len(pages),
        "scope": "native_selectable_text",
        "includes": ["body_text", "headings", "captions", "tables", "selectable_equations"],
        "excludes": ["running_headers", "page_numbers", "raster_only_figure_text"],
        "cer_normalization": ["Unicode NFKC", "remove all Unicode whitespace"],
        "independent_extractor": "Poppler pdftohtml XML",
        "font_repairs": {
            "encoding": "TeX OT1",
            "affected_fonts": ["CMR10", "CMR12"],
            "repaired_character_count": repaired_total,
        },
        "quality": {
            "label": "silver_ground_truth",
            "auto_verified_pages": sum(
                record["review_status"] in {"auto_verified", "visually_spot_checked"}
                for record in pages
            ),
            "pages_requiring_manual_review": sum(bool(record["review_flags"]) for record in pages),
            "review_flag_counts": dict(sorted(flag_counts.items())),
            "verified_blank_pages": sorted(verified_blank_pages),
            "visually_spot_checked_pages": sorted(spot_checked_pages),
        },
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return manifest


def main() -> None:
    args = parse_args()
    pdf_path = args.pdf.resolve()
    if not pdf_path.is_file():
        raise FileNotFoundError(pdf_path)
    output = args.output.resolve()
    if args.xml_cache is not None:
        xml_path = args.xml_cache.resolve()
        if not xml_path.is_file():
            run_pdftohtml(pdf_path, xml_path)
        manifest = build_dataset(
            pdf_path,
            xml_path,
            output,
            verified_blank_pages=frozenset(args.verified_blank_pages),
            spot_checked_pages=frozenset(args.spot_checked_pages),
        )
    else:
        with tempfile.TemporaryDirectory(prefix="pdf-ground-truth-") as directory:
            xml_path = Path(directory) / "source.xml"
            run_pdftohtml(pdf_path, xml_path)
            manifest = build_dataset(
                pdf_path,
                xml_path,
                output,
                verified_blank_pages=frozenset(args.verified_blank_pages),
                spot_checked_pages=frozenset(args.spot_checked_pages),
            )
    if args.expected_pages is not None and manifest["page_count"] != args.expected_pages:
        raise RuntimeError(
            f"expected {args.expected_pages} pages, generated {manifest['page_count']}"
        )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
