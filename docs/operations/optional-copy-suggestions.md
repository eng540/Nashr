# Optional copy suggestions

Implementation is separated from service activation. Production endpoints never
construct or resolve a provider. A configured Gemini key or model does not enable
this feature. The UI clearly reports the live service as disabled and preserves
the saved fields unchanged. No new external disclosure or generation cost occurs.

An injected provider can produce proposals in tests. The Gemini adapter reuses
the central retry/model policy but is deliberately unreachable from production
endpoints pending verified permission and cost coverage. Its prompt treats source
text as data, requests source-grounded language and no description of unseen
media. Suggestions are not guaranteed factually correct and need full review.

Each valid proposal is stored apart from the original and copy, pinned to source
fingerprint, copy version and saved-fields digest. Creating it changes no approval,
media, destination, schedule or publishing authorization. UI shows full before and
after fields. Apply is explicit, checks staleness under the original row lock,
uses the existing copy mutation checks, and consumes the proposal once. Applying
changes only that platform copy and bumps its version; original approval remains.
Unsupported platforms stay blocked. Invalid/provider-failed output leaves exact
saved fields. Over-limit platform output remains visible and blocked, not cut.

Production acceptance still outstanding: permission/cost check, live provider
activation and a separately authorized real service check. No generated hooks or
SEO outcome are claimed from a disabled service. Until then, manual copy editing
and unchanged-original fallback continue to work.
