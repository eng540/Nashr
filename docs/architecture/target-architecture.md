# Nashr Target Architecture

الحالة: Target Architecture / Baseline
المبدأ: Progressive Implementation, Stable Architecture

## 1. هوية النظام

Nashr ليس نظامًا لتحويل كتاب إلى منشور Telegram.

الهدف المعماري:
منصة إنتاج معرفي متعددة المصادر والهويات ومسارات الإنتاج والمخرجات والتوزيع، تفصل المعرفة عن نية الإنتاج وعن التنفيذ التقني.

المسار المرجعي:

Source
→ Knowledge / Inventory
→ Control Plane
→ Production Engine
→ Content Artifact
→ Review / Approval
→ Product / Publication
→ Distribution

## 2. Control Plane

تحدد ماذا نريد من محرك الإنتاج.

تتكون من:
- Identity
- Knowledge
- Taxonomy
- Policies
- Instructions
- Prompt Templates
- Production Recipes
- Output Contracts

Identity تمثل الغاية التحريرية/المنتجية: Purpose, Audience, Voice, Tone, Principles, Objectives, Constraints.

Policy تمثل قواعد الاختيار والجودة والاستبعاد والسلامة والتحرير.

Prompt مكوّن من مكونات التحكم، وليس هوية النظام كلها.

Recipe تحدد تسلسل الإنتاج.

Output Contract يحدد شكل المخرج.

## 3. Production Engine

المحرك مسؤول عن كيف ننفذ، لا عن الغاية التحريرية.

القدرات العامة قد تشمل:
- Retrieve
- Extract
- Classify
- Select
- Transform
- Generate
- Validate
- Render

المحرك يستقبل المدخلات وسياق Control Plane والقدرات ويُنشئ Production Runs وArtifacts.

## 4. Capability / Provider Boundary

القدرة التقنية تكون خلف Port/Adapter.

Production Engine
→ Capability Port
→ Provider Adapter
→ Gemini أو مزود آخر

Provider-specific APIs وretries وtimeouts وquota وrate limits لا تتسرب إلى Domain.

## 5. Source وKnowledge

Source هو الأصل ذو provenance. PDF/Book نوع من أنواع Source وليس تعريف النظام.

المعرفة المستخرجة تصبح Canonical Knowledge Inventory قابلة لإعادة الاستخدام.

Source
→ Canonical Knowledge
→ Identity A / Recipe A
→ Identity B / Recipe B
→ Identity C / Recipe C

لا نعيد تحليل المصدر لكل هوية عندما تكون المعرفة نفسها قابلة لإعادة الاستخدام.

## 6. Artifact

الوحدة العامة المستهدفة هي Content Artifact، وليس Post.

يمكن أن يمثل لاحقًا:
Text, Post, Article, Thread, Image, Audio, Video, Carousel, Lesson, Course component, PDF, Newsletter.

لا يلزم تنفيذ كل الأنواع الآن، لكن يجب ألا تجعل المعمارية Post أو Telegram شرطًا على قلب النظام.

## 7. Review

Production لا يساوي Review ولا Approval ولا Publication ولا Distribution.

المراجعة بوابة بشرية مستقلة.

## 8. Product / Publication / Distribution

Artifact
→ Product عند الحاجة
→ Publication
→ Distribution

Telegram هو أول Distribution Adapter وليس مفهومًا مركزيًا في Domain.

## 9. Platform Foundation

الأساس الحالي المناسب للاستمرار:
- Python
- FastAPI
- PostgreSQL
- SQLAlchemy
- Alembic
- durable jobs
- storage abstraction
- AI/provider adapters
- configuration
- security boundary
- observability
- deployment/runtime controls

لا نضيف Microservices أو Kafka أو Kubernetes أو Redis لمجرد الحداثة. التقنية الجديدة تحتاج حاجة تشغيلية أو معمارية مثبتة.

## 10. Execution

الحالة الدائمة في قاعدة البيانات:

API
→ Persist Job
→ Execute
→ Persist State
→ Retry / Recover / Resume

الذاكرة وprocess state ليست مصدر الحقيقة.

## 11. Data Architecture

PostgreSQL هو مصدر الحقيقة للكيانات والعلاقات.

- relational model للكيانات الأساسية.
- JSONB فقط للبيانات المرنة المناسبة.
- provenance وversioning جزء من التصميم.
- migrations لأي تغيير schema.

## 12. Versioning

Production Run يجب أن يستطيع تسجيل الإصدارات المؤثرة عند دخول هذه الطبقات إلى التنفيذ:
- source version
- knowledge version
- identity version
- policy version
- recipe version
- prompt version
- model/provider
- output schema version

الهدف هو تفسير سبب إنتاج النتيجة.

## 13. Security

Authentication وAuthorization وownership/workspace boundary وعزل الأسرار والاعتمادات والتدقيق من اهتمامات الأساس، لا ميزات مؤجلة.

## 14. Observability

العمليات المهمة يجب أن تكون قابلة للتتبع عبر request/job/run/source/artifact/publication identifiers.

## 15. Architectural Style

Modular Monolith مع حدود Domain/Application/Infrastructure واضحة.

لا يوجد التزام بـMicroservices. إذا أصبح فصل خدمة مطلوبًا، يكون استخراجًا من حدود قائمة وليس إعادة بناء.

## 16. المسار الحالي

Book
→ Book Map
→ Knowledge/Materials
→ Post
→ Review
→ Schedule
→ Telegram

يُعامل معماريًا باعتباره Production Recipe أولى:
BOOK_TO_TELEGRAM_POST

وليس تعريف Nashr.

## 17. القاعدة الحاكمة

> الكود يوفّر القدرات.
> التهيئة تحدد السلوك.
> المعرفة توفر السياق.
> الوصفة تحدد مسار الإنتاج.
> الهوية تحدد الغاية التحريرية.
> المخرج يمثل Artifact/Product.
> التوزيع ينفذ الوصول إلى القناة.
