# Read-only Meta batch review worksheet

A selected approved-original batch can now be reviewed together below its saved destination controls. The worksheet reads each selected original's distribution readiness and saved platform copies with at most four concurrent read chains. It never creates copies, operation previews, decisions, schedules, uploads or publications.

Only saved selected Instagram/Facebook targets are displayed for each material, in the exact selected-original order. Other selected platforms remain named as outside this worksheet, never substituted. No Meta choice is inferred for an original without one. Stale destination choices stay flagged as historical choices that must be reviewed and saved before continuing. Missing copies remain missing. Field acceptance is distinct from media/account/execution readiness. Existing operation/history checks are explicitly outside this worksheet.

A read failure, identity mismatch, missing Meta target inventory or malformed copy response blocks the entire batch result rather than showing a plausible partial set. Late results from a prior selection are discarded. Changing selected IDs clears local proposed times.

Optional start, IANA zone and elapsed-minute interval fields compute a local-only proposed time per material, not per platform. They have no defaults and never get sent to execution APIs or carried into commit links. Existing timezone conversion rejects invalid dates, unknown zones, DST gaps and ambiguous repeated hours. A proposal is not checked against a provider's future execution window and does not establish permission, account validity or absence of an existing scheduled/published operation.

This is a pre-execution worksheet, not completed batch scheduling. Existing separate platform review links remain. A future durable batch plan would still need a separate exact snapshot, stale-check, conflict/duplicate handling and explicit execution-decision workflow before it can create any schedule.

Proof is local: seven mocked-browser cases cover saved per-item exceptions, copy text, optional local time calculation, missing choices/copies, stale choices, incomplete or mismatched responses, failed reads, late results and a DST repeated-hour refusal. Eight adjacent browser cases cover approval handoff and destination/copy workflows. Reads create zero writes. No live content or schedule was created for acceptance.
