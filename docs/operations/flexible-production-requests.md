# Flexible production requests

The content factory exposes three request modes: a published product, a published product plus task-scoped instructions, and custom guidance without a product.

Task instructions are persisted on the Production Claim and appended to the pinned execution prompt by the existing production runner. They do not mutate published product versions or override recipe, output-contract, policy, or execution constraints.

Direct text is represented with the existing Source and KnowledgeUnit lineage. It is not stored in a parallel library. Flexible requests preserve the explicit order of selected materials; legacy requests retain the existing order-independent behavior.

Productless production requires the user to choose an existing published recipe compatible with the current Post production capability and TELEGRAM_POST output contract. Image, audio, and video remain product-backed unless a compatible productless recipe and contract are implemented.

Job details expose the mode, product if present, task instructions, input preview, and actual source material titles. Results continue through the existing review and publishing flow; this feature does not publish externally.

Validation must include backend integration tests, frontend typecheck/build, and browser E2E. A successful CI run is not proof of deployment; deployment and production behavior are reported separately.
