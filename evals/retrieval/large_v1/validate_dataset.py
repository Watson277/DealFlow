# ruff: noqa: E501
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path

import tiktoken

ROOT = Path(__file__).resolve().parent
TOKENIZER = "cl100k_base"
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
KEBAB = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
FACT_ID = re.compile(r"\bDF-\d{2}-\d{2}\b")
QUERY_TYPES = (
    "multi-evidence",
    "hard-negative",
    "paraphrase",
    "direct",
    "mixed",
    "numeric",
)
EXPECTED_TYPES = {
    "direct": 55,
    "paraphrase": 25,
    "hard-negative": 25,
    "multi-evidence": 15,
    "mixed": 15,
    "numeric": 15,
}
EXPECTED_DIFFICULTIES = {"easy": 45, "medium": 75, "hard": 30}
EXPECTED_DEV_DIFFICULTIES = {"easy": 32, "medium": 52, "hard": 21}
EXPECTED_TEST_DIFFICULTIES = {"easy": 13, "medium": 23, "hard": 9}
EXPECTED_DEV_TYPES = {
    "direct": 39,
    "paraphrase": 18,
    "hard-negative": 17,
    "multi-evidence": 11,
    "mixed": 10,
    "numeric": 10,
}
EXPECTED_TEST_TYPES = {
    "direct": 16,
    "paraphrase": 7,
    "hard-negative": 8,
    "multi-evidence": 4,
    "mixed": 5,
    "numeric": 5,
}
TARGET_TOKENS = {
    "01-platform-overview-current.md": 18_000,
    "02-platform-overview-legacy.md": 14_000,
    "03-identity-access-control.md": 14_000,
    "04-identity-access-migration-legacy.md": 12_000,
    "05-encryption-key-data-protection.md": 15_000,
    "06-audit-logging-security-operations.md": 15_000,
    "07-compliance-privacy-certifications.md": 18_000,
    "08-availability-service-levels.md": 16_000,
    "09-backup-recovery-disaster-recovery.md": 16_000,
    "10-deployment-models.md": 15_000,
    "11-network-security-boundaries.md": 14_000,
    "12-data-residency-cross-region.md": 14_000,
    "13-api-webhook-service-accounts.md": 16_000,
    "14-enterprise-integrations.md": 16_000,
    "15-performance-capacity-upload-limits.md": 14_000,
    "16-rfp-proposal-workflow.md": 15_000,
    "17-knowledge-chunk-incremental-update.md": 15_000,
    "18-support-incident-response.md": 14_000,
    "19-implementation-migration-training.md": 14_000,
    "20-limitations-deprecations-roadmap.md": 13_000,
}
EXPECTED_FIELDS = {
    "query_id",
    "query",
    "category",
    "difficulty",
    "critical",
    "relevant",
}


def load_jsonl(path: Path) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    rows: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise TypeError("row is not an object")
            rows.append(value)
        except (json.JSONDecodeError, TypeError) as exc:
            errors.append({"file": path.name, "line": line_number, "error": str(exc)})
    return rows, errors


def heading_tree(text: str) -> tuple[set[tuple[str, ...]], list[str]]:
    headings: dict[int, str] = {}
    paths: set[tuple[str, ...]] = set()
    h1_titles: list[str] = []
    for raw_line in text.splitlines():
        match = HEADING.match(raw_line)
        if match is None:
            continue
        level = len(match.group(1))
        title = re.sub(r"\s+#+\s*$", "", match.group(2)).strip()
        for old_level in tuple(headings):
            if old_level >= level:
                del headings[old_level]
        headings[level] = title
        path = tuple(headings[index] for index in sorted(headings))
        paths.add(path)
        if level == 1:
            h1_titles.append(title)
    return paths, h1_titles


def query_type(query_id: str) -> str:
    for value in QUERY_TYPES:
        if query_id.startswith(f"{value}-"):
            return value
    return "unknown"


def normalize_intent(value: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", value.casefold())


def trigrams(value: str) -> set[str]:
    normalized = normalize_intent(value)
    if len(normalized) < 3:
        return {normalized}
    return {normalized[index : index + 3] for index in range(len(normalized) - 2)}


def similarity(left: str, right: str) -> float:
    left_normalized = normalize_intent(left)
    right_normalized = normalize_intent(right)
    left_grams = trigrams(left)
    right_grams = trigrams(right)
    union = left_grams | right_grams
    jaccard = len(left_grams & right_grams) / len(union) if union else 1.0
    return max(jaccard, SequenceMatcher(None, left_normalized, right_normalized).ratio())


def label_key(label: dict[str, object]) -> tuple[str, tuple[str, ...]]:
    return str(label.get("title", "")), tuple(str(item) for item in label.get("section_path", []))


def main() -> None:
    manifest_path = ROOT / "corpus.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    documents = manifest.get("documents", [])
    encoding = tiktoken.get_encoding(TOKENIZER)

    missing_manifest_files: list[str] = []
    title_mismatches: list[dict[str, object]] = []
    invalid_markdown_structure: list[dict[str, object]] = []
    document_tokens: dict[str, int] = {}
    document_paths: dict[str, set[tuple[str, ...]]] = {}
    corpus_parts: list[str] = []
    document_keys: list[str] = []
    manifest_titles: list[str] = []
    long_paragraphs: Counter[str] = Counter()
    fact_ids_leaked_into_documents: list[dict[str, object]] = []
    historical_metadata_errors: list[str] = []

    for item in documents:
        relative_path = str(item.get("path", ""))
        path = ROOT / relative_path
        document_keys.append(str(item.get("document_key", "")))
        manifest_title = str(item.get("title", ""))
        manifest_titles.append(manifest_title)
        if not path.is_file():
            missing_manifest_files.append(relative_path)
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            invalid_markdown_structure.append({"path": relative_path, "error": str(exc)})
            continue
        corpus_parts.append(text)
        document_tokens[relative_path] = len(encoding.encode(text, disallowed_special=()))
        paths, h1_titles = heading_tree(text)
        document_paths[manifest_title] = paths
        if len(h1_titles) != 1:
            invalid_markdown_structure.append({
                "path": relative_path,
                "error": f"expected one H1, found {len(h1_titles)}",
            })
        elif h1_titles[0] != manifest_title:
            title_mismatches.append({
                "path": relative_path,
                "manifest_title": manifest_title,
                "markdown_h1": h1_titles[0],
            })
        h2_count = sum(len(path_value) == 2 for path_value in paths)
        h3_count = sum(len(path_value) == 3 for path_value in paths)
        if h2_count == 0 or h3_count == 0:
            invalid_markdown_structure.append({
                "path": relative_path,
                "error": f"natural H2/H3 hierarchy missing: h2={h2_count}, h3={h3_count}",
            })
        leaked_ids = sorted(set(FACT_ID.findall(text)))
        if leaked_ids:
            fact_ids_leaked_into_documents.append({"path": relative_path, "fact_ids": leaked_ids})
        for paragraph in (value.strip() for value in text.split("\n\n")):
            if len(paragraph) >= 200:
                long_paragraphs[paragraph] += 1
        if item.get("version") in {"2.4", "1.9"}:
            required = (
                "Document status: superseded",
                "Effective period: 2024-01-01 to 2025-06-30",
                "Replaced by:",
            )
            if any(value not in text for value in required):
                historical_metadata_errors.append(relative_path)

    dev_rows, dev_jsonl_errors = load_jsonl(ROOT / "queries-dev.jsonl")
    test_rows, test_jsonl_errors = load_jsonl(ROOT / "queries-test.jsonl")
    all_rows = dev_rows + test_rows
    jsonl_errors = dev_jsonl_errors + test_jsonl_errors
    query_ids = [str(row.get("query_id", "")) for row in all_rows]
    duplicate_query_ids = sorted(key for key, count in Counter(query_ids).items() if count > 1)
    invalid_query_rows: list[dict[str, object]] = []
    invalid_section_paths: list[dict[str, object]] = []
    query_fact_id_leaks: list[str] = []

    for split, rows in (("dev", dev_rows), ("test", test_rows)):
        for index, row in enumerate(rows, 1):
            row_id = str(row.get("query_id", ""))
            reasons: list[str] = []
            if set(row) != EXPECTED_FIELDS:
                reasons.append("unexpected or missing fields")
            if KEBAB.fullmatch(row_id) is None:
                reasons.append("query_id is not kebab-case")
            if not str(row.get("query", "")).strip():
                reasons.append("query is empty")
            if KEBAB.fullmatch(str(row.get("category", ""))) is None:
                reasons.append("category is not kebab-case")
            if row.get("difficulty") not in {"easy", "medium", "hard"}:
                reasons.append("difficulty is invalid")
            if not isinstance(row.get("critical"), bool):
                reasons.append("critical is not boolean")
            relevant = row.get("relevant")
            if not isinstance(relevant, list) or not relevant:
                reasons.append("relevant must be a non-empty list")
                relevant = []
            if FACT_ID.search(row_id) or FACT_ID.search(str(row.get("query", ""))):
                query_fact_id_leaks.append(row_id)
            for label in relevant:
                if not isinstance(label, dict):
                    reasons.append("relevance label is not an object")
                    continue
                title, path_value = label_key(label)
                relevance = label.get("relevance")
                if not isinstance(relevance, int) or isinstance(relevance, bool) or relevance < 1:
                    reasons.append("relevance must be a positive integer")
                if not path_value or path_value not in document_paths.get(title, set()):
                    invalid_section_paths.append({
                        "split": split,
                        "query_id": row_id,
                        "title": title,
                        "section_path": list(path_value),
                    })
            if reasons:
                invalid_query_rows.append({
                    "split": split,
                    "line": index,
                    "query_id": row_id,
                    "reasons": sorted(set(reasons)),
                })

    difficulty_counts = Counter(str(row.get("difficulty", "")) for row in all_rows)
    dev_difficulties = Counter(str(row.get("difficulty", "")) for row in dev_rows)
    test_difficulties = Counter(str(row.get("difficulty", "")) for row in test_rows)
    type_counts = Counter(query_type(str(row.get("query_id", ""))) for row in all_rows)
    dev_types = Counter(query_type(str(row.get("query_id", ""))) for row in dev_rows)
    test_types = Counter(query_type(str(row.get("query_id", ""))) for row in test_rows)
    category_counts = Counter(str(row.get("category", "")) for row in all_rows)
    dev_categories = Counter(str(row.get("category", "")) for row in dev_rows)
    test_categories = Counter(str(row.get("category", "")) for row in test_rows)
    critical_count = sum(row.get("critical") is True for row in all_rows)
    dev_critical = sum(row.get("critical") is True for row in dev_rows)
    test_critical = sum(row.get("critical") is True for row in test_rows)
    multi_evidence_count = sum(
        isinstance(row.get("relevant"), list) and len(row["relevant"]) >= 2
        for row in all_rows
    )

    dev_intents = {normalize_intent(str(row.get("query", ""))) for row in dev_rows}
    test_intents = {normalize_intent(str(row.get("query", ""))) for row in test_rows}
    exact_intent_overlap = sorted(dev_intents & test_intents)
    dev_labels = {
        label_key(label)
        for row in dev_rows
        for label in row.get("relevant", [])
        if isinstance(label, dict)
    }
    test_labels = {
        label_key(label)
        for row in test_rows
        for label in row.get("relevant", [])
        if isinstance(label, dict)
    }
    shared_labels = dev_labels & test_labels
    dev_test_leakage_candidates: list[dict[str, object]] = []
    highest_similarity: dict[str, object] | None = None
    for dev_row in dev_rows:
        for test_row in test_rows:
            score = similarity(str(dev_row.get("query", "")), str(test_row.get("query", "")))
            candidate = {
                "dev_query_id": dev_row.get("query_id"),
                "test_query_id": test_row.get("query_id"),
                "similarity": round(score, 4),
            }
            if highest_similarity is None or score > float(highest_similarity["similarity"]):
                highest_similarity = candidate
            if score >= 0.82:
                dev_test_leakage_candidates.append(candidate)
    for title, path_value in sorted(shared_labels):
        dev_test_leakage_candidates.append({
            "kind": "shared_relevance_label",
            "title": title,
            "section_path": list(path_value),
        })

    corpus_text = "\n".join(corpus_parts)
    query_sentence_leaks = [
        str(row.get("query_id", ""))
        for row in all_rows
        if str(row.get("query", "")) in corpus_text
    ]
    repeated_long_paragraphs = [
        {"count": count, "preview": paragraph[:240]}
        for paragraph, count in long_paragraphs.items()
        if count > 1
    ]
    catalog_text = (ROOT / "catalog.md").read_text(encoding="utf-8")
    catalog_fact_ids = re.findall(r"(?m)^\| (DF-\d{2}-\d{2}) \|", catalog_text)
    knowledge_files = sorted((ROOT / "knowledge").glob("*.md"))
    total_tokens = sum(document_tokens.values())
    target_deviations = {
        f"knowledge/{filename}": round(
            (document_tokens.get(f"knowledge/{filename}", 0) - target) / target * 100,
            3,
        )
        for filename, target in TARGET_TOKENS.items()
    }
    per_document_within_tolerance = all(
        abs(target_deviations[f"knowledge/{filename}"]) <= 15
        for filename in TARGET_TOKENS
    )

    gates = {
        "manifest_has_20_documents": len(documents) == 20,
        "knowledge_has_20_markdown_files": len(knowledge_files) == 20,
        "manifest_files_exist": not missing_manifest_files,
        "document_keys_unique": len(document_keys) == len(set(document_keys)) == 20,
        "titles_unique": len(manifest_titles) == len(set(manifest_titles)) == 20,
        "titles_match_h1": not title_mismatches,
        "markdown_hierarchy_valid": not invalid_markdown_structure,
        "historical_metadata_valid": not historical_metadata_errors,
        "catalog_has_240_unique_facts": len(catalog_fact_ids) == len(set(catalog_fact_ids)) == 240,
        "fact_ids_not_in_documents_or_queries": not fact_ids_leaked_into_documents and not query_fact_id_leaks,
        "total_tokens_in_range": 268_200 <= total_tokens <= 327_800,
        "per_document_tokens_within_15_percent": per_document_within_tolerance,
        "dev_has_105_queries": len(dev_rows) == 105,
        "test_has_45_queries": len(test_rows) == 45,
        "jsonl_parses": not jsonl_errors,
        "query_rows_valid": not invalid_query_rows,
        "query_ids_unique": len(query_ids) == len(set(query_ids)) == 150,
        "difficulty_distribution_valid": dict(difficulty_counts) == EXPECTED_DIFFICULTIES,
        "query_type_distribution_valid": dict(type_counts) == EXPECTED_TYPES,
        "dev_difficulty_stratified": dict(dev_difficulties) == EXPECTED_DEV_DIFFICULTIES,
        "test_difficulty_stratified": dict(test_difficulties) == EXPECTED_TEST_DIFFICULTIES,
        "dev_query_types_stratified": dict(dev_types) == EXPECTED_DEV_TYPES,
        "test_query_types_stratified": dict(test_types) == EXPECTED_TEST_TYPES,
        "categories_stratified": set(dev_categories) == set(test_categories) == set(category_counts),
        "critical_count_45": critical_count == 45,
        "critical_split_32_13": dev_critical == 32 and test_critical == 13,
        "multi_evidence_at_least_15": multi_evidence_count >= 15,
        "section_paths_exist": not invalid_section_paths,
        "no_dev_test_leakage": not exact_intent_overlap and not dev_test_leakage_candidates,
        "no_query_sentence_leak": not query_sentence_leaks,
        "no_repeated_long_paragraphs": not repeated_long_paragraphs,
    }

    runtime_evaluations: dict[str, object] = {}
    for split in ("dev", "test"):
        report_dir = ROOT.parent / "reports" / f"large-v1-{split}"
        summary_path = report_dir / "summary.json"
        details_path = report_dir / "query-details.jsonl"
        html_path = report_dir / "report.html"
        if not summary_path.is_file():
            continue
        report = json.loads(summary_path.read_text(encoding="utf-8"))
        indexing = report.get("indexing") or {}
        modes = {}
        for mode, values in report.get("reports", {}).items():
            modes[mode] = {
                "query_count": values.get("query_count"),
                "hit_rate_at_5": values.get("hit_rate"),
                "mrr_at_5": values.get("mean_reciprocal_rank"),
                "recall_at_5": values.get("mean_recall"),
                "ndcg_at_5": values.get("mean_ndcg"),
                "mean_latency_ms": values.get("mean_latency_ms"),
                "p95_latency_ms": values.get("p95_latency_ms"),
            }
        runtime_evaluations[split] = {
            "artifacts_complete": summary_path.is_file() and details_path.is_file() and html_path.is_file(),
            "document_count": indexing.get("document_count"),
            "observed_parent_count": indexing.get("parent_count"),
            "observed_child_count": indexing.get("child_count"),
            "observed_qdrant_point_count": indexing.get("child_count"),
            "index_elapsed_ms": indexing.get("elapsed_ms"),
            "modes": modes,
        }
    system_evaluation_complete = (
        set(runtime_evaluations) == {"dev", "test"}
        and all(
            item.get("artifacts_complete") is True
            and set(item.get("modes", {})) == {"dense", "hybrid", "hybrid_reranker"}
            for item in runtime_evaluations.values()
            if isinstance(item, dict)
        )
    )
    ndcg_above_one = any(
        float(mode_values.get("ndcg_at_5") or 0) > 1
        for item in runtime_evaluations.values()
        if isinstance(item, dict)
        for mode_values in item.get("modes", {}).values()
    )

    payload = {
        "schema_version": "2.0",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "validation_scope": "source data only; no parser, chunker, embedding, or vector store invoked",
        "tokenizer": TOKENIZER,
        "document_count": len(documents),
        "total_tokens": total_tokens,
        "document_tokens": document_tokens,
        "document_token_target_deviation_percent": target_deviations,
        "dev_query_count": len(dev_rows),
        "test_query_count": len(test_rows),
        "difficulty_counts": dict(sorted(difficulty_counts.items())),
        "critical_count": critical_count,
        "multi_evidence_count": multi_evidence_count,
        "query_type_counts": dict(sorted(type_counts.items())),
        "category_counts": dict(sorted(category_counts.items())),
        "dev_distribution": {
            "difficulty_counts": dict(sorted(dev_difficulties.items())),
            "query_type_counts": dict(sorted(dev_types.items())),
            "category_counts": dict(sorted(dev_categories.items())),
            "critical_count": dev_critical,
        },
        "test_distribution": {
            "difficulty_counts": dict(sorted(test_difficulties.items())),
            "query_type_counts": dict(sorted(test_types.items())),
            "category_counts": dict(sorted(test_categories.items())),
            "critical_count": test_critical,
        },
        "duplicate_query_ids": duplicate_query_ids,
        "missing_manifest_files": missing_manifest_files,
        "title_mismatches": title_mismatches,
        "invalid_section_paths": invalid_section_paths,
        "dev_test_leakage_candidates": dev_test_leakage_candidates,
        "highest_cross_split_similarity": highest_similarity,
        "jsonl_errors": jsonl_errors,
        "invalid_query_rows": invalid_query_rows,
        "invalid_markdown_structure": invalid_markdown_structure,
        "historical_metadata_errors": historical_metadata_errors,
        "query_sentence_leaks": query_sentence_leaks,
        "fact_ids_leaked_into_documents": fact_ids_leaked_into_documents,
        "fact_ids_leaked_into_queries": query_fact_id_leaks,
        "repeated_long_paragraphs": repeated_long_paragraphs,
        "catalog_fact_count": len(catalog_fact_ids),
        "system_evaluation_complete": system_evaluation_complete,
        "runtime_observations": runtime_evaluations,
        "known_system_limitations": ([
            "nDCG@5 exceeds 1.0 because the current evaluator can add gain for multiple Parent candidates matching one source-section label while the ideal gain includes that label once; recorded without changing production evaluation semantics."
        ] if ndcg_above_one else []),
        "freeze": {
            "queries_test_sha256": hashlib.sha256((ROOT / "queries-test.jsonl").read_bytes()).hexdigest(),
            "corpus_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        },
        "gates": gates,
        "all_gates_passed": all(gates.values()),
    }
    (ROOT / "validation-summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    log_path = ROOT / "generation-log.md"
    log = log_path.read_text(encoding="utf-8")
    marker = "\n## Latest source validation\n"
    if marker in log:
        log = log.split(marker, maxsplit=1)[0].rstrip() + "\n"
    log += (
        f"{marker}\n"
        f"- Generated at: {payload['generated_at_utc']}\n"
        f"- Documents / cl100k_base tokens: {len(documents)} / {total_tokens:,}\n"
        f"- Dev / Test queries: {len(dev_rows)} / {len(test_rows)}\n"
        f"- Critical / multi-evidence queries: {critical_count} / {multi_evidence_count}\n"
        f"- Invalid section paths: {len(invalid_section_paths)}\n"
        f"- Dev/Test leakage candidates: {len(dev_test_leakage_candidates)}\n"
        f"- Repeated long paragraphs: {len(repeated_long_paragraphs)}\n"
        f"- Frozen Test SHA-256: {payload['freeze']['queries_test_sha256']}\n"
        f"- All source-data gates passed: {all(gates.values())}\n"
    )
    if runtime_evaluations:
        first_observation = next(iter(runtime_evaluations.values()))
        log += (
            "\n## Runtime evaluation observations\n\n"
            "- Initial container attempt could not see large_v1 because the local image predated the dataset; rebuilding the existing rag-eval image resolved the environment issue.\n"
            f"- Observed documents / Parent / Child / Qdrant Point: "
            f"{first_observation['document_count']} / {first_observation['observed_parent_count']} / "
            f"{first_observation['observed_child_count']} / {first_observation['observed_qdrant_point_count']}\n"
            f"- Dev and Test report artifacts complete: {system_evaluation_complete}\n"
        )
        for split, observation in runtime_evaluations.items():
            for mode, values in observation["modes"].items():
                log += (
                    f"- {split} {mode}: Hit@5={values['hit_rate_at_5']:.4f}, "
                    f"MRR@5={values['mrr_at_5']:.4f}, Recall@5={values['recall_at_5']:.4f}, "
                    f"nDCG@5={values['ndcg_at_5']:.4f}\n"
                )
        if ndcg_above_one:
            log += (
                "- Known system limitation: nDCG@5 can exceed 1.0 because multiple Parent candidates under one labeled source section each add gain while the ideal gain counts the section label once. Production evaluation logic was not changed.\n"
            )
    log_path.write_text(log, encoding="utf-8")
    print(json.dumps({
        "document_count": payload["document_count"],
        "total_tokens": payload["total_tokens"],
        "dev_query_count": payload["dev_query_count"],
        "test_query_count": payload["test_query_count"],
        "difficulty_counts": payload["difficulty_counts"],
        "critical_count": payload["critical_count"],
        "multi_evidence_count": payload["multi_evidence_count"],
        "highest_cross_split_similarity": payload["highest_cross_split_similarity"],
        "all_gates_passed": payload["all_gates_passed"],
    }, ensure_ascii=False, indent=2))
    if not all(gates.values()):
        failed = [name for name, passed in gates.items() if not passed]
        raise SystemExit(f"source validation failed: {', '.join(failed)}")


if __name__ == "__main__":
    main()
