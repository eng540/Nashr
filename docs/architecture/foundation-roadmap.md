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
