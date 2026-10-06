# Nashr Documentation

هذه الوثائق هي نقطة الدخول المعمارية والتنفيذية الرسمية لمشروع Nashr.

## قاعدة العمل

قبل أي PR أو بناء أو ترقية كبيرة، يجب قراءة:
1. Target Architecture
2. Current Baseline
3. Foundation Roadmap
4. ADR 0002

## المبدأ الثابت

> Progressive Implementation, Stable Architecture
> تنفيذ تدريجي، معمارية مستقرة.

المراحل تضيف قدرات فوق الأساس نفسه. لا نبني تنفيذًا مؤقتًا معروفًا أنه سيجبرنا لاحقًا على إعادة بناء الأساس.

## الوثائق

- architecture/target-architecture.md: المعمارية المستهدفة وحدود النظام.
- architecture/current-baseline.md: الحالة الفعلية المثبتة عند baseline الحالي.
- architecture/foundation-roadmap.md: ترتيب التثبيت والترقية والخطوات القادمة.
- adr/0002-nashr-target-architecture.md: القرارات المعمارية الملزمة.

## قاعدة تغيير الوثائق

إذا أدى PR لاحق إلى تغيير قرار معماري أو حدود أساسية، يجب تحديث الوثائق في نفس PR أو إنشاء ADR جديد يوضح السبب والأثر.

هذه الوثائق لا تستبدل اختبارات النظام أو مراجعة الكود أو التحقق التشغيلي.


## Frontend Foundation

- [Frontend Architecture](architecture/frontend.md) — React/API boundary, workspace isolation, state and E2E migration policy.
