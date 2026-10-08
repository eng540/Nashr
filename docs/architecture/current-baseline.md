# Nashr Current Architecture Baseline

Baseline commit: 89d672a24783099e6d586f501baada7e9a6be363
Branch: main

الغرض: تسجيل الحالة الفعلية بعد PR #53، الذي فعّل Artifact consumption عند حدود Publication دون تغيير persistence/API/browser contracts.

## 1. الحالة الفعلية

الأساس الحالي:
API → Application → Domain → Infrastructure / Adapters

Frontend Foundation موجودة للمساحات المهاجرة، مع React + TypeScript + Vite + Tailwind + TanStack Query + Playwright، بينما بقية المساحات legacy تعمل ضمن الهجرة التدريجية.

المسار التشغيلي الحالي:
Source → Knowledge / Inventory → Production → Post-backed Artifact → Review → Publication → Telegram Distribution.

تم تنفيذ Artifact Boundary على مرحلتين:
- PR #49: إنشاء `Artifact` كـdomain output contract وadapter من Post.
- PR #53: جعل Publication يستهلك Artifact عند الحد الفعلي للنشر، بما في ذلك إنشاء مسودة Telegram، والتحقق من الحالة والمحتوى، ومسار Scheduling قبل استدعاء Telegram.

## 2. الملكية الحالية

### Artifact
- `Artifact` هو contract محايد للمخرج.
- `ArtifactKind.POST` هو النوع الحالي.
- لا يعرف Artifact شيئًا عن Telegram أو أي provider.

### Post
- ما زال مصدر الحقيقة persistence للمحتوى والحالة التحريرية الحالية.
- Review ما زال يملك انتقالات DRAFT / APPROVED / REJECTED.
- لا يوجد قرار بنقل Post أو إزالته الآن.

### Publication
- Publication persistence ما زالت تحمل `post_id` للتوافق.
- المحتوى الذي يذهب إلى publisher يأتي من Artifact في المسار الجديد.
- توجد compatibility path داخل `ApproveAndPublish` لتحويل Post persisted إلى Artifact عند عدم تمرير Artifact صراحة.
- لذلك Publication هو أول consumer حقيقي للـArtifact، لكنه ليس boundary مكتمل الاستقلال بعد.

### Scheduling
- Schedule/ScheduleItem ما زالت Post-centric في الهوية وeligibility/persistence.
- التنفيذ يستخرج Artifact قبل إنشاء Publication وقبل استدعاء `ApproveAndPublish`.
- يجب أن يبقى فحص APPROVED النهائي قبل النشر.
- يجب أن يبقى PUBLISHED → SKIPPED وidempotency.

### Review
- Review ما زال Post-centric عمدًا.
- تعديل المحتوى يعيد الحالة إلى DRAFT ويلغي العناصر المجدولة المعلقة.
- لا ننقل Review إلى Artifact في هذه المرحلة.

### Distribution
- Telegram يبقى Adapter خارجيًا.
- لا يدخل Telegram في Artifact أو Domain.

## 3. ما تم إثباته في PR #53

- Post → Artifact adapter موجود ومستخدم.
- CreateTelegramDraft يستطيع العمل من Artifact.
- ApproveAndPublish يقبل Artifact صريحًا ويفرض APPROVED قبل النشر.
- Scheduling يمرر Artifact إلى مسار النشر.
- `post_id` persistence محفوظ.
- API/browser contracts لم تتغير.
- لا migration.
- لا Identity / Recipe / Product.
- لا queues/workers.
- PUBLISHED → SKIPPED وidempotency محفوظان.

## 4. الفجوة الحالية

Artifact Boundary أصبح حقيقيًا، لكنه **Transitional**.

الفجوة الأساسية ليست غياب Artifact؛ بل وجود compatibility coupling داخل Publication:
- `ApproveAndPublish` ما زال يستطيع تحميل `PostModel` مباشرة عندما لا يُمرر Artifact.
- توجد بعض فحوص approval/content المكررة على Post لضمان التوافق.
- لذلك لا يصح بعد القول إن Post اختفى من Publication application boundary.

هذه الفجوة صغيرة ومحددة، ولا تبرر migration أو إعادة تصميم واسعة.

## 5. قرارات KEEP / REFACTOR / DEFER / PROHIBIT

| Area | Decision |
|---|---|
| Artifact domain contract | KEEP |
| Post → Artifact adapter | KEEP |
| Production → Artifact | KEEP |
| Publication → Artifact | KEEP + HARDEN |
| Post persistence | KEEP |
| Review | KEEP / DEFER refactor |
| Scheduling persistence & eligibility | KEEP / DEFER refactor |
| Telegram adapter | KEEP |
| Identity | DEFER |
| Recipe | DEFER |
| Product | DEFER |
| `artifact_id` migration | PROHIBIT NOW |
| Post removal/rename | PROHIBIT NOW |
| Queue/worker infrastructure | PROHIBIT NOW |
| Domain-specific Telegram logic | PROHIBIT |

## 6. القرار الحالي

**PASS WITH CONTROLLED REFACTOR.**

يمكن الاستمرار بعد PR #53، لكن لا ننقل ملكية Review أو Scheduling إلى Artifact بعد.

الخطوة التنفيذية التالية هي PR صغير بعنوان تقريبي:

**Harden Publication Artifact Boundary**

هدفه:
1. جعل Artifact هو المدخل الداخلي الواضح لمسار publication.
2. حصر PostModel → Artifact compatibility في adapter/application edge بدل تكرارها داخل منطق النشر.
3. إزالة/تقليل فحوص Post المباشرة المكررة داخل `ApproveAndPublish` دون تغيير السلوك.
4. الحفاظ على `post_id`, API/browser contracts, APPROVED gate, idempotency, وPUBLISHED → SKIPPED.
5. إضافة tests تثبت أن publication لا يستخدم content مختلفًا عن Artifact.
6. لا migration، ولا نقل Review/Scheduling ownership.

بعد هذا PR فقط نعيد Architecture Gate لتحديد هل أصبحت Review/Scheduling جاهزة لخطوة لاحقة.

## 7. ممنوعات المرحلة

- لا `artifact_id` migration.
- لا حذف Post.
- لا نقل Review إلى Artifact لمجرد وجود Artifact.
- لا إعادة كتابة Scheduling.
- لا Identity / Recipe / Product.
- لا queues/workers/microservices.
- لا تغيير API/browser contracts.
- لا إدخال Telegram في Domain.
- لا تحسينات جودة/ذكاء واسعة داخل هذا المسار.

## 8. Definition of Done للمرحلة الحالية

1. Publication يستهلك Artifact بوضوح.
2. Post compatibility محصورة عند الحافة.
3. السلوك الحالي محفوظ باختبارات backend وE2E القائمة.
4. APPROVED gate النهائي محفوظ.
5. idempotency وPUBLISHED → SKIPPED محفوظان.
6. لا schema/API/browser migration.
7. هذه الوثيقة وGate مرتبطان بـmain الحالي.
