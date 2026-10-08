# Nashr Current Architecture Baseline

Baseline commit: bf62b410136224f20ef2bc4fee6d4ad89e5deb19
Branch: main

الغرض: تسجيل الحالة الفعلية بعد دمج PR #49 (Artifact Boundary Foundation).

## 1. الحالة الفعلية

الأساس الحالي:
API → Application → Domain → Infrastructure / Adapters

تم تثبيت Frontend Foundation للمساحات المهاجرة، كما توجد مصادر ومعرفة وBook Map واستخراج وإنتاج ومراجعة وجدولة ونشر وتوزيع وjobs durable وidempotency وprovenance.

تمت إضافة Artifact Boundary في PR #49:
- `Artifact` كـdomain output contract.
- `ArtifactKind.POST` كأول نوع مخرج.
- `post_to_artifact()` كـadapter صريح من Post إلى Artifact.
- Production Job Runner يكمل العنصر من خلال artifact.id مع إبقاء `post_id` persistence contract كما هو.
- characterization test يحمي التحويل.

## 2. ما لم يتغير عمدًا

- Post ما زال مصدر الحقيقة persistence للمحتوى الحالي.
- Review ما زال يغيّر حالة Post.
- Publication persistence ما زالت تحمل `post_id`.
- Scheduling persistence ما زالت تحمل `post_id`.
- Telegram ما زال adapter خارجيًا.
- لا Identity / Recipe / Product.
- لا queue/worker infrastructure.
- لا schema rewrite.

## 3. الملاحظة المعمارية

Artifact أصبح boundary حقيقيًا لكنه ما زال transitional:
Production يعرف نتيجة generic عبر adapter، بينما Review/Publication/Scheduling ما زالت تقرأ Post مباشرة.

هذا مقبول مؤقتًا لأن نقل ownership دفعة واحدة سيكسر contracts الحالية ويجمع عدة تغييرات عالية المخاطر.

## 4. قرار ما بعد PR #49

**PASS — الانتقال إلى Artifact Consumption تدريجيًا.**

القاعدة التالية:
1. لا ننقل persistence ownership قبل وجود consumer حقيقي للـArtifact.
2. أول consumer مرشح هو Publication domain/application لأنه يمثل output بعد الإنتاج وقبل distribution.
3. Review وScheduling يبقيان متوافقين مع Post حتى يصبح Artifact state/identity contract أكثر نضجًا.
4. لا نضيف `artifact_id` migration في هذه المرحلة.
5. يمكن جعل Publication domain يرى `artifact_id` كهوية المخرج الحالية، مع استمرار `post_id` في persistence عبر adapter.
6. يجب أن يبقى فحص APPROVED النهائي قبل النشر.
7. يجب أن يبقى PUBLISHED→SKIPPED وidempotency.
8. Telegram لا يدخل Domain Artifact.

## 5. القرار

التالي هو PR صغير بعنوان Artifact Consumption in Publication:
- تحويل Post إلى Artifact عند حدود publication.
- جعل Publication domain يتعامل مع هوية artifact الحالية.
- إبقاء DB/API compatibility.
- إضافة characterization tests.
- دون migration.

بعد نجاحه نعيد gate قبل أي نقل ملكية persistence.
