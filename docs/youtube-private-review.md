# Private YouTube review

The material's saved YouTube copy now has a private review panel. It displays exact title, description and tags, a proposed channel identifier explicitly marked unverified, explicit privacy and audience declarations, rights acknowledgement, optional review time/timezone and current blockers. No value defaults to public, no audience declaration is assumed, and preparing a draft is not upload consent.

Owner authentication and same-origin POSTs protect preview/save/cancel. Each saved snapshot binds original fingerprint, copy version, exact metadata, selected media inspection and every review choice. A changed choice or source invalidates the preview hash. Repeated saves return the same draft; local cancellation preserves history and permits a new draft. Proposed time is never a scheduler entry. Nothing invokes the dormant upload core, Google OAuth, private storage or a provider request.

This stage accepts a proposed channel ID and numeric category only as review intent. It does not verify ownership, availability or permitted categories. A real Google channel selector and category list require separate connection work. No source media URI, credential or resumable session capability is returned. A current inspection is shown if available; missing or blocked inspection remains a blocker even when a local preparation draft can be saved.
