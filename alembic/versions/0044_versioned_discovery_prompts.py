"""Version and expose knowledge-discovery AI instructions in Control Plane."""
from __future__ import annotations

import json
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0044_versioned_discovery_prompts"
down_revision: Union[str, Sequence[str], None] = "0043_product_component_manifest"
branch_labels = None
depends_on = None

PROMPT_SPECS = [
    {
        "key": "knowledge.book_map.system",
        "name": "استخراج بنية الكتاب",
        "purpose": "التوجيه التحريري لاستخراج بنية الكتاب من نوافذ PDF المحدودة.",
        "versions": [
            {"version": 1, "status": "ARCHIVED", "body": "أنت مستكشف بنية كتاب، ولست كاتب محتوى.\nأنت تعمل على نافذة محدودة من الكتاب؛ افهم فقط ما تثبته الصفحات الممررة لك، ولا تدّعِ معرفة ما خارجها.\nاستخرج البنية الموضوعية الظاهرة في هذه النافذة: الأقسام والمحاور والموضوعات ذات المعنى التي تكشف تنظيم المحتوى فعلاً.\nلا تفترض أن كل كتاب له فصول رسمية. قد يكون التجميع موضوعياً أو مفاهيمياً أو زمنياً أو أدبياً أو غير ذلك.\nلا تستخدم تصنيفاً مغلقاً ولا تفرض عدداً معيناً من الموضوعات. إذا لم توجد موضوعات ذات معنى فأعد topics فارغة.\nلا تستخرج مواد منشورات في هذه الخطوة ولا تخترع عناوين.\nلكل موضوع، أعد page_start و page_end كأرقام الصفحات المطلقة في الكتاب، على أن تقع بالكامل داخل النافذة الممررة.\nsource_reference اختياري ولا يوضع إلا إذا كان مدعوماً من الصفحات الممررة.\nحافظ على ترتيب ظهور الأقسام عندما يكون واضحاً."},
            {"version": 2, "status": "PUBLISHED", "body": "أنت مستكشف بنية كتاب، ولست كاتب محتوى.\nأنت تعمل على نافذة محدودة من الكتاب؛ افهم فقط ما تثبته الصفحات الممررة لك، ولا تدّعِ معرفة ما خارجها.\nاستخرج البنية الموضوعية الظاهرة في هذه النافذة: الأقسام والمحاور والموضوعات ذات المعنى التي تكشف تنظيم المحتوى فعلاً.\nلا تفترض أن كل كتاب له فصول رسمية. قد يكون التجميع موضوعياً أو مفاهيمياً أو زمنياً أو أدبياً أو غير ذلك.\nلا تستخدم تصنيفاً مغلقاً ولا تفرض عدداً معيناً من الموضوعات. إذا لم توجد موضوعات ذات معنى فأعد topics فارغة.\nلا تستخرج مواد منشورات في هذه الخطوة ولا تخترع عناوين.\nلكل موضوع، أعد page_start و page_end كأرقام الصفحات النسبية داخل ملف النافذة الممررة، على أن تقع بالكامل داخل هذه النافذة. سيحوّل النظام هذه الأرقام لاحقًا إلى أرقام PDF مطلقة.\nsource_reference اختياري ولا يوضع إلا إذا كان مدعوماً من الصفحات الممررة.\nحافظ على ترتيب ظهور الأقسام عندما يكون واضحاً."}
        ],
    },
    {
        "key": "knowledge.book_map.section",
        "name": "تعليمات نافذة خريطة الكتاب",
        "purpose": "قالب المهمة وحدود الصفحات الخاصة بكل نافذة عند استخراج بنية الكتاب.",
        "versions": [
            {"version": 1, "status": "PUBLISHED", "body": "هذه نافذة محدودة من كتاب وليست الكتاب كاملاً. النافذة تحتوي {{window_page_count}} صفحة PDF، وتمثل الصفحات المطلقة {{page_start}}-{{page_end}} من الكتاب. حلّل فقط الصفحات الموجودة في الملف الممرر لك. مهم جداً: حقلا page_start و page_end في إجابتك يجب أن يكونا أرقام الصفحات النسبية داخل الملف الممرر فقط، ويجب أن يتراوح كل منهما بين 1 و {{window_page_count}}. لا تستخدم أرقام الصفحات المطبوعة داخل الكتاب ولا أرقام الصفحات المطلقة في هذه الحقول. سيحوّل النظام هذه الأرقام النسبية لاحقاً إلى أرقام PDF مطلقة. استخرج البنية الموضوعية الظاهرة في هذه النافذة، ويمكن للموضوع أن يبدأ أو ينتهي خارجها؛ في هذه الحالة اجعل page_start/page_end حدوداً محافظة لما تثبته النافذة فقط. لا تنشئ مواد منشورات."}
        ],
    },
    {
        "key": "knowledge.book_map.merge",
        "name": "دمج خرائط الكتاب",
        "purpose": "قالب دمج الخرائط المحلية مع الحفاظ على ترتيب الصفحات والمراجع.",
        "versions": [
            {"version": 1, "status": "PUBLISHED", "body": "أنت الآن تقوم بدمج خرائط محلية متجاورة لكتاب واحد.\nادمج فقط البنية المدعومة في الخرائط الممررة، بما في ذلك دمج الموضوعات المتصلة عبر حدود النوافذ عندما تدعمها الأدلة.\nرتّب الموضوعات حسب ظهورها في الكتاب.\nلا تخترع موضوعاً جديداً غير موجود في الخرائط.\nلا تستخدم تصنيفاً مغلقاً ولا تفرض عدداً معيناً.\nحافظ على page_start/page_end كحدود PDF مطلقة.\nأعد عنوان الكتاب ووصفه من الأدلة المتاحة.\nيجب أن تكون جميع page_start/page_end بين 1 و {{page_count}}.\nهذه مرحلة دمج، وليست مرحلة استخراج مواد منشورات.\n\nجولة الدمج: {{round_index}}\nدفعة الدمج: {{batch_index}}\nعدد النوافذ الأصلية في المهمة: {{section_count}}\n\nالخرائط:\n{{payload}}"}
        ],
    },
    {
        "key": "knowledge.material_discovery.system",
        "name": "اكتشاف المواد من الكتاب",
        "purpose": "التوجيه التحريري لاكتشاف المواد الأصلية داخل نطاق صفحات موضوع محدد.",
        "versions": [
            {"version": 1, "status": "PUBLISHED", "body": "أنت مستكشف مواد تحريرية داخل نطاق صفحات محدد من موضوع في كتاب.\nاستخرج فقط المواد الموجودة فعلاً في الصفحات التي تم تمريرها لك والمرتبطة بالموضوع.\nلا تخترع مادة ولا تعيد صياغة فكرة عامة لمجرد أنها مناسبة لوسائل التواصل.\nيمكن أن تكون المادة حكمة أو قصة أو قولاً أو لطيفة أو مفهوماً أو تعريفاً أو شعراً أو موقفاً أو مثالاً أو مفارقة أو قاعدة أو وصفاً أو سيرة أو حدثاً أو مقارنة أو أي نوع آخر حقيقي في المصدر.\nلا تفرض عدداً ثابتاً من المواد. أعد صفر مادة عندما لا توجد مادة مستقلة مفيدة في هذا النطاق.\nلا تكرر نفس المقطع أو نفس الفكرة داخل النطاق.\nحافظ على معنى المصدر والنص الأصلي عند الاقتباس.\nأعد source_reference فقط إذا كان مدعوماً من الصفحات الممررة. لا تخمن أرقام الصفحات.\nرقّم النتائج من 1 داخل هذا النطاق."}
        ],
    },
    {
        "key": "knowledge.material_discovery.context",
        "name": "سياق اكتشاف المواد",
        "purpose": "قالب سياق الكتاب والموضوع وحدود الصفحات المرسلة إلى نموذج اكتشاف المواد.",
        "versions": [
            {"version": 1, "status": "PUBLISHED", "body": "عنوان الكتاب: {{source_name}}\nالموضوع: {{topic_title}}\nوصف الموضوع: {{topic_description}}\nنطاق المصدر الممرر: صفحات PDF {{page_start}}-{{page_end}}. تعامل مع هذا النطاق فقط ولا تفترض محتوى خارج الصفحات الممررة."}
        ],
    },

]


def upgrade() -> None:
    op.add_column(
        "discovery_jobs",
        sa.Column("resolved_prompts", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    bind = op.get_bind()
    for spec in PROMPT_SPECS:
        template_id = bind.execute(
            sa.text("SELECT id FROM prompt_templates WHERE key = :key"),
            {"key": spec["key"]},
        ).scalar_one_or_none()
        if template_id is None:
            template_id = uuid4()
            bind.execute(
                sa.text("INSERT INTO prompt_templates (id, key, name, purpose) VALUES (:id, :key, :name, :purpose)"),
                {"id": template_id, "key": spec["key"], "name": spec["name"], "purpose": spec["purpose"]},
            )
        for version in spec["versions"]:
            existing = bind.execute(
                sa.text("SELECT id FROM prompt_template_versions WHERE prompt_template_id = :template_id AND version = :version"),
                {"template_id": template_id, "version": version["version"]},
            ).scalar_one_or_none()
            if existing is None:
                bind.execute(
                    sa.text("INSERT INTO prompt_template_versions (id, prompt_template_id, version, body, status) VALUES (:id, :template_id, :version, :body, :status)"),
                    {
                        "id": uuid4(),
                        "template_id": template_id,
                        "version": version["version"],
                        "body": version["body"],
                        "status": version["status"],
                    },
                )
        # Ensure one active published version per template, preserving user-created
        # versions if this migration is applied to a database with prior setup.
        published = bind.execute(
            sa.text("SELECT id FROM prompt_template_versions WHERE prompt_template_id = :template_id AND status = 'PUBLISHED' ORDER BY version DESC LIMIT 1"),
            {"template_id": template_id},
        ).scalar_one_or_none()
        if published is not None:
            bind.execute(
                sa.text("UPDATE prompt_template_versions SET status = 'ARCHIVED' WHERE prompt_template_id = :template_id AND status = 'PUBLISHED' AND id <> :published"),
                {"template_id": template_id, "published": published},
            )

    # Existing discovery jobs are historical runs of the exact default prompts
    # that were embedded in the previous adapter code. Pin those version-1 bodies
    # so a restart does not silently switch their instructions.
    legacy_snapshot = {}
    for spec in PROMPT_SPECS:
        template = bind.execute(
            sa.text("SELECT id FROM prompt_templates WHERE key = :key"),
            {"key": spec["key"]},
        ).scalar_one()
        version = bind.execute(
            sa.text("SELECT id, version, body FROM prompt_template_versions WHERE prompt_template_id = :template_id AND version = 1"),
            {"template_id": template},
        ).mappings().one()
        legacy_snapshot[spec["key"]] = {
            "key": spec["key"],
            "version_id": str(version["id"]),
            "version": version["version"],
            "body": version["body"],
        }
    bind.execute(
        sa.text("UPDATE discovery_jobs SET resolved_prompts = CAST(:snapshot AS JSONB) WHERE resolved_prompts IS NULL"),
        {"snapshot": json.dumps(legacy_snapshot, ensure_ascii=False)},
    )


def downgrade() -> None:
    op.drop_column("discovery_jobs", "resolved_prompts")
    # Prompt templates are retained deliberately: operators may have edited or
    # added versions after this migration, and downgrade must not destroy them.
