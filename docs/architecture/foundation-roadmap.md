# Nashr Foundation Roadmap

هذه الخطة هي مسار التنفيذ من الحالة الحالية إلى Target Architecture.

## القاعدة

لا نستخدم "التوسع لاحقًا" مبررًا لبناء Foundation مؤقتة.

ننّفذ القدرة تدريجيًا، لكن الحدود الأساسية تصمم الآن بما يخدم المسار المعروف.

## المرحلة 0 — Architecture Gate

قبل أي بناء كبير:
1. قراءة وثائق architecture وADR.
2. فحص main الفعلي.
3. تحديد module/contract المتأثر.
4. تحديد هل التغيير Capability أم Foundation.
5. التأكد من عدم إدخال coupling جديد مع Telegram أو Post ككيان نهائي أو Prompt/Identity hard-coding أو UI workspace آخر أو Provider محدد.
6. تحديث الوثيقة/ADR إذا تغير قرار معماري.

المخرج: Keep / Refactor / Replace / Defer.

## المرحلة 1 — Frontend Foundation

الأولوية لأن الواجهة الحالية embedded في Python وستصبح عائقًا مع زيادة workspaces.

الهدف:
React + TypeScript + Vite + Tailwind production build + Router + TanStack Query + shared UI + Playwright.

المسار:
1. تثبيت API contracts الحالية.
2. استخراج Frontend تدريجيًا.
3. إنشاء App shell وworkspace boundaries.
4. نقل Publishing وPost Bank بدون تغيير business behavior.
5. إضافة E2E للمسارات الحرجة.
6. إزالة cross-workspace DOM coupling.
7. عدم تغيير business logic أثناء النقل إلا عند الحاجة الموثقة.

بوابة النجاح: المسارات الحالية تعمل من Browser حقيقي مع E2E.

## المرحلة 2 — Domain Boundary Stabilization

تثبيت المفاهيم:
Source
Knowledge / Inventory
Identity
Production Recipe
Production Run
Artifact
Review
Product
Publication
Distribution

المسار الحالي يستمر.

بوابة النجاح: ملكية كل مفهوم ومسؤولية كل module وعقده واضحة.

## بوابة ما بعد المرحلة 1 — Artifact Gate

بعد نجاح Frontend Foundation يجب تنفيذ Architecture Gate على main الفعلي. تم تسجيل هذا gate في docs/architecture/gates/2026-10-06-post-pr47.md.

نتيجة gate الحالي: PASS. المرحلة التالية هي Artifact Boundary بحدود صغيرة وتوافقية، وليس schema rewrite.

## المرحلة 3 — Artifact Boundary

الانتقال من Post-centric إلى Artifact-centric:

Knowledge
→ Production Run
→ Artifact
→ Review

Post يصبح نوعًا مناسبًا للمخرج الحالي.

يجب الحفاظ على compatibility مع البيانات والمسار الحالي.

بوابة النجاح: Production Engine لا يحتاج معرفة أن كل مخرج Telegram Post.

## المرحلة 4 — Control Plane Foundation

التنفيذ الأول لهذه المرحلة هو Prompt Control Plane Foundation: Prompt Template + Versioning + Resolver + API + UI + Runtime Consumer. هذا لا يعني تنفيذ Identity أو Policy أو Recipe كاملة.

إدخال:
- Identity
- Policy
- Taxonomy/Knowledge configuration
- Prompt templates
- Output contracts
- Versioning

قواعد:
- لا Python داخل configuration.
- لا secrets داخل configuration.
- لا SQL/security policy قابلة للكتابة من Identity.
- Prompt ليس بديلًا عن Policy أو Recipe.
- كل version مؤثر في Production Run يسجل.

بوابة النجاح: تغيير سلوك تحريري/إنتاجي معروف لا يتطلب تعديل Python في المحرك.

## المرحلة 5 — Recipe / Production Engine

تحويل المسار الحالي إلى Recipe:
BOOK_TO_TELEGRAM_POST

ثم تعميم stages/capabilities:
Retrieve, Classify, Select, Transform, Generate, Validate, Render.

بوابة النجاح: إضافة Recipe ثانية لا تتطلب نسخ Production Engine أو pipeline خاص.

## المرحلة 6 — Distribution Boundary

فصل:
Publication
→ Distribution Adapter

Telegram يبقى أول adapter.

بوابة النجاح: إضافة channel ثانٍ دون تعديل Domain الخاص بالإنتاج.

## المرحلة 7 — Product Layer

بعد Artifact وRecipe:
Artifacts
→ Product
→ Publication

بوابة النجاح: تمثيل منتج معرفي/تعليمي مختلف دون تحويل Post إلى abstraction زائف.

## المرحلة 8 — Security / Workspace Boundary

قبل التوسع:
- Authentication
- Authorization
- Workspace ownership
- identity ownership
- credentials isolation
- audit trail

## المرحلة 9 — Observability & Operations

Correlation عبر:
Request → Job → Production Run → Artifact → Review → Publication → Distribution

مع metrics للأخطاء وزمن المراحل وإعادة المحاولة.

## المرحلة 10 — Additional Capabilities / Recipes

إضافة هويات ووصفات ومخرجات ومنتجات وقنوات جديدة فوق نفس المحرك والأساس.

## ترتيب الأولويات

0. Architecture Gate
1. Frontend Foundation
2. Domain Boundary
3. Artifact
4. Control Plane
5. Recipe / Production Engine
6. Distribution
7. Product
8. Security / Workspace
9. Observability
10. More capabilities/products

قد تتداخل الأعمال، لكن لا يجوز تجاوز Foundation blocker للوصول إلى Feature جديدة.

## Definition of Done للـFoundation

1. الحدود واضحة في الكود.
2. API contracts مستقرة.
3. الاختبارات تحمي behavior.
4. E2E يغطي المسارات الحرجة.
5. migration آمنة إن وجدت.
6. لا يوجد coupling جديد معروف عبر الحدود.
7. التشغيل الفعلي متحقق.
8. الوثائق محدثة.
9. PR منفصل وقابل للمراجعة.
10. لا يوجد Rewrite مخفي مؤجل.

## ممنوعات

- بناء نسخة مؤقتة معروفة بأنها ستُستبدل.
- تأجيل Frontend architecture إلى بعد تضخم الواجهة.
- جعل Identity hard-coded في Python.
- جعل Recipe if/else متضخم.
- جعل Prompt واحد يمثل Identity + Policy + Recipe.
- جعل Telegram شرطًا في Domain.
- إدخال distributed infrastructure دون حاجة.
- الادعاء بنجاح runtime دون تحقق.
- دمج Foundation PR قبل الاختبارات والمراجعة.

## النتيجة

Capabilities وRecipes وIdentities وArtifacts وProducts وChannels تنمو، بينما Foundation وDomain boundaries وContracts وExecution model وData ownership وProvider boundaries وFrontend architecture تبقى مستقرة.

هذا هو معنى:
> الوصول ثم التوسع = البناء فوق نفس الأساس، وليس إعادة بناء الأساس.


## Shared Production Engine Reliability Program — implementation status (2026-10-11)

The Recipe / Production Engine phase is implemented for multiple output kinds, but the **reliability acceptance gate remains in progress**. Do not mark the whole phase complete until lifecycle recovery, capability conformance, fault-injection, UI visibility, and production evidence are complete.

Merged PRs on `main`:
- #108 — lifecycle audit.
- #109 — guarded item completion transition.
- #110 — shared production engine and capability contract.
- #111 — common Artifact result validation.
- #112 — stale recovery reconciles Artifact/provider-operation state and holds unknown outcomes.
- #113 — ambiguous video start outcome classification.
- #114 — shared ambiguous provider outcome classification for text/image/audio and fal image calls.
- #115 — regression test for persisted Artifact recovery.
- #117 — API/UI expose RUNNING and unresolved-outcome counts; suppress unsafe retry.
- #118 — adapter-boundary fake tests for ambiguous text/image/audio provider outcomes.

Next work, in dependency order:
1. Controlled operator reconciliation procedure/action for `PROVIDER_OUTCOME_UNKNOWN` and `PRODUCTION_OUTPUT_RECONCILIATION_REQUIRED` items; UI now exposes item-level details, but resolution is not implemented because it needs an authenticated/controlled mutation path.
2. Fault injection for object-store/DB crash windows and concurrent resume/claim behavior.
3. Shared contract integration tests for POST/TEXT/IMAGE/VIDEO/AUDIO and review visibility after reload.
4. Operational runbook, stale-item metrics, provider operation age, output-storage verification, and exact Railway deployment evidence.

No new queue or microservice is approved by this status update. Telegram publication is excluded from reliability tests.


## Product architecture and operational memory — 2026-10-13

The product layer has reached versioned definitions and UI integration, but the next milestone is not adding more generic components: it is proving that each published product version resolves into a complete immutable runtime manifest and that all execution/resume/retry paths honor it.

Follow [Product Model and Gap Audit](product-model-and-gap-audit.md) for evidence and acceptance criteria. Target behavior is proposed in [ADR-001](decisions/ADR-001-product-version-manifest.md), which remains Proposed until the full model/API audit and review are complete. No schema migration is authorized by the audit alone.

Priority order:
1. Audit product, identity, prompt, recipe, policy, and output-contract models/repositories/migrations/APIs and all production-job creation paths.
2. Verify pinned context on create, resume, and retry, including legacy compatibility.
3. Read-only inspect the previous `QUL_WA_LA_TAQUL_VIDEO` job, provider operation, Artifact, and storage metadata before considering a new generation.
4. Trace video duration from product/experience to recipe, provider request, and returned media metadata.
5. Add focused tests and narrow implementation PRs only for demonstrated gaps.
6. Update [Product Architecture Operational Status](../operations/product-architecture-status.md) with exact CI/deployment/live evidence.

Do not send to Telegram, publish externally, or launch duplicate paid provider work.

## Product Layer acceptance checkpoint (2026-10-13)

The Product Layer is **in progress**, not complete. A candidate branch `feat/immutable-product-component-manifest` implements explicit component references for prompt, identity, recipe, policy, and output contract, freezes those references on product publication, and resolves them for job creation. It also adds a compatibility migration for built-in post/text products while preserving their prior published versions.

Remaining in dependency order:
1. Complete CI and review for the manifest branch, including migration and legacy job tests.
2. Implement independent product derivation with parent lineage and an auditable component diff in Control Plane.
3. Complete preflight compatibility validation across product, recipe, output contract, capability, and available provider.
4. Decide and verify video duration based on the actual output, not only a requested metadata value.
5. Update this roadmap and ADR-001 with merge evidence; record Railway deployment and live acceptance separately.

Until these gates pass, do not describe the Product Layer or ADR-001 as accepted. No external publication is part of these tests.

