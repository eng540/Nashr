# Nashr Current Architecture Baseline

Baseline commit: 4adc1abc609c0b6f67e95bd49313603f11cf7b42
Branch: main

الغرض: تسجيل الحالة الفعلية التي بُنيت عليها Target Architecture، وليس الادعاء بأن النظام وصل إلى الهدف النهائي.

## 1. الموجود حاليًا

المستودع يملك أساسًا layered واضحًا:
API → Application → Domain → Infrastructure / Adapters

وتوجد وحدات فعلية للمصادر، المعرفة، Book Map، الاستخراج، الإنتاج، المراجعة، الجدولة، المنشورات والتوزيع.

كما توجد:
- PostgreSQL / SQLAlchemy / Alembic
- migrations متتابعة حتى 0014_schedule_idempotency
- Gemini adapters وسياسة Gemini مركزية
- fake adapters للاختبار
- durable discovery/production/scheduling job state
- provenance للمادة
- Book Map وcheckpoints
- editorial review
- publication/scheduling
- Telegram publishing adapter
- unit/integration tests
- CI workflow

## 2. ما يجب الحفاظ عليه

- FastAPI / Python / PostgreSQL / SQLAlchemy / Alembic.
- طبقات Domain/Application/Infrastructure.
- Gemini adapter boundary وسياسة Gemini المركزية.
- durable jobs والاسترداد وidempotency.
- provenance وBook Map.
- فصل Review عن Scheduling/Publication.
- الاختبارات الحالية كأساس، مع توسيعها.

## 3. الفجوات المعمارية

### Post-centric domain

الإنتاج والمخرجات ما زالت مرتبطة بـPost في أجزاء من النظام.

الهدف: Artifact عام، وPost يصبح نوعًا من المخرجات.

الإجراء: Refactor تدريجي، لا Rewrite.

### Identity

لا توجد حاليًا طبقة مكتملة first-class تعبر عن Identity كـControl Plane.

### Production Recipe

Book → Post موجود كمسار تطبيقي، لكنه ليس Recipe مستقلة قابلة للتهيئة.

### Product

لا يوجد Product عام يفصل تجميع/تقديم المخرجات عن Artifact.

### Distribution coupling

Telegram موجود كAdapter، لكن أجزاء من scheduling/application ما زالت مرتبطة بمفاهيم Telegram/وجهة Telegram.

### Frontend boundary

الواجهة الحالية تحتوي HTML/JS داخل app/api/*.py، ما يسمح بتداخل DOM ومسؤوليات الـworkspaces. ظهرت هذه الفئة من المشاكل فعليًا في Publishing.

### Frontend architecture

لا يوجد Frontend application مستقل بمعمارية React/TypeScript/build pipeline.

الهدف: React + TypeScript + Vite + Tailwind production build + Query layer + E2E.

### Browser E2E

اختبارات التكامل الحالية ليست بديلًا كاملًا لاختبار Browser E2E.

### Security / ownership

الهدف المستقبلي يحتاج Authentication/Authorization وownership/workspace boundary قبل التوسع متعدد الهويات والمستخدمين.

### Observability

يوجد structured/event-like logging، لكن target architecture يحتاج correlation عبر Request → Job → Run → Artifact → Publication.

## 4. ما لا نعتبره فجوة تلقائيًا

لا نعتبر Microservices أو Kafka/RabbitMQ أو Kubernetes أو Redis كـqueue أو Graph DB أو Vector DB أو Agent swarm ديونًا لمجرد عدم وجودها.

تدخل فقط عند وجود حاجة مثبتة.

## 5. توصيف الحالة

الوصف الأدق:
Production-capable vertical slice + early platform core، مع ارتباطات تحتاج تثبيتًا قبل التحول إلى منصة متعددة الهويات والمسارات والمخرجات.

النظام ليس بدائيًا ولا يحتاج Rewrite، لكنه يحتاج Foundation Refactoring في الحدود المذكورة.

## 6. حدود هذه الوثيقة

هذه baseline عند commit المحدد أعلاه. إذا تغير main لاحقًا، يجب تحديث baseline أو إنشاء baseline جديد بدل افتراض أن الوثيقة ما زالت تصف الحالة الحالية.
