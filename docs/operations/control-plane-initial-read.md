# Control Plane initial-read race

The postmerge331 run had183browser cases pass and one fail: a new product key
became empty after filling it.330's later full run passed, but that does not
invalidate the observed failure.

A deterministic mocked test reproduces both a stale successful initial read
resetting fields and a stale failure replacing current UI state. React StrictMode
in development invokes the initial effect twice. Previously either completion
could set loading false, so an older pending completion could arrive after editing
started. No331logic touched ControlPlane.

The patch gives reload operations a monotonically increasing generation and
invalidates it on effect cleanup. Stale success/error/finally results cannot
change state. Loading only clears for the current read. No endpoint, write or
schema changes. This is specifically initial/reload ordering, not a claim to fix
all item-selection races.

Verification: identical deterministic tests fail twice on unchanged main330 and
pass after the patch, including three repeated runs each for late success/error.
21unit tests and production build pass. Screenshot uses mocked empty lists and
retained NEW_PRODUCT/New product fields, not a product created in production.
