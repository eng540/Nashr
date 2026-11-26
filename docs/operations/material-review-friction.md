# First material-review friction fixes

Observed on live mobile 390px, November 27:

- The approved-originals summary card promised copy/destination review but linked
  to publishing, not the matching approved library. It now links directly to
  `/bank?artifact_status=APPROVED`, the same central material review list.
- Expanding saved platform copies displayed no saved copies until a second read
  button. The first expansion now reads existing records only. It never prepares
  missing records, saves edits, approves, inspects bytes or publishes.

Read failures remain errors, not empty results. No automatic retry loop runs on
collapse/reopen. The explicit refresh remains. Reopening preserves dirty edits
without loading over them. Existing exact-platform handoffs use the same guarded
read path and do not cause another automatic read from the toggle event.

This is a bounded first UX repair, not a declaration that the site's entire UX
has been audited or improved. Facebook Reel still has a separate review route;
full batch preparation/approval remains separate work. No live writes or test
posts were used to find these defects.
