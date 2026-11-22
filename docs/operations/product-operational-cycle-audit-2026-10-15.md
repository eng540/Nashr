# تدقيق الدورة التشغيلية للمنتج — Nashr

**تاريخ التدقيق:** 2026-10-15  
**المستودع:** `eng540/Nashr`  
**الفرع المفحوص:** `main`  
**HEAD المفحوص:** `5846260adb07cff3d3e2da7041e8238d2eb19bf3` — `test: verify product prompt and identity persistence`  
**فرع التقرير:** `audit/operational-product-cycle-20261015`  
**Railway:** `zealous-communication / production / Nashr`  
**الرابط:** https://nashr-production.up.railway.app

## أ. الملخص التنفيذي

**قرار القبول: اجتازت جزئيًا مع فجوات محددة.**

الكود الموجود في `main` يثبت أن طبقات Control Plane وتثبيت الإصدارات والـ Recipe Engine وحفظ Artifact والمراجعة مصممة ومغطاة باختبارات مهمة. كما أن واجهات Railway الحالية تعيد منتجات منشورة بإصدارات ذات manifest مكوّنات.

لكن **لم تثبت الدورة التشغيلية الكاملة في Railway**. الدليل التشغيلي القابل للتتبع الذي أمكن قراءته هو مهمة الإنتاج التاريخية:

- المهمة: `9a1f240a-4e6f-4a69-859a-551b444af087`
- الحالة: `FAILED`
- المخرج: `artifact_id = null`
- السبب: مزود Gemini أعاد `429` بسبب حصة Free Tier
- حالة عملية المزود بقيت `SUBMITTED`

كما أن قائمة Railway الحالية، وعددها 26 Artifact، لم تعرض Artifact مرتبطًا بـ `production_job_id` أو سياق منتج يمكن ربطه بمهمة مكتملة. لذلك لا يجوز وصف الدورة بأنها مكتملة أو ناجحة تشغيليًا.

لم يتم أثناء التدقيق:

- إرسال أي محتوى إلى Telegram أو قناة خارجية.
- إنشاء مهمة إنتاج جديدة في Railway.
- تنفيذ نشر عام أو جدولة.
- تعديل بيانات الإنتاج أو المستخدمين.
- تنفيذ migration أو تغيير إعدادات Railway.
- استدعاء مزود توليد مدفوع جديد.

## ب. نطاق وأدلة البداية

### GitHub

- `main` يشير إلى `5846260adb07cff3d3e2da7041e8238d2eb19bf3`.
- آخر PR مدمج هو **PR #137**، الخاص باختبار حفظ `prompt_key` و`identity_key`.
- PRs #131 و#132 و#133 و#134 و#135 و#136 و#137 مدمجة في `main` بحسب سجل GitHub.
- تشغيل GitHub Actions الأخير على `main` للالتزام `5846260` انتهى بـ `success`.
- هذا يثبت نجاح CI على الالتزام، ولا يثبت نشر Railway أو نجاح مزود خارجي أو دورة إنتاج حقيقية.

### Railway — فحص قراءة فقط

- `GET /health` أعاد `200` و`{"status":"ok"}`.
- واجهات Control Plane التالية أعادت `200`: prompts, recipes, identities, policies, output-contracts, products.
- `GET /api/artifacts` أعاد 26 Artifact.
- الفحص الأول لـ `GET /api/control/products` أعاد `500`، ثم أعاد `200` في إعادة آمنة لاحقة؛ لم أعتبر ذلك عطلًا ثابتًا لغياب السجلات التشخيصية.
- ترويسات HTTP لا تكشف SHA النشر الفعلي. موصل Railway غير مفعّل في الجلسة، ولذلك **لا يمكن إثبات الالتزام المنشور فعليًا أو حالة migration عبر Railway API من هذه الجلسة**.

### المنتجات الحالية في Railway

أظهر `GET /api/control/products` أن المنتجات الحالية النشطة تحمل إصدارات منشورة ذات manifest مكوّنات، ومنها:

- `ARABIC_LITERATURE_TELEGRAM_POST` — الإصدار 2
- `ARABIC_LITERATURE_BRIEF_TELEGRAM_POST` — الإصدار 2
- `ARABIC_LITERATURE_TEXT` — الإصدار 2
- `ARABIC_LITERATURE_IMAGE` — الإصدار 2
- `ARABIC_LITERATURE_VIDEO` — الإصدار 2
- `ARABIC_LITERATURE_AUDIO` — الإصدار 2
- منتجات `QUL_WA_LA_TAQUL_*` و`WISDOM_SPARK_POST` بإصدارات منشورة ذات manifests

هذا يثبت وجود بيانات Control Plane المنشورة، لا استهلاكها بنجاح في تنفيذ إنتاج مكتمل.

## ج. مخطط المسار الفعلي في `main`

```text
Content Factory UI
  -> POST /production-jobs
     app/api/routes.py:create_production_job_route
  -> app/application/production_jobs.py:create_production_job
     - resolve_product()
     - resolve_prompt_version()
     - resolve_recipe_version()
     - resolve_identity_version()
     - resolve_policy_version()
     - resolve_output_contract_version()
     - ResolvedProductionContext.capture(...)
     - INSERT ProductionClaim + ProductionJob + ProductionJobItem(PENDING)
  -> app/main.py / BackgroundTasks
     run_production_job(job_id)
  -> ProductionJobRunner.run()
     - _recover_stale()
     - _claim_job()
     - _claim_next_item()
     - ProductionExecutionContext
  -> app/application/recipe_engine.py:ProductionRecipeEngine.execute()
     - resolve registered capability by recipe stage/key/version
     - pass pinned editorial prompt and stage configuration
  -> capability
     - produce_post / produce_text_artifact / produce_image_artifact /
       produce_video_artifact / produce_audio_artifact
     - provider adapter where applicable
     - validate output and output contract
  -> app/application/artifacts.py
     persist_generic_artifact() / ensure_post_artifact()
     - persist Artifact + resolved_context + contract provenance
  -> app/application/production_jobs.py
     _complete_item() with guarded RUNNING -> COMPLETED update
  -> GET /production-jobs/{id} and GET /production-jobs/{id}/items
  -> review
     POST review UI for POST, generic Artifact review API/UI for TEXT/IMAGE/VIDEO/AUDIO
  -> publication/distribution
     خارج نطاق هذا التدقيق، ولم يُنفّذ
```

### الملفات والنماذج الأساسية

| المرحلة | التنفيذ الفعلي |
|---|---|
| تعريف المنتج | `app/api/products.py`, `app/application/product_control_plane.py`, `ProductionProductModel`, `ProductionProductVersionModel` |
| نشر الإصدار | `ProductionProductControlPlaneService.publish()` |
| manifest | `ProductionProductDefinition.component_versions`، والـ migration `0043_product_component_manifest.py` |
| اشتقاق المنتجات | `derive_product()`، والـ migration `0044_product_derivation_lineage.py` |
| إنشاء المهمة | `create_production_job()` في `app/application/production_jobs.py` |
| تثبيت السياق | `ResolvedProductionContext` في `app/domain/production_context.py`؛ schema v6 للمنتج |
| التنفيذ | `ProductionJobRunner` ثم `ProductionRecipeEngine` |
| المخرج | `ArtifactModel` و`ProductionJobItemModel.artifact_id` |
| المراجعة | `app/api/artifacts.py` و`GenericArtifactReviewService` للمخرجات غير POST؛ مسار Post مستقل |
| الاستئناف/التعافي | `resume_production_job()` و`_recover_stale()` و`_reconcile_stale_item()` |

## د. جدول الإثبات

| المرحلة | النتيجة | الدليل | البيئة | ما بقي |
|---|---|---|---|---|
| تعريف المنتج | مثبت | API ونموذج المنتج واختبارات Control Plane | `main` + Railway GET | لا يوجد دليل صلاحيات/هوية مستخدم في هذا التدقيق |
| نشر إصدار المنتج | مثبت | `publish()` يبني manifest ويجعل الإصدار PUBLISHED | `main` + Railway GET | لا يوجد سجل نشر Railway يطابق SHA الكود |
| تثبيت prompt/identity/recipe/policy/contract | مثبت على مستوى الكود والاختبارات | `component_versions` و`ResolvedProductionContext`، و52 اختبار وحدة ناجح | `main` | اختبارات التكامل محجوبة محليًا لغياب PostgreSQL |
| عدم تغيير إصدار منشور بأثر رجعي | مثبت على مستوى الاختبار | `test_product_lifecycle_versions_and_published_reference_validation` واختبارات retry/manifest | `main`/CI | غير مثبت في Railway على مهمة جديدة فعلية |
| إنشاء ProductionJob | مثبت على مستوى الكود وAPI | `POST /production-jobs` واختبارات API | `main`/CI | لم تُنشأ مهمة جديدة في Railway بسبب ضوابط العزل |
| ربط المهمة بالمنتج والإصدار | مثبت على مستوى السياق | `resolved_context.product` في schema v6 | `main`/CI | لا توجد مهمة Railway مكتملة جديدة لإثباتها عمليًا |
| تمرير المكونات إلى المحرك | مثبت على مستوى الكود والاختبارات | `ProductionExecutionContext` و`_stage_system_prompt()` وcapabilities | `main`/CI | لا يوجد log تشغيلي من دورة ناجحة يثبت القيم الفعلية |
| تنفيذ إنتاج فعلي | فاشل | المهمة التاريخية `9a1f...` انتهت `FAILED` بسبب Gemini `429` | Railway | حصة/صلاحية المزود، ثم تشغيل معزول جديد عند توفر الاعتماد |
| حفظ Artifact | غير مثبت تشغيليًا لهذه الدورة | كود persistence واختبارات generic artifact؛ المهمة التاريخية بلا Artifact | `main`/CI + Railway | لا يوجد Artifact مرتبط بمهمة منتج مكتملة |
| ربط Artifact بالمهمة والمنتج | مثبت بنيويًا، غير مثبت تشغيليًا | `artifact_id` و`resolved_context` في النماذج والـ API | `main`/CI | قائمة Railway الحالية لم تعرض ارتباطًا صالحًا بمهمة مكتملة |
| المراجعة | مثبتة بنيويًا | Generic Artifact review API وحالات DRAFT/APPROVED/REJECTED | `main`/CI + Railway GET | لم تُراجع نتيجة ناتجة عن دورة منتج مكتملة |
| منع التوزيع الخارجي | مثبت ضمن حدود التدقيق | لم تُستدعَ Telegram أو publication؛ الضوابط والاختبارات تفصل المسار | هذه المهمة | لا يشمل ذلك إثباتًا عامًا لكل تشغيل مستقبلي |
| مطابقة Railway مع `main` | غير مثبت | HEAD GitHub معروف، لكن SHA Railway غير مكشوف وموصل Railway غير مفعّل | GitHub + Railway HTTP | يلزم Railway deployment metadata/logs |

## هـ. الفجوات والسبب الجذري

### 1. لا يوجد دليل قبول تشغيلي مكتمل على Railway

**النوع:** إعداد/تشغيل Railway أو provider readiness، وحفظ المخرجات.  
**السبب الجذري:** لم تُنفذ دورة جديدة معزولة ناجحة بعد نشر manifest الحالي، والمهمة التاريخية استخدمت منتجًا/سياقًا قديمًا وانتهت بحصة Gemini صفرية (`429`).  
**الأثر:** لا يمكن إثبات وصول كل المكونات إلى المحرك أو حفظ Artifact وربطه ومراجعته في الإنتاج.

### 2. حصة مزود الإنتاج تمنع التنفيذ

**النوع:** provider readiness.  
**الدليل:** `error_code=429`، ورسالة المزود: `limit: 0 requests per day on Free Tier`.  
**الأثر:** لا يجوز إعادة المحاولة عشوائيًا؛ قد يؤدي ذلك إلى فشل متكرر أو تكلفة غير مقصودة.

### 3. SHA النشر الفعلي وحالة migrations غير قابلين للتحقق من المسار المتاح

**النوع:** Railway observability/access.  
**السبب الجذري:** موصل Railway غير مفعّل ولا تكشف الخدمة العامة SHA أو migration revision.  
**الأثر:** `health=200` لا يكفي لإثبات أن الخدمة تعمل على `main` الحالي أو أن migration `0044` مطبقة.

### 4. اختبارات التكامل المحلية لم تعمل

**النوع:** بيئة اختبار.  
**الدليل:** 50 اختبار تكامل فشلوا لأن PostgreSQL المحلي غير مستمع على `localhost:5432`؛ هذا مانع بيئي وليس فشلًا وظيفيًا مثبتًا في الكود.  
**الأثر:** لا أخلط نجاح 52 اختبار وحدة مع إثبات تكامل قاعدة البيانات.

### 5. توجد مخاطر معروفة، لكنها ليست فجوات جديدة أعيد تنفيذ إصلاحها

الكود الحالي يعالج بالفعل عدة ملاحظات سابقة:

- فحص `rowcount` في `_complete_item()`.
- reconciliation للمخرج أو provider operation قبل إعادة المهمة stale.
- حجز `PROVIDER_OUTCOME_UNKNOWN` عند عدم وجود مخرج أو handle.
- تثبيت manifest كامل للمنتج عند النشر.
- تمرير الـ editorial context المثبت إلى الفيديو.

لذلك لم أعد تنفيذ إصلاحات PRs #109–#137، ولم أضف migration أو إعادة هيكلة تخمينية.

تبقى، وفق الوثائق الحالية، تغطية fault-injection الشاملة لحدود provider/storage/DB، وإجراء operator reconciliation، وإثبات المراجعة لكل modality، مسائل acceptance لاحقة وليست مثبتة بدورة Railway الناجحة.

## و. التغييرات المنفذة في هذه المهمة

- لم يتغير كود التشغيل.
- أُضيف هذا التقرير فقط.
- أُنشئ فرع العمل:
  `audit/operational-product-cycle-20261015`
- سيُرفع PR توثيقي مستقل، ولن يُدمج ولن يُنشر على Railway ضمن هذه المهمة.

## ز. حالة Railway

| البند | الحالة |
|---|---|
| الخدمة | تستجيب لـ `/health` بـ `200` |
| Control Plane GET | متاح وقت الفحص؛ المنتجات تعرض manifests منشورة |
| المخرج | 26 Artifact في القائمة، دون Artifact مرتبط ظاهرًا بمهمة منتج مكتملة |
| المهمة التاريخية القابلة للتتبع | `9a1f240a-4e6f-4a69-859a-551b444af087` — `FAILED` |
| سبب الفشل | Gemini `429`, Free Tier daily limit 0 |
| provider operation | `SUBMITTED` في سجل العنصر، دون Artifact |
| SHA المنشور | غير مثبت؛ لا تكشفه الخدمة العامة ولا يوجد موصل Railway مفعّل |
| migration revision | غير مثبت من هذه الجلسة |
| Telegram/النشر الخارجي | لم يُنفذ |

## ح. قرار القبول

**اجتازت جزئيًا مع فجوات محددة.**

تثبت `main` بنيويًا ومساريًا أن المنتج ليس مجرد تعريف محفوظ: manifest يُبنى عند النشر، والسياق يُثبت عند إنشاء المهمة، والمحرك يستهلك السياق، والمخرج يملك مسار persistence/review. لكن معيار الدورة التشغيلية الكاملة يتطلب Artifact ناتجًا فعليًا في Railway مرتبطًا بمهمة ومنتج وإصدار مكونات، وهذا غير متوفر في الأدلة الحالية.

## ط. أصغر مجموعة أعمال تالية

1. تمكين وصول قراءة فقط إلى Railway deployment metadata/logs أو توفير SHA المنشور وmigration revision.
2. معالجة provider readiness/الحصة خارج هذا التدقيق، دون تغيير إعدادات الإنتاج تلقائيًا.
3. تنفيذ تشغيل واحد فقط في مصدر تجريبي معزول ومنتج manifest-backed، بعد التحقق من عدم وجود تشغيل مدفوع عالق.
4. حفظ evidence غير حساس: product/version، job/item، component versions، provider operation، Artifact، signed media readback، review status.
5. عدم اعتماد الدورة إلا بعد نجاح: job `COMPLETED`، item `COMPLETED`، Artifact `AVAILABLE`، ربط `artifact_id`، `resolved_context.product`، وإمكانية استرجاع المخرج بعد إعادة التحميل.
6. تشغيل اختبارات التكامل في PostgreSQL مع migrations مطبقة، ثم إضافة fault-injection/concurrency coverage للفجوات المذكورة في وثيقة shared production engine.

## حدود هذا التقرير

هذا التقرير يميز صراحة بين:

1. الكود المدمج في GitHub.
2. نجاح CI.
3. صحة HTTP/health في Railway.
4. بيانات Control Plane الحية.
5. نجاح دورة إنتاج فعلية.

لا يُستنتج أحدها من الآخر.


## ي. تحديث القبول التشغيلي بعد التدقيق

**تاريخ التحديث: 2026-10-15 — إفادة لاحقة من مالك المشروع.**

بعد إعداد اللقطة التاريخية أعلاه، أكد مالك Nashr أن دورة تشغيل أحدث اكتملت فعليًا: المنتجات المنشورة استُخدمت في مهام الإنتاج، أُنتجت المخرجات المتوقعة، ثم اعتُمدت ونُشرت ووصلت إلى Telegram.

بناءً على هذه الإفادة، تُسجّل حالة المشروع الحالية على النحو التالي:

- **الدورة التشغيلية الأساسية للمنتج: مكتملة وفق تأكيد التشغيل الفعلي من المالك.**
- لا يُعاد فتح المهمة التاريخية الفاشلة المذكورة أعلاه باعتبارها وصفًا للحالة الحالية؛ تبقى سجلًا تاريخيًا لواقعة سابقة.
- لا يُدّعى أن فحص هذه الجلسة أعاد تنفيذ الدورة أو التقط معرفات المهمة والمخرج أو سجلات النشر الناجح؛ هذه التفاصيل لم تُرفق في الإفادة.
- نجاح دورة المنتج الأساسية لا يعني تلقائيًا أن جميع أنواع المخرجات (TEXT / IMAGE / VIDEO / AUDIO) اجتازت كل اختبارات القبول المستقلة، ولا يلغي اختبارات الموثوقية والتعافي المتبقية.

### القرار المحدّث

**مقبول تشغيليًا للدورة الأساسية للمنتج وفق تأكيد المالك.**  
تُغلق فجوة «لم تثبت دورة ناجحة» كحالة عمل راهنة؛ ويُحتفظ بوصف الأدلة التفصيلية في القسمين السابقين بوصفه لقطة زمنية لما كان متاحًا عند التدقيق، لا حكمًا يناقض النجاح اللاحق.

### الخطوة التالية — من دون إعادة الدورة من البداية

1. اعتماد هذا الإنجاز كخط أساس: تعريف منتج منشور → مهمة إنتاج → مخرج → مراجعة/اعتماد → نشر فعلي إلى Telegram.
2. الانتقال إلى قبول تعدد المخرجات، مع إثبات منفصل لكل نوع: TEXT وIMAGE وVIDEO وAUDIO، بما يشمل حفظ Artifact، واسترجاعه بعد إعادة التحميل، وظهوره في مساحة المراجعة، وتسجيل حالة المراجعة.
3. إكمال اختبارات الأعطال والتزامن حول provider / object storage / DB، بما في ذلك النتائج الملتبسة ومنع التوليد المكرر.
4. توفير إجراء آمن للمشغّل لحسم الحالات المعلقة غير المؤكدة، دون تجاوز تلقائي أو إعادة توليد غير مأمونة.
5. إكمال المقاييس وسجل التشغيل التشغيلي لمهام stale ونتائج provider غير المؤكدة، والتحقق من حالة CI والنشر بعد كل دمج.

لا تتضمن هذه الخطوة إرسالًا جديدًا إلى Telegram، ولا تشغيل مزود مدفوع، ولا تعديلًا على بيئة الإنتاج.
