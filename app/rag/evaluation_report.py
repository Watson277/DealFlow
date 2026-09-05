from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


def write_evaluation_report(
    payload: dict[str, object],
    report_dir: Path,
) -> dict[str, str]:
    report_dir.mkdir(parents=True, exist_ok=True)
    summary_path = report_dir / "summary.json"
    details_path = report_dir / "query-details.jsonl"
    html_path = report_dir / "report.html"

    summary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    detail_lines: list[str] = []
    reports = payload.get("reports")
    if isinstance(reports, dict):
        for mode, report in reports.items():
            if not isinstance(report, dict):
                continue
            queries = report.get("queries")
            if not isinstance(queries, list):
                continue
            detail_lines.extend(
                json.dumps({"mode": mode, **query}, ensure_ascii=False)
                for query in queries
                if isinstance(query, dict)
            )
    details_path.write_text(
        "\n".join(detail_lines) + ("\n" if detail_lines else ""),
        encoding="utf-8",
    )
    html_path.write_text(_render_html(payload), encoding="utf-8")
    return {
        "summary": str(summary_path),
        "details": str(details_path),
        "html": str(html_path),
    }


def _render_html(payload: dict[str, object]) -> str:
    metadata_rows = "".join(
        _row(label, payload.get(key))
        for key, label in (
            ("dataset", "Dataset"),
            ("corpus_manifest", "Corpus"),
            ("collection", "Collection"),
            ("embedding_model", "Embedding"),
            ("reranker_model", "Reranker"),
            ("top_k", "Top K"),
            ("candidate_k", "Candidate K"),
        )
    )
    summary_rows: list[str] = []
    query_sections: list[str] = []
    reports = payload.get("reports")
    if isinstance(reports, dict):
        for mode, raw_report in reports.items():
            if not isinstance(raw_report, dict):
                continue
            summary_rows.append(
                "<tr>"
                f"<td>{_escape(mode)}</td>"
                f"<td>{_number(raw_report.get('hit_rate'))}</td>"
                f"<td>{_number(raw_report.get('mean_recall'))}</td>"
                f"<td>{_number(raw_report.get('mean_reciprocal_rank'))}</td>"
                f"<td>{_number(raw_report.get('mean_ndcg'))}</td>"
                f"<td>{_number(raw_report.get('mean_latency_ms'), digits=1)}</td>"
                f"<td>{_number(raw_report.get('p95_latency_ms'), digits=1)}</td>"
                "</tr>"
            )
            queries = raw_report.get("queries")
            if isinstance(queries, list):
                query_sections.append(_query_section(str(mode), queries))

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>DealFlow RAG Evaluation</title>
  <style>
    :root {{ color-scheme: light; --ink:#172033; --muted:#667085; --line:#d9e1ec;
      --blue:#24577f; --pale:#eef5fa; --good:#137a4a; --bad:#b42318; }}
    body {{ margin:0; background:#f5f7fa; color:var(--ink); font:14px/1.55 Arial,sans-serif; }}
    main {{ max-width:1200px; margin:32px auto; padding:0 20px 48px; }}
    h1 {{ margin:0 0 8px; font-size:28px; }} h2 {{ margin:30px 0 12px; }}
    .muted {{ color:var(--muted); }} .card {{ background:#fff; border:1px solid var(--line);
      border-radius:10px; padding:18px; margin:14px 0; box-shadow:0 2px 8px #1720330a; }}
    table {{ width:100%; border-collapse:collapse; }} th,td {{ border-bottom:1px solid var(--line);
      padding:9px 10px; text-align:left; vertical-align:top; }} th {{ background:var(--pale); }}
    .ok {{ color:var(--good); font-weight:700; }} .miss {{ color:var(--bad); font-weight:700; }}
    .query {{ display:flex; gap:12px; align-items:baseline; flex-wrap:wrap; }}
    code {{ white-space:pre-wrap; word-break:break-word; }} details {{ margin-top:10px; }}
  </style>
</head>
<body><main>
  <h1>DealFlow RAG Evaluation</h1>
  <p class="muted">自动生成的离线评测报告</p>
  <section class="card"><table><tbody>{metadata_rows}</tbody></table></section>
  <h2>汇总</h2>
  <section class="card"><table><thead><tr><th>模式</th><th>Hit Rate</th>
    <th>Recall</th><th>MRR</th><th>nDCG</th><th>平均耗时 ms</th><th>P95 ms</th>
    </tr></thead><tbody>{''.join(summary_rows)}</tbody></table></section>
  <h2>逐查询明细</h2>
  {''.join(query_sections)}
</main></body></html>
"""


def _query_section(mode: str, queries: list[Any]) -> str:
    cards: list[str] = [f"<h3>{_escape(mode)}</h3>"]
    for raw_query in queries:
        if not isinstance(raw_query, dict):
            continue
        hit = bool(raw_query.get("hit"))
        status = '<span class="ok">HIT</span>' if hit else '<span class="miss">MISS</span>'
        candidates = raw_query.get("candidates")
        candidate_rows = ""
        if isinstance(candidates, list):
            candidate_rows = "".join(
                _candidate_row(candidate)
                for candidate in candidates
                if isinstance(candidate, dict)
            )
        cards.append(
            '<article class="card">'
            '<div class="query">'
            f"<strong>{_escape(raw_query.get('query_id'))}</strong>{status}"
            f"<span>RR={_number(raw_query.get('reciprocal_rank'))}</span>"
            f"<span>Recall={_number(raw_query.get('recall'))}</span>"
            f"<span>nDCG={_number(raw_query.get('normalized_discounted_cumulative_gain'))}</span>"
            f"<span>{_number(raw_query.get('elapsed_ms'), digits=1)} ms</span>"
            "</div>"
            f"<p>{_escape(raw_query.get('query'))}</p>"
            "<details open><summary>候选结果</summary><table><thead><tr>"
            "<th>#</th><th>相关</th><th>文档 / 章节</th><th>召回分</th><th>重排分</th>"
            f"<th>命中 Child</th></tr></thead><tbody>{candidate_rows}</tbody></table></details>"
            "</article>"
        )
    return "".join(cards)


def _candidate_row(candidate: dict[str, Any]) -> str:
    relevant = bool(candidate.get("relevant"))
    relevance = candidate.get("relevance", 0)
    marker = (
        f'<span class="ok">是 ({_escape(relevance)})</span>'
        if relevant
        else '<span class="miss">否</span>'
    )
    section = " &gt; ".join(
        _escape(item) for item in candidate.get("section_path", []) if isinstance(item, str)
    )
    preview = candidate.get("matched_child_preview") or candidate.get("text_preview")
    return (
        "<tr>"
        f"<td>{_escape(candidate.get('rank'))}</td><td>{marker}</td>"
        f"<td><strong>{_escape(candidate.get('title'))}</strong><br>{section}</td>"
        f"<td>{_number(candidate.get('retrieval_score'))}</td>"
        f"<td>{_number(candidate.get('rerank_score'))}</td>"
        f"<td><code>{_escape(preview)}</code></td>"
        "</tr>"
    )


def _row(label: str, value: object) -> str:
    return f"<tr><th>{_escape(label)}</th><td>{_escape(value)}</td></tr>"


def _number(value: object, *, digits: int = 4) -> str:
    if isinstance(value, int | float):
        return f"{float(value):.{digits}f}"
    return "—"


def _escape(value: object) -> str:
    return html.escape("" if value is None else str(value))
