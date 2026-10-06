# ADR 0002 — Nashr Target Architecture

Status: Accepted as target architecture baseline
Date: 2026-10-02

## Context

Nashr بدأ كمسار رأسي يربط مصدرًا/كتابًا بالمعرفة ثم Post ثم مراجعة وجدولة ونشر Telegram.

الاتجاه المستهدف أوسع: مصادر متعددة، Knowledge Inventory قابل لإعادة الاستخدام، هويات متعددة، وصفات إنتاج متعددة، مخرجات متعددة، منتجات وقنوات توزيع متعددة.

الخطر هو استخدام "البساطة الحالية" لبناء حدود نعرف مسبقًا أنها ستحتاج إلى إعادة بناء.

## Decisions

### 1. Stable architecture, progressive implementation

المعمارية والحدود الأساسية تحدد الآن. التنفيذ على مراحل. لا نؤجل Foundation معروفة إلى مرحلة لاحقة بحجة أن الميزة غير مطلوبة اليوم.

### 2. Modular Monolith

Nashr يبقى modular monolith مع حدود Domain/Application/Infrastructure واضحة.

### 3. Reference flow

Source → Knowledge → Control Plane → Production → Artifact → Review → Publication → Distribution

### 4. Control Plane

Identity وPolicies وTaxonomy وPrompt Templates وRecipes وOutput Contracts تمثل behavior/intent/context ولا تصبح Python hard-coded داخل Production Engine.

### 5. Capability / Provider separation

المحرك يستدعي capabilities عبر ports/adapters. Provider APIs لا تتسرب إلى Domain.

### 6. Artifact بدل Post

Post هو مخرج من مخرجات المسار الحالي، وليس abstraction النهائي لكل أنواع الإنتاج.

### 7. Telegram ليس Domain core

Telegram هو أول Distribution Adapter.

### 8. Database is source of truth

Jobs وruns والحالات المهمة durable.

### 9. Versioned production

نتيجة الإنتاج ترتبط بالإصدارات المؤثرة عندما تدخل هذه الطبقات إلى التنفيذ.

### 10. Frontend boundary

الواجهة المستهدفة React + TypeScript + Vite + Tailwind production build + query layer + E2E. HTML/JS embedded داخل FastAPI ليس Target Architecture.

### 11. Security and ownership

Authentication وAuthorization وworkspace ownership من اهتمامات الأساس.

## Consequences

الإيجابيات:
- إضافة Identity دون إعادة بناء Production Engine.
- إضافة Recipe دون نسخ pipeline.
- إضافة Output/Distribution دون جعل Telegram شرطًا.
- استبدال AI provider خلف adapter.
- توسيع الواجهة دون cross-workspace DOM coupling.
- تفسير نتائج الإنتاج عبر versioning.

التكاليف:
- Refactoring مطلوب قبل التوسع الكبير.
- انتقال تدريجي من Post-centric إلى Artifact-centric.
- تأسيس Frontend حقيقي.
- انضباط في ADRs وcontracts والاختبارات.

## Explicit non-goals

لا يعني القرار إضافة Microservices أو Kafka/RabbitMQ أو Kubernetes أو Redis كqueue أو Graph DB أو Vector DB أو Agent swarm الآن.

هذه تقنيات اختيارية تعتمد على حاجة مثبتة.

## Change rule

أي تغيير لهذا القرار يجب أن:
1. يكون موثقًا في ADR جديد.
2. يعتمد على evidence من النظام أو التشغيل.
3. يوضح أثره على البيانات والعقود والmodules.
4. يملك خطة migration.
5. لا يضيف Rewrite غير مبرر.

الهدف ليس تجميد التقنية؛ الهدف منع العشوائية وإعادة البناء التي يمكن تجنبها.
