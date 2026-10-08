# Nashr Current Architecture Baseline

Baseline commit: f25764e91bc8f704dd080d5270d894cfc4011607
Branch: main

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