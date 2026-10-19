"""Seed the Arabic Literary Gems product through the existing Control Plane.

This migration deliberately reuses the published TEXT_ARTIFACT contract and the
existing generic text capability. Product-specific behavior is carried by pinned
prompt, identity, policy, and recipe components; no parallel production path is
introduced.
"""
from __future__ import annotations

import json
from typing import Sequence, Union
from uuid import UUID

from alembic import op
import sqlalchemy as sa

revision: str = "0051_seed_arabic_literary_gems"
down_revision: Union[str, Sequence[str], None] = "0050_post_visual_artifact"
branch_labels = None
depends_on = None

PROMPT_KEY = "ARABIC_LITERARY_GEMS_DRAFTER"
IDENTITY_KEY = "ARABIC_LITERARY_EDITOR"
POLICY_KEY = "ARABIC_LITERARY_EDITORIAL_POLICY"
RECIPE_KEY = "ARABIC_LITERARY_POST_V1"
PRODUCT_KEY = "ARABIC_LITERARY_GEMS"

IDENTITY_ID = "00000000-0000-0000-0000-000000001301"
IDENTITY_VERSION_ID = "00000000-0000-0000-0000-000000001302"
POLICY_ID = "00000000-0000-0000-0000-000000001303"
POLICY_VERSION_ID = "00000000-0000-0000-0000-000000001304"
RECIPE_ID = "00000000-0000-0000-0000-000000001305"
RECIPE_VERSION_ID = "00000000-0000-0000-0000-000000001306"
PRODUCT_ID = "00000000-0000-0000-0000-000000001307"
PRODUCT_VERSION_ID = "00000000-0000-0000-0000-000000001308"
PROMPT_ID = "00000000-0000-0000-0000-000000001309"
PROMPT_VERSION_ID = "00000000-0000-0000-0000-000000001310"

IDENTITY_DEFINITION = {
    "purpose": "انتقاء النصوص الأدبية العربية وتقديمها بأمانة للمصدر وبأقل تدخل تحريري لازم.",
    "audience": "محبو الأدب العربي واللغة والتراث، من المتخصصين والقراء العامين.",
    "voice": "محرر أدبي عربي دقيق، أمين للمصدر، واضح ومقتصد.",
    "tone": "رصين، فصيح، طبيعي، غير تسويقي وغير متكلف.",
    "principles": [
        "النص الأصلي مقدم على التعليق عليه.",
        "صحة النص ونسبته مقدمتان على جاذبية المنشور.",
        "الاختيار النوعي أهم من كثرة المخرجات.",
        "لا يفرض عنوان أو مقدمة أو خاتمة على كل نص.",
        "لا يحول النص الأدبي إلى موعظة أو حكمة عامة دون مقتضى.",
        "لا يختلق مصدر أو اسم كتاب أو صفحة أو نسبة أدبية.",
        "يفصل بوضوح بين كلام المؤلف والإضافة التحريرية.",
        "تحفظ خصوصية النوع الأدبي؛ فالشعر ليس نثرا والرسالة ليست حكمة مقتضبة.",
    ],
    "objectives": [
        "إنتاج مسودة عربية قابلة للمراجعة البشرية قبل الاعتماد والنشر.",
        "إظهار القيمة الأدبية الموجودة في المادة دون استبدالها بصوت النموذج.",
        "تقديم النص بصورة مناسبة للقراءة على الهاتف وتيليجرام.",
    ],
    "constraints": [
        "اعمل فقط ضمن المادة وبيانات المصدر المقدمة في المهمة.",
        "لا تدع أن تحقق خارجيا من نسبة أو مصدر لم تتح لك مادته أو وسيلته.",
        "لا تعرض ملاحظات التشغيل أو المراجعة داخل النص الموجه للقارئ.",
        "يبقى الاعتماد النهائي والنشر ضمن دورة المراجعة البشرية في Nashr.",
    ],
}

POLICY_DEFINITION = {
    "min_content_chars": 1,
    "max_content_chars": 100000,
    "required_terms": [],
    "forbidden_terms": ["http://", "https://"],
    "allow_urls": False,
}

RECIPE_STYLE_INSTRUCTIONS = (
    "أنتج نصا أدبيا عربيا من المادة المصدرية المقدمة فقط. افحص كفاية المادة وحدودها قبل الصياغة. "
    "إذا كان النص صالحا للنقل فاحفظ ألفاظه وترتيبه ولا تستكمله من الذاكرة. اختر الشكل الذي يخدم المادة: "
    "النص وحده أو عنوان قصير أو سياق محدود عند الحاجة. لا تختلق نسبة أو مصدرا أو صفحة أو بيتا. "
    "افصل الإضافة التحريرية عن النص الأصلي، وحافظ على بنية الشعر. لا تحول الأدب إلى موعظة، ولا تضع "
    "بيانات JSON أو تعليمات المحرك أو ملاحظات المراجعة داخل النص النهائي. أعد مسودة واضحة صالحة للمراجعة "
    "البشرية؛ فالاعتماد والنشر ليسا جزءا من هذه الوصفة."
)

PROMPT_BODY = """أنت تنفذ مهمة إنتاج منشور أدبي لمنتج «روائع النصوص العربية».

ستصلك من محرك Nashr مادة معرفية واحدة واسم مصدرها وعنوانها. هذه المادة وحدها هي نطاق معرفتك في المهمة؛ لا تفترض كتابا أو صفحات أو مؤلفا أو سياقا غير موجود في المدخلات، ولا تستخدم الذاكرة لتعويض نص ناقص.

المهمة:
حوّل المادة الأدبية الموثوقة إلى مسودة عربية مناسبة للقراءة على Telegram، مع المحافظة على أصالة النص، وصحة المعلومات المتاحة، وخصوصية نوعه الأدبي. الهدف ليس إعادة صياغة كل مادة ولا إضافة عاطفة أو وعظ، بل اختيار أفضل صورة للنص وفق قيمته الفعلية.

قواعد القرار:
- افحص عنوان المصدر واسم المؤلف والنص ونوعه وحدود البيانات المتاحة قبل الإنتاج.
- إذا لم تتوفر مادة أدبية فعلية أو كانت مشوهة بما يمنع النقل الموثوق، لا تسد النقص بالتخمين؛ أخرج أقل نتيجة ممكنة قابلة للمراجعة أو بيّن الحاجة إلى المراجعة.
- اختر مقطعا متماسكا ذا قيمة أدبية واضحة، ولا تدع أنك قارنت جميع نصوص المصدر ما لم تكن متاحة فعلا.
- إذا كان المخرج اقتباسا، انقل ألفاظ المادة المقدمة بأمانة. لا تستبدل الكلمات بمرادفات، ولا تحذف ما يغير المعنى، ولا تدمج مقطعين منفصلين كأنهما نص واحد، ولا تنشئ بيتا أو عبارة لإكمال النص.
- لا تنسب نصا إلى شخص بسبب شهرته أو شيوع العبارة وحدهما. لا تخترع عنوان كتاب أو صفحة أو طبعة أو واقعة أو رابطا.
- اختر الشكل الذي يناسب المادة: النص وحده إذا كان مكتفيا، أو عنوان قصير أو سياق محدود إذا كان ذلك يضيف قيمة حقيقية. لا تفرض عنوانا أو مقدمة أو خاتمة على كل نص.
- في الشعر حافظ على ترتيب الأبيات وتقسيمها وبنيتها قدر الإمكان. لا تحول الشعر إلى فقرة نثرية.
- افصل أي إضافة تحريرية عن كلام المصدر. لا تحول النص إلى موعظة أو درس لغوي أو تعليق تسويقي.
- اجعل النص صالحا لشاشة الهاتف، بفواصل أسطر تخدم القراءة ومن دون زخرفة أو رموز تعبيرية أو وسوم تقنية.
- لا تضع تعليمات النموذج أو أسماء الحقول أو بيانات JSON أو ملاحظات التشغيل داخل النص الموجه للقارئ.

يجب أن يلتزم المخرج بعقد TEXT_ARTIFACT المرتبط بالمنتج: النص النهائي هو المحتوى الأساسي، والعنوان إن توفر يوضع في البيانات الوصفية التي يدعمها المحرك. لا تنشئ بنية غير مدعومة ولا تخلط ملاحظات المراجعة بالنص. أي حاجة إلى التحقق أو شك في النسبة تبقى للمراجعة البشرية ولا تتحول إلى حقيقة داخل النص.

الاعتماد النهائي والنشر من اختصاص دورة العمل البشرية والتشغيلية في Nashr. أخرج المسودة النهائية فقط داخل الحقل content الذي يطلبه المحرك، ولا تعرض تحليلك الداخلي أو مراحل القرار."""


def _assert_reserved(bind) -> None:
    checks = [
        ("prompt_templates", "id", UUID(PROMPT_ID)),
        ("prompt_templates", "key", PROMPT_KEY),
        ("prompt_template_versions", "id", UUID(PROMPT_VERSION_ID)),
        ("editorial_identities", "id", UUID(IDENTITY_ID)),
        ("editorial_identities", "key", IDENTITY_KEY),
        ("editorial_identity_versions", "id", UUID(IDENTITY_VERSION_ID)),
        ("production_policies", "id", UUID(POLICY_ID)),
        ("production_policies", "key", POLICY_KEY),
        ("production_policy_versions", "id", UUID(POLICY_VERSION_ID)),
        ("production_recipes", "id", UUID(RECIPE_ID)),
        ("production_recipes", "key", RECIPE_KEY),
        ("production_recipe_versions", "id", UUID(RECIPE_VERSION_ID)),
        ("production_products", "id", UUID(PRODUCT_ID)),
        ("production_products", "key", PRODUCT_KEY),
        ("production_product_versions", "id", UUID(PRODUCT_VERSION_ID)),
    ]
    for table, column, value in checks:
        if bind.execute(sa.text(f"SELECT 1 FROM {table} WHERE {column} = :value LIMIT 1"), {"value": value}).scalar_one_or_none() is not None:
            raise RuntimeError(f"Cannot seed Arabic Literary Gems: reserved {table}.{column} already exists.")


def upgrade() -> None:
    bind = op.get_bind()
    _assert_reserved(bind)

    bind.execute(sa.text("""
        INSERT INTO prompt_templates (id, key, name, purpose)
        VALUES (:id, :key, :name, :purpose)
    """), {
        "id": UUID(PROMPT_ID),
        "key": PROMPT_KEY,
        "name": "موجّه روائع النصوص العربية",
        "purpose": "موجّه فعلي لإنتاج مسودة أدبية أمينة للمصدر ضمن منتج روائع النصوص العربية.",
    })
    bind.execute(sa.text("""
        INSERT INTO prompt_template_versions (id, prompt_template_id, version, body, status)
        VALUES (:id, :template_id, 1, :body, 'PUBLISHED')
    """), {"id": UUID(PROMPT_VERSION_ID), "template_id": UUID(PROMPT_ID), "body": PROMPT_BODY})

    bind.execute(sa.text("""
        INSERT INTO editorial_identities (id, key, name, purpose)
        VALUES (:id, :key, :name, :purpose)
    """), {
        "id": UUID(IDENTITY_ID), "key": IDENTITY_KEY,
        "name": "المحرر الأدبي العربي", "purpose": IDENTITY_DEFINITION["purpose"],
    })
    bind.execute(sa.text("""
        INSERT INTO editorial_identity_versions (id, identity_id, version, definition, status)
        VALUES (:id, :identity_id, 1, CAST(:definition AS JSONB), 'PUBLISHED')
    """), {
        "id": UUID(IDENTITY_VERSION_ID), "identity_id": UUID(IDENTITY_ID),
        "definition": json.dumps(IDENTITY_DEFINITION, ensure_ascii=False),
    })

    bind.execute(sa.text("""
        INSERT INTO production_policies (id, key, name, purpose)
        VALUES (:id, :key, :name, :purpose)
    """), {
        "id": UUID(POLICY_ID), "key": POLICY_KEY,
        "name": "سياسة روائع النصوص العربية",
        "purpose": "ضبط سلامة مخرجات المنتج ومنع الروابط وترك الاعتماد والنشر للمراجعة البشرية.",
    })
    bind.execute(sa.text("""
        INSERT INTO production_policy_versions (id, policy_id, version, definition, status)
        VALUES (:id, :policy_id, 1, CAST(:definition AS JSONB), 'PUBLISHED')
    """), {
        "id": UUID(POLICY_VERSION_ID), "policy_id": UUID(POLICY_ID),
        "definition": json.dumps(POLICY_DEFINITION, ensure_ascii=False),
    })

    contract = bind.execute(sa.text("""
        SELECT c.key, cv.id AS version_id, cv.version
        FROM output_contracts c
        JOIN output_contract_versions cv ON cv.contract_id = c.id
        WHERE c.key = 'TEXT_ARTIFACT' AND cv.status = 'PUBLISHED'
        ORDER BY cv.version DESC LIMIT 1
    """)).mappings().one_or_none()
    if contract is None:
        raise RuntimeError("Cannot seed Arabic Literary Gems: published TEXT_ARTIFACT contract is missing.")

    recipe_definition = {"stages": [{
        "key": "produce-literary-text-artifact",
        "capability_key": "produce_text_artifact",
        "capability_version": 1,
        "configuration": {"style_instructions": RECIPE_STYLE_INSTRUCTIONS},
    }]}
    bind.execute(sa.text("""
        INSERT INTO production_recipes (id, key, name, purpose)
        VALUES (:id, :key, :name, :purpose)
    """), {
        "id": UUID(RECIPE_ID), "key": RECIPE_KEY,
        "name": "إنتاج منشور أدبي من مادة معرفية",
        "purpose": "إنتاج TEXT_ARTIFACT أدبي قابل للمراجعة من KnowledgeUnit باستخدام المكونات المثبتة للمنتج.",
    })
    bind.execute(sa.text("""
        INSERT INTO production_recipe_versions (id, recipe_id, version, definition, status)
        VALUES (:id, :recipe_id, 1, CAST(:definition AS JSONB), 'PUBLISHED')
    """), {
        "id": UUID(RECIPE_VERSION_ID), "recipe_id": UUID(RECIPE_ID),
        "definition": json.dumps(recipe_definition, ensure_ascii=False),
    })

    product_definition = {
        "recipe_key": RECIPE_KEY,
        "output_contract_key": contract["key"],
        "policy_key": POLICY_KEY,
        "audience": "محبو الأدب العربي واللغة والتراث",
        "experience": "مسودة أدبية عربية أمينة للمصدر، جاهزة للمراجعة البشرية قبل الاعتماد والنشر على Telegram",
        "prompt_key": PROMPT_KEY,
        "identity_key": IDENTITY_KEY,
        "component_versions": {
            "prompt": {"key": PROMPT_KEY, "version_id": PROMPT_VERSION_ID, "version": 1},
            "identity": {"key": IDENTITY_KEY, "version_id": IDENTITY_VERSION_ID, "version": 1},
            "recipe": {"key": RECIPE_KEY, "version_id": RECIPE_VERSION_ID, "version": 1},
            "policy": {"key": POLICY_KEY, "version_id": POLICY_VERSION_ID, "version": 1},
            "output_contract": {"key": contract["key"], "version_id": str(contract["version_id"]), "version": contract["version"]},
        },
    }
    bind.execute(sa.text("""
        INSERT INTO production_products (id, key, name, purpose)
        VALUES (:id, :key, :name, :purpose)
    """), {
        "id": UUID(PRODUCT_ID), "key": PRODUCT_KEY,
        "name": "روائع النصوص العربية",
        "purpose": "تحويل مادة أدبية موثقة إلى منشور عربي مختار بعناية مع الحفاظ على الأصل وإتاحته للمراجعة البشرية.",
    })
    bind.execute(sa.text("""
        INSERT INTO production_product_versions (id, product_id, version, definition, status)
        VALUES (:id, :product_id, 1, CAST(:definition AS JSONB), 'PUBLISHED')
    """), {
        "id": UUID(PRODUCT_VERSION_ID), "product_id": UUID(PRODUCT_ID),
        "definition": json.dumps(product_definition, ensure_ascii=False),
    })


def downgrade() -> None:
    bind = op.get_bind()
    for table, expression, identifier in (
        ("production_jobs", "resolved_context->'product'->>'version_id'", PRODUCT_VERSION_ID),
        ("production_jobs", "resolved_context->'recipe'->>'version_id'", RECIPE_VERSION_ID),
        ("artifacts", "resolved_context->'product'->>'version_id'", PRODUCT_VERSION_ID),
        ("artifacts", "resolved_context->'recipe'->>'version_id'", RECIPE_VERSION_ID),
    ):
        if bind.execute(sa.text(f"SELECT 1 FROM {table} WHERE {expression} = :id LIMIT 1"), {"id": identifier}).scalar_one_or_none() is not None:
            raise RuntimeError("Cannot downgrade Arabic Literary Gems: a job or Artifact references its pinned product or recipe.")
    bind.execute(sa.text("DELETE FROM production_product_versions WHERE id = :id"), {"id": UUID(PRODUCT_VERSION_ID)})
    bind.execute(sa.text("DELETE FROM production_products WHERE id = :id"), {"id": UUID(PRODUCT_ID)})
    bind.execute(sa.text("DELETE FROM production_recipe_versions WHERE id = :id"), {"id": UUID(RECIPE_VERSION_ID)})
    bind.execute(sa.text("DELETE FROM production_recipes WHERE id = :id"), {"id": UUID(RECIPE_ID)})
    bind.execute(sa.text("DELETE FROM production_policy_versions WHERE id = :id"), {"id": UUID(POLICY_VERSION_ID)})
    bind.execute(sa.text("DELETE FROM production_policies WHERE id = :id"), {"id": UUID(POLICY_ID)})
    bind.execute(sa.text("DELETE FROM editorial_identity_versions WHERE id = :id"), {"id": UUID(IDENTITY_VERSION_ID)})
    bind.execute(sa.text("DELETE FROM editorial_identities WHERE id = :id"), {"id": UUID(IDENTITY_ID)})
    bind.execute(sa.text("DELETE FROM prompt_template_versions WHERE id = :id"), {"id": UUID(PROMPT_VERSION_ID)})
    bind.execute(sa.text("DELETE FROM prompt_templates WHERE id = :id"), {"id": UUID(PROMPT_ID)})
