# DealFlow RAG Large V1 Generation Log

## Build identity

- Build seed: 20260906
- Tokenizer: cl100k_base
- Source data: fictional DealFlow product policies defined in catalog.md
- Production RAG changes: none
- Source generation does not invoke the parser, chunker, embedding service, or vector store

## Batches

1. Established the document plan and fact matrix before emitting queries.
2. Generated documents 01-05 for platform, IAM, and encryption controls.
3. Generated documents 06-10 for security operations, compliance, resilience, and deployment.
4. Generated documents 11-15 for networking, residency, integrations, and performance.
5. Generated documents 16-20 for workflow, knowledge indexing, support, implementation, and product status.
6. Generated 105 stratified Dev queries and 45 frozen Test queries from distinct primary facts.

## Human review points encoded in the build

- Current and superseded documents carry explicit status and effective dates.
- SLA, RTO, RPO, retention, capacity, and capability-state distractors are deliberately different.
- Multi-evidence cases use two independently labeled sections.
- Query wording is generated from business cues rather than copied from section headings.
- Knowledge headings follow four reader-oriented business areas with three factual subsections each; heading count and paragraph length are not tuned to Chunker behavior.
- Every long paragraph is unique, and each paragraph contributes a separate scope, procedure, exception, evidence, failure, responsibility, scenario, or change-control fact.

## Known limitations

- The corpus is synthetic and tests retrieval discrimination, not legal sufficiency.
- Core documents are Markdown only; PDF, DOCX, and OCR robustness remain separate evaluation concerns.
- The source validator checks the Markdown heading tree directly and never runs the Chunker. Runtime Parent and Child counts are recorded only by the isolated system evaluation.
- Retrieval metrics require Qdrant, embedding, and reranker services.

## Latest source validation

- Generated at: 2026-09-06T07:42:36.241095+00:00
- Documents / cl100k_base tokens: 20 / 323,680
- Dev / Test queries: 105 / 45
- Critical / multi-evidence queries: 45 / 15
- Invalid section paths: 0
- Dev/Test leakage candidates: 0
- Repeated long paragraphs: 0
- Frozen Test SHA-256: 120cdfd0d52742aca55cb70448c5a497915d324412f06aa12955c2ee2288bd67
- All source-data gates passed: True
