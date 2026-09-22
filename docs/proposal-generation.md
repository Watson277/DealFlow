# Proposal generation

Generated narrative fields use Simplified Chinese, including batch responses,
evidence summaries, risks and overview sections. Prompts preserve technical names,
numbers, JSON keys and requirement identifiers. Markdown headings, column labels
and capability display labels are Chinese; stored capability enum values are
unchanged. This does not translate already saved drafts or Markdown objects:
existing proposals must be regenerated through the review/revision workflow.

The generator divides capability results into batches (default 8, configured through
`PROPOSAL_BATCH_SIZE`, range 1–10) and runs up to 3 independent top-level batches
concurrently (configured through `PROPOSAL_BATCH_CONCURRENCY`, range 1–16). Output is
merged in source order regardless of completion order. Each batch returns only
requirement keys, responses, evidence summaries and risks. Source requirement text
and capability status are restored locally. The prompt explicitly enumerates the
exact source keys. Missing, unknown or duplicate keys trigger one corrective
regeneration of the complete batch with coverage diagnostics. If correction fails,
the batch is halved recursively. A singleton gets at most one coverage correction;
continued mismatch fails before sections or a proposal are saved. Responses are
never assigned to different keys or silently dropped to pass validation.

After all batches succeed, a separate call generates the overall proposal
sections from the compact responses, without raw evidence snippets. Python merges
the sections and ordered response matrix into the existing `ProposalDraft`.
The Markdown renderer, review API and database schema remain compatible.

`finish_reason=length` raises an explicit truncation error. Requirement batches
are recursively halved on truncation, stopping at one requirement. A truncated
single-requirement response or overview fails explicitly; truncated JSON is never
accepted or fed into the generic schema repair loop. Other schema errors retain
the existing one-repair limit and transport retry budget.

Logs `proposal_batch_completed` report completed/total requirements;
`proposal_batch_coverage_failed` reports missing, unknown and duplicate keys;
`proposal_batch_split` reports automatic subdivision and its reason. The stage remains
`generate_proposal` until all validation, rendering and persistence succeed.

Coverage repair and recursive splitting stay inside the concurrency slot owned by the
top-level batch, so corrective calls cannot bypass the configured limit. Successful
batches are held in memory for this generation attempt. They are not
checkpointed across process restarts or manual retries; a failed task retry
regenerates all batches. Splitting can increase call count and overall latency.
`PROPOSAL_MAX_OUTPUT_TOKENS` applies to each call, including the overview.

Verification uses mocked LLM completions for a 42-requirement matrix, ordering,
missing/duplicate/unknown keys, truncation splitting and bounded terminal failure.
