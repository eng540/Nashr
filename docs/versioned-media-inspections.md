# Private versioned media-inspection history

2026-11-24. Additive migration0059, no change to originals, platform fields, selection, scheduling or execution.

The existing inspect-media action remains read-only. A separate explicit action runs that same bounded probe and stores its result as private historical evidence. It records source fingerprint, copy version, whether original or current selection was inspected, selected-media ID, full byte hash, probe version, measured blockers/pending checks and inspection time. The source and copy are re-read under the existing lock order after network work before saving. A changed context never becomes a newly saved current record.

History returns the latest20 records for the artifact/platform only. Current/stale refers to those recorded bindings, not proof that storage bytes have not changed since inspection. The UI says this directly and retains all unverified checks. Source, copy version, media selection, approval/availability or probe-version changes mark evidence stale. Unselected historical media remains historical. There is no platform-acceptance, ready-to-publish or execution grant inferred from a saved result.

Records are append-only in this feature. GET history does not read storage or issue signed media links. No API accepts client-supplied measurements. Inspection can fail without a record, preserving existing work. This release does not feed saved results into scheduling eligibility or skip fresh execution checks.

Tests cover record/reload, read without storage access, stale copy/source/probe/selection, concurrent original change preventing save, unchanged original/copy fields/publication/schedule rows and mobile rendering. Migration upgrade/downgrade/upgrade tested on an isolated database.
