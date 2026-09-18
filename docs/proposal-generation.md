# Proposal generation

The generator processes capability results sequentially in batches (default 8,
configured through `PROPOSAL_BATCH_SIZE`, range 1–10). Each batch returns only
requirement keys, responses, evidence summaries and risks. Source requirement text
and capability status are restored locally. Missing, unknown or duplicate keys
fail generation before a proposal is saved.

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
`proposal_batch_split` reports automatic subdivision. The stage remains
`generate_proposal` until all validation, rendering and persistence succeed.

Successful batches are held in memory for this generation attempt. They are not
checkpointed across process restarts or manual retries; a failed task retry
regenerates all batches. Splitting can increase call count and overall latency.
`PROPOSAL_MAX_OUTPUT_TOKENS` applies to each call, including the overview.

Verification uses mocked LLM completions for a 42-requirement matrix, ordering,
missing/duplicate/unknown keys, truncation splitting and bounded terminal failure.
