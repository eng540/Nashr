# ADR — Vertical Slice 2 Discovery and Gemini Runtime

## Context

The previous discovery path performed topic-level generate_content calls with the complete PDF as input. Historical runtime evidence showed 429 RESOURCE_EXHAUSTED on Gemini input-token quota.

## Decisions

1. Discovery is represented by a persisted job and is launched asynchronously.
2. The original source PDF is uploaded to Gemini Files API once per source content version and its reference is persisted.
3. Book Map generation uses that reusable original document.
4. Book Map topics must contain evidence-backed PDF page bounds.
5. Topic material discovery never passes the original full PDF. It creates bounded PDF slices in memory from the persisted local source and passes those slices inline to Gemini.
6. Large topics are split into persisted sequential chunks. Each chunk is checkpointed before the next chunk is processed.
7. Completed chunks are skipped on resume. Failed/running chunks are reset to pending by retry/recovery.
8. Structured JSON output is used for both map and material discovery.
9. Gemini errors are classified and quota exhaustion is not blindly retried.
10. Gemini implicit caching remains available automatically on supported models, but correctness does not depend on cache hits.
11. Explicit context caching is not a correctness dependency because the repaired design removes repeated full-corpus input from topic discovery; it remains subject to Google's current beta/billing/account constraints.
12. Draft → Review → Telegram is unchanged.

## Consequences

- Gemini model input is bounded by topic/chunk page range instead of fanning out the full PDF.
- The system can resume after a process interruption without rediscovering completed chunks.
- Page provenance is explicit and evidence-backed.
- A topic without a trustworthy page range fails explicitly rather than causing an unbounded full-document fallback.
- Additional local PDF processing dependency (pypdf) is used only to construct bounded in-memory document slices; no new queue or retrieval infrastructure is introduced.

## Evidence

Google's current document-processing documentation states that PDF inputs are processed with native visual/text understanding, Files API reuse is recommended for larger documents reused across requests, and PDF pages contribute meaningful input processing. Google's current caching documentation describes implicit caching on Gemini 2.5+ and explicit caching as a beta mechanism.