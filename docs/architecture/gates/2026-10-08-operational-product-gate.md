# Operational / Product Gate — 2026-10-08

## الهدف

فحص الرحلة التشغيلية الفعلية بعد اكتمال Artifact/Publication boundary، لتحديد أقرب فجوة تمنع Nashr من أن يكون منتجًا قابلًا للاستخدام مع عميل حقيقي.

## الرحلة المطلوبة

Source → Library → Production → Draft/Edit → Review → Approval → Publishing → Schedule → Telegram → Publication Ledger

## Evidence

- `/console` ما زالت مساحة Library القديمة وتحتوي upload / discovery / Book Map / materials.
- `/posts/workspace` و`/publishing` يعملان كمساحتين React مستقلتين عندما يكون frontend/dist موجودًا.
- Content Factory يمرر الاختيار إلى Publishing عبر `selected_post_ids` في URL، وليس عبر DOM أو global browser state.
- Publishing يستدعي `GET /posts?status=APPROVED&publication_state=ELIGIBLE`.
- Publishing يعيد فحص eligibility قبل إنشاء الخطة.
- Browser E2E يغطي Content Factory → Publishing boundary.
- Browser E2E يغطي إنشاء Schedule حقيقي عبر `POST /schedules` ويثبت HTTP 201 وpayload.
- Backend integration E2E يغطي مسار PDF ingestion حتى PUBLISHED Publication Ledger.
- لا يوجد Browser E2E يغطي الرحلة الكاملة من Library upload/discovery → production → review/approval → publishing → schedule execution → Telegram/publication ledger.

## Gate findings

### 1. Library — PASS WITH LEGACY UI

الوظائف الأساسية موجودة: upload، discovery، Book Map، materials. لكنها ما زالت ضمن legacy console وليست ضمن Browser E2E الكامل.

القرار: KEEP الآن. لا إعادة كتابة Library قبل إثبات حاجة تشغيلية.

### 2. Content Factory — PASS

المساحة تركز على Post Bank والإنتاج والتحرير والمراجعة والاعتماد. handoff إلى Publishing واضح عبر URL state.

القرار: KEEP.

### 3. Publishing — PASS

يبدأ من APPROVED + ELIGIBLE، ويعيد فحص eligibility قبل إنشاء Schedule. إنشاء الخطة يستخدم API الحقيقي في Browser E2E.

القرار: KEEP.

### 4. Schedule execution — PASS BACKEND / NOT FULL BROWSER PROVEN

الـbackend لديه durable schedule state، recovery، trigger، processing، retry، وintegration coverage.

لكن Browser E2E لا يثبت تنفيذ Schedule فعليًا حتى نتيجة النشر.

القرار: لا إعادة بناء scheduling. نضيف فقط إثباتًا تشغيليًا بالاختبار.

### 5. Telegram / Publication Ledger — PASS BACKEND / NOT FULL BROWSER PROVEN

المسار backend موجود ومغطى باختبار vertical slice، لكن لا يوجد Browser E2E كامل يثبت الرحلة من واجهة المستخدم حتى النتيجة النهائية.

القرار: لا تغيير في Telegram adapter أو Publication architecture. المطلوب اختبار تشغيلي فقط.

## Gate outcome

**CONDITIONAL PASS — PRODUCT PATH EXISTS, FULL BROWSER JOURNEY NOT YET PROVEN**

النظام يملك المسار التشغيلي الحقيقي في backend، والمساحات الرئيسية منفصلة، وواجهة Publishing لديها E2E حقيقي حتى إنشاء Schedule.

لكن لا ينبغي اعتبار Nashr بعدُ "رحلة مستخدم كاملة مثبتة" لأن Browser E2E لا يثبت المسار من Source/Library حتى النشر النهائي.

## KEEP

- Library / Content Factory / Publishing separation.
- Post as editorial source of truth.
- Artifact as provider-neutral output contract.
- Publication as distribution ledger.
- Schedule as timing/execution state.
- Existing APIs.
- Existing backend integration E2E.
- Telegram adapter boundary.

## ADD — NEXT IMPLEMENTATION

**Browser Operational Journey Test (اختبار رحلة تشغيلية كاملة عبر المتصفح)**.

يجب أن يثبت بأقل fixture ممكن:

1. دخول Library.
2. وجود/اختيار Source صالح.
3. الانتقال إلى material/production.
4. إنتاج Post DRAFT.
5. تعديل/اعتماد Post.
6. انتقال الاختيار إلى Publishing.
7. ظهور المنشور فقط ضمن APPROVED + ELIGIBLE.
8. إنشاء Schedule عبر API الحقيقي.
9. تفعيل/تنفيذ Schedule بطريقة deterministic test-safe.
10. إثبات النتيجة النهائية في Publication Ledger.

إذا كان استدعاء Telegram الحقيقي غير مناسب في CI، يستخدم الاختبار publisher test adapter / controlled test seam فقط عند حدود الاختبار، دون تغيير Production architecture ودون mock للـHTTP scheduling boundary.

## REFACTOR

لا يوجد refactor معماري مطلوب بناءً على هذا Gate.

## DEFER

- Library React migration.
- Identity.
- Recipe.
- Product abstraction.
- Artifact persistence.
- Review ownership migration.
- Scheduling ownership migration.

## PROHIBIT

- artifact_id migration.
- حذف Post.
- نقل Review إلى Artifact.
- إعادة كتابة Scheduling.
- queues/workers/microservices.
- Telegram logic داخل Artifact/Domain.
- إضافة abstraction جديد فقط لتحسين شكل architecture.

## Definition of Done للخطوة التالية

- Browser test يثبت الرحلة الأساسية من Source/Library إلى Publication Ledger.
- لا تغييرات في domain ownership لمجرد الاختبار.
- لا mocks تتجاوز الحدود التي نريد إثباتها.
- CI يمر.
- backend integration/E2E يبقى أخضر.
- بعد نجاح الاختبار فقط نقرر إن كانت هناك فجوة منتج فعلية تستحق PR جديدًا.