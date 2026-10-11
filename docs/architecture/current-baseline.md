# Nashr Current Architecture Baseline

Historical snapshot commit: f25764e91bc8f704dd080d5270d894cfc4011607
Branch: main

> **تنبيه تحديث:** هذا الملف يسجل لقطة تاريخية بعد PR #55، وليس وصفًا كاملًا للحالة التشغيلية الحالية. راجع قسم Shared Production Engine Reliability أدناه ووثيقة العقد المشترك.

الغرض: تسجيل الحالة الفعلية بعد PR #55، الذي أنهى مرحلة Harden Publication Artifact Boundary دون تغيير persistence أو API/browser contracts.

## 1. الحالة الفعلية

الأساس الحالي:
Frontend / Presentation → HTTP API → FastAPI → Application → Domain → Infrastructure / Adapters

المسار التشغيلي الحالي:
Source → Knowledge / Inventory → Production → Post-backed Artifact → Review → Scheduling / Publication → Telegram Distribution.

الحدود الأساسية الحالية:
- Library: Source / Knowledge / Inventory.
- Content Factory: Production / Post / Review.
- Publishing: Publication / Scheduling / Telegram Distribution.
- Artifact: contract عام للمخرج بين الإنتاج والاستهلاك، وليس مخزن بيانات مستقلًا.

## 2. الملكية الحالية

### Artifact
- `Artifact` هو contract محايد للمخرج.
- `ArtifactKind.POST` هو النوع الحالي.
- لا يعرف Artifact شيئًا عن Telegram أو أي provider.
- `post_to_artifact` و`post_model_to_artifact` يحولان التمثيل الحالي إلى Artifact.
- التحميل من persistence إلى Artifact محصور في application adapter.

### Post
- ما زال مصدر الحقيقة للـpersistence التحريرية الحالية.
- يملك DRAFT / APPROVED / REJECTED.
- يظل هو الهوية المستخدمة حاليًا في Review وScheduling persistence.
- لا يوجد قرار بحذفه أو استبداله.

### Review
- Review ما زال Post-centric عمدًا.
- الموافقة/الرفض/التعديل تتم على Post.
- تعديل المحتوى يعيد الحالة إلى DRAFT ويلغي عناصر الجدولة المعلقة.
- توجد حماية تمنع التعديل التحريري أثناء تنفيذ عنصر نشر PROCESSING.
- لا توجد حاجة معمارية حالية لنقل ملكية Review إلى Artifact.

### Publication
- Publication يستهلك Artifact صريحًا داخل مسار النشر.
- `ApproveAndPublish` يعتمد داخليًا على Artifact في فحوص الحالة والمحتوى.
- Post → Artifact fallback موجود فقط عند حافة التوافق مع callers/persistence الحالية.
- `post_id` ما زال محفوظًا عمدًا.
- provider call خارج transaction قاعدة البيانات.
- APPROVED gate وidempotency وPUBLISHED → SKIPPED محفوظة.

### Scheduling
- Schedule/ScheduleItem ما زالت Post-centric في الهوية وeligibility وpersistence وواجهات API.
- مسار التنفيذ يحول Post إلى Artifact قبل Publication.
- فحص APPROVED النهائي قبل النشر محفوظ.
- التزامن/منع التكرار وحالات PUBLISHED/SKIPPED وdurable state محفوظة.
- لا ننقل ملكية Scheduling إلى Artifact الآن.

### Distribution
- Telegram يبقى Adapter خارجيًا.
- لا Telegram داخل Artifact أو Domain.

## 3. نتيجة PR #55

PR #55 أغلق الفجوة المحددة في Gate بعد PR #53:
- Publication أصبح Artifact-first داخل منطق النشر.
- compatibility path محصورة عند application edge.
- فحوص approval/content الأساسية لم تعد تعتمد مباشرة على PostModel.
- أضيفت تغطية لاستخدام محتوى Artifact الصريح.
- أضيفت regression coverage لمسار PostModel compatibility.
- لم تتغير schema أو API/browser contracts.

## 4. قرار Architecture Gate الحالي

**PASS — BOUNDARY HARDENED**

لم تعد هناك فجوة معمارية صغيرة تستدعي PR آخر داخل Publication قبل الانتقال.

الأهم: نجاح PR #55 لا يعني أن كل شيء يجب أن يتحول إلى Artifact.

الملكية الحالية مقصودة:
- Post → editorial persistence/state.
- Artifact → generic production output contract.
- Publication → distribution ledger.
- Schedule → timing/execution state.

وجود Artifact لا يبرر نقل Review أو Scheduling تلقائيًا.

## 5. KEEP / REFACTOR / ADD / DEFER / PROHIBIT

| Area | Decision |
|---|---|
| Artifact domain contract | KEEP |
| Post → Artifact adapter | KEEP |
| Publication → Artifact | KEEP |
| Publication compatibility edge | KEEP AS COMPATIBILITY EDGE |
| Post persistence/editorial state | KEEP |
| Review ownership | KEEP / DEFER |
| Scheduling ownership | KEEP / DEFER |
| Scheduling execution → Artifact | KEEP |
| Telegram adapter | KEEP |
| Frontend workspace separation | KEEP |
| Identity | DEFER |
| Recipe | DEFER |
| Product abstraction | DEFER |
| artifact_id migration | PROHIBIT NOW |
| Post removal/rename | PROHIBIT NOW |
| Review → Artifact ownership migration | PROHIBIT NOW |
| Scheduling → Artifact persistence migration | PROHIBIT NOW |
| Queue/worker/microservice expansion | PROHIBIT NOW |
| Telegram logic inside Artifact/Domain | PROHIBIT |

## 6. ما يجب فحصه قبل PR تنفيذي جديد

المرحلة المعمارية Artifact/Publication مكتملة بما يكفي للانتقال.

قبل إنشاء PR تنفيذي جديد يجب أن يكون القرار مبنيًا على قيمة تشغيلية فعلية، وليس على الرغبة في مزيد من التجريد.

الأولوية الآن:
1. التحقق من أن Library / Content Factory / Publishing تمثل حدود المنتج فعليًا في الواجهة.
2. التحقق من أن Content Factory يركز على Production → Draft/Edit → Review → Approval دون إدخال scheduling controls فيه.
3. التحقق من أن Publishing يعرض APPROVED + eligible فقط عند التخطيط للنشر.
4. التحقق من رحلة المستخدم الكاملة عبر Browser E2E.
5. التحقق من المسار التشغيلي الفعلي حتى Telegram/Publication Ledger.
6. بعد ثبات الرحلة، الانتقال إلى capability/identity configuration فقط إذا أثبت الاستخدام حاجة حقيقية.

## 7. ممنوعات المرحلة التالية

- لا Artifact database table.
- لا `artifact_id` migration.
- لا حذف Post.
- لا نقل Review إلى Artifact لمجرد التماثل.
- لا إعادة كتابة Scheduling ownership.
- لا Identity / Recipe / Product قبل الحاجة التشغيلية.
- لا queues/workers/microservices.
- لا إدخال Telegram في Domain.
- لا مزج Library / Factory / Publishing في workspace واحد.
- لا إضافة abstraction جديد دون consumer حقيقي واختبار واضح.

## 8. Definition of Done لهذه المرحلة

1. Publication boundary hardened.
2. Artifact contract provider-neutral.
3. Post remains editorial source of truth.
4. Review/Scheduling ownership remains explicit and stable.
5. API/browser/schema contracts preserved.
6. Existing backend/E2E regression coverage remains green.
7. Architecture documentation points to main HEAD f25764e9.
8. Next implementation is selected from operational/product evidence, not speculative model migration.

## Shared Production Engine Reliability — status update (2026-10-11)

Current reviewed main after PR #120: `f24e8b1a99351c4acd6c59db4e40ff77db937478`.

The production platform now includes registered POST/TEXT/IMAGE/VIDEO/AUDIO capabilities, a generic Artifact persistence/review path, pinned production context, private media storage, and durable provider-operation fields. The shared reliability work is progressing through small PRs rather than replacing the engine or adding a new queue.

Merged reliability changes:
- PR #108: lifecycle audit and confirmed-gap inventory.
- PR #109: completion transition checks the conditional update row count; backend/frontend/E2E CI passed on the PR head.
- PR #110: shared engine/capability/result/error/recovery contract; CI passed on the PR head.
- PR #111: provider-neutral Artifact envelope validation before item completion; CI passed on the PR head.
- PR #112: stale recovery reconciles an existing Artifact or persisted provider operation; unknown outcomes are held instead of blindly regenerated; retry of unresolved outcomes is blocked. CI passed on the PR head.
- PR #113: video start timeouts/ambiguous errors use `PROVIDER_OUTCOME_UNKNOWN`; CI passed on the PR head.
- PR #114: common ambiguous-provider error classification integrated with text, Gemini image, fal image, and Gemini TTS call boundaries; CI passed on the PR head.
- PR #115: regression test proves a persisted Artifact is reused after a simulated crash before item completion; CI passed on the PR head.
- PR #117: API/UI expose RUNNING and reconciliation-held counts; the Content Factory warns and hides retry when outcome is unresolved; CI passed on the PR head.
- PR #118: fake-provider timeout regressions for Gemini text/image/audio prove the shared unknown-outcome error contract; CI passed on the PR head.
- PR #120: item API and Content Factory show which outputs are held for reconciliation, including provider/operation diagnostics where recorded; retry remains disabled. CI passed on the PR head.

Remaining before calling the engine fully accepted:
1. Add a controlled operator resolution procedure/action for held unknown outcomes; the UI now identifies the exact items and available provider metadata, but intentionally has no unsafe retry override.
2. Expand fault-injection coverage for object upload / DB persistence split, provider success with lost output, and concurrent resume across all capabilities.
3. Verify review visibility for every modality after page reload; the job progress/counts and unsafe-retry warning are now implemented, but all modality review paths still need acceptance coverage.
4. Add/verify production observability and runbook metrics for stale items and unknown provider outcomes.
5. Verify the exact post-merge main CI and Railway deployment state separately; PR CI is not production evidence.

Telegram remains outside this program's tests. No live provider generation was used for these PRs.
