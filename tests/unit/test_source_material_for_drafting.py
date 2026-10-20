from app.application.posts import _source_material_for_drafting


def test_original_text_is_sent_as_source_and_extracted_content_as_context() -> None:
    original_text = "قال الشاعر: اصبر على الدهر إن الدهر ذو غير"
    extracted_content = "خلاصة المادة: تحث على الصبر أمام تقلبات الزمن."

    result = _source_material_for_drafting(original_text, extracted_content, "صفحة 27")

    assert f"النص الأصلي المحفوظ من المصدر:\n{original_text}" in result
    assert f"وصف المادة المستخرج للسياق فقط، وليس اقتباسًا حرفيًا:\n{extracted_content}" in result
    assert "إحالة المادة المحفوظة: صفحة 27" in result


def test_content_is_preserved_when_original_text_is_unavailable() -> None:
    extracted_content = "المادة المحفوظة كاملة عند غياب الحقل الأصلي."

    result = _source_material_for_drafting(None, extracted_content, None)

    assert result == f"المادة النصية المحفوظة:\n{extracted_content}"


def test_identical_original_and_extracted_text_is_not_duplicated() -> None:
    text = "النص كما ورد في المادة."

    result = _source_material_for_drafting(text, text, "ص 5")

    assert result.count(text) == 1
    assert "وصف المادة المستخرج" not in result
    assert "إحالة المادة المحفوظة: ص 5" in result
