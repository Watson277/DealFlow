"""Font-aware repair for malformed native PDF text runs."""

from __future__ import annotations

from dataclasses import dataclass

_TEX_OT1_FONT_PREFIXES = ("CMR", "CMBX", "CMTI", "CMSL", "CMSS", "SFRM")
_TEX_OT1_OFFSET_START = 0x9000
_TEX_OT1_OFFSET_END = 0x907F
_TEX_OT1_SPECIAL = {
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


@dataclass(frozen=True, slots=True)
class NormalizedPDFSpan:
    text: str
    repaired_character_count: int
    encoding: str | None = None


def normalize_pdf_span(text: str, font_name: str) -> NormalizedPDFSpan:
    """Decode the U+9000-offset defect only for known TeX OT1 text fonts.

    Font gating is essential because U+9000..U+907F also contains legitimate
    Chinese characters. Math fonts intentionally are not included: they use a
    different slot mapping and need a dedicated equation representation.
    """

    family = font_name.rsplit("+", maxsplit=1)[-1].upper()
    if not family.startswith(_TEX_OT1_FONT_PREFIXES):
        return NormalizedPDFSpan(text=text, repaired_character_count=0)

    output: list[str] = []
    repaired = 0
    for character in text:
        codepoint = ord(character)
        if not _TEX_OT1_OFFSET_START <= codepoint <= _TEX_OT1_OFFSET_END:
            output.append(character)
            continue
        slot = codepoint - _TEX_OT1_OFFSET_START
        output.append(_TEX_OT1_SPECIAL.get(slot, chr(slot)))
        repaired += 1
    return NormalizedPDFSpan(
        text="".join(output),
        repaired_character_count=repaired,
        encoding="tex_ot1_u9000_offset" if repaired else None,
    )
