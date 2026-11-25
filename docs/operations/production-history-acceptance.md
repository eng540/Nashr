# Production history and acceptance boundaries

2026-11-25. The production workspace now has a bounded, newest-first history of existing jobs, filtered by technical status. It links to the existing job-follow-up route and from completed items to existing content-bank outputs. Reads neither create jobs nor resume them. Summary reads deliberately omit prompts and full resolved contexts.

## Evidence

- Backend integration coverage: ordering, pagination, filtering, invalid query values, summary shape and no attempt/status mutations. Existing job-detail APIs unchanged.
- Browser regression: mobile history error/retry, pagination, status filter resets page, selected job reload, artifact link and zero writes.
- Live acceptance remains required after deployment: use an existing successful job only. Never generate a paid job merely to fill this evidence gap.

## Reconciled scope

Historical UX audit gaps are not all current open work. Central artifact review, automatic eligible-platform copy preparation, distribution targeting/queue, review navigation, source analysis restoration, known-ID job error handling and saved-plan response ordering have subsequent implementations. They should not be reimplemented based on the older audit text alone.

Remaining acceptance boundaries include live successful-job restoration until demonstrated, per-modality generated-output evidence without paid regeneration, and platform account/provider constraints. A working Facebook/Instagram workflow does not prove all connectors work. Production history does not authorize generation, retries, posting or spending. Existing approval, selection and dispatch rules remain unchanged.
