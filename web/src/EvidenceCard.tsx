import type { CapabilityEvidence } from "./types";

function positiveInteger(value: unknown): number | null {
  return typeof value === "number" && Number.isInteger(value) && value > 0
    ? value
    : null;
}

function range(start: unknown, end: unknown, unit: string): string | null {
  const first = positiveInteger(start);
  const last = positiveInteger(end);
  if (first === null) return null;
  return `第 ${first}${last !== null && last > first ? `–${last}` : ""} ${unit}`;
}

export function EvidenceCard({ evidence }: { evidence: CapabilityEvidence }) {
  const location = evidence.source_location ?? {};
  const sourceType = evidence.source_type ?? location.source_type;
  let position: string | null = null;
  if (sourceType === "markdown") {
    position = range(location.line_start, location.line_end, "行（解析文本）");
  } else if (sourceType === "docx") {
    position = range(location.paragraph_start, location.paragraph_end, "段（提取文本）");
  } else {
    position = range(
      location.page_start ?? evidence.page_number,
      location.page_end ?? evidence.page_end,
      "页",
    );
  }

  return (
    <div className="evidence-card">
      <div className="evidence-card-heading">
        <strong>{evidence.document_title || "未记录文档标题"}</strong>
        <span>{evidence.is_selected ? "已引用" : "候选证据"}</span>
      </div>
      <p className="evidence-source">
        {evidence.document_version ? `版本 ${evidence.document_version} · ` : ""}
        命中位置：{position ?? "未记录位置"}
      </p>
      {!!evidence.section_path?.length && (
        <p className="evidence-source">章节：{evidence.section_path.join(" › ")}</p>
      )}
      {evidence.matched_child_text ? (
        <>
          <blockquote>{evidence.matched_child_text}</blockquote>
          {evidence.snippet !== evidence.matched_child_text && (
            <details>
              <summary>展开上下文（可能超出上述命中范围）</summary>
              <blockquote>{evidence.snippet}</blockquote>
            </details>
          )}
        </>
      ) : (
        <blockquote>{evidence.snippet}</blockquote>
      )}
      <details className="evidence-source-details">
        <summary>来源标识</summary>
        <p>文档 ID：{evidence.document_id}</p>
        {!!evidence.source_block_ids?.length && (
          <p>来源块：{evidence.source_block_ids.join("、")}</p>
        )}
      </details>
    </div>
  );
}
