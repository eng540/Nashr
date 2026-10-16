from app.adapters.drafting.gemini import GeminiEditorialDrafter
from app.application.provider_errors import ProviderOutcomeUnknownError
from app.domain.editorial import EditorialSourceMaterial


class FakeParsed:
    content = "**افتتاحية**\\n\\nشاهد واضح.\\n\\nالفائدة: تطبيق عملي.\\n\\n📚 الكتاب\\n#فكر"


class FakeResponse:
    parsed = FakeParsed()


class FakeModels:
    def __init__(self) -> None:
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return FakeResponse()


class FakeClient:
    def __init__(self) -> None:
        self.models = FakeModels()


def test_editorial_drafter_returns_structured_markdown() -> None:
    client = FakeClient()
    drafter = GeminiEditorialDrafter(client=client)
    result = drafter._draft_sync("فكرة", "مادة المصدر", "كتاب.pdf", system_prompt="resolved editorial instruction")
    assert result.startswith("**افتتاحية**")
    call = client.models.calls[0]
    assert call["config"].response_mime_type == "application/json"
    assert call["contents"][0] == "resolved editorial instruction"
    assert "اسم المصدر:" in call["contents"][1]
    assert "المادة المصدرية:" in call["contents"][1]


def test_editorial_drafter_attaches_visual_pdf_slice() -> None:
    client = FakeClient()
    drafter = GeminiEditorialDrafter(client=client)
    drafter._draft_sync("فكرة", "مادة المصدر", "كتاب.pdf", b"%PDF-visual-slice", "resolved editorial instruction")
    part = client.models.calls[0]["contents"][2]
    assert part.inline_data.mime_type == "application/pdf"
    assert part.inline_data.data == b"%PDF-visual-slice"


def test_multi_source_drafter_sends_each_selected_source_and_reference() -> None:
    client = FakeClient()
    drafter = GeminiEditorialDrafter(client=client)
    sources = [
        EditorialSourceMaterial("unit-1", "الصبر", "النص الأول", "كتاب أ", "ص 12"),
        EditorialSourceMaterial("unit-2", "الحلم", "النص الثاني", "كتاب ب", None),
    ]
    result = drafter._draft_sources_sync("الصبر عند العرب", sources, "تعليمات منشورة")
    assert result.startswith("**افتتاحية**")
    call = client.models.calls[0]
    assert call["contents"][0] == "تعليمات منشورة"
    prompt = call["contents"][1]
    assert "الصبر عند العرب" in prompt
    assert "unit-1" in prompt and "unit-2" in prompt
    assert "ص 12" in prompt
    assert "لا توجد إحالة صفحات محفوظة" in prompt
    assert "النص الأول" in prompt and "النص الثاني" in prompt
    assert call["context"] == {"theme": "الصبر عند العرب", "source_count": 2}


def test_multi_source_drafter_rejects_insufficient_or_duplicate_sources():
    import asyncio
    import pytest

    drafter = GeminiEditorialDrafter(client=FakeClient())
    source = EditorialSourceMaterial("unit-1", "عنوان", "نص", "كتاب", None)
    with pytest.raises(ValueError, match="at least two"):
        asyncio.run(drafter.draft_sources(theme="ثيمة", sources=[source], system_prompt="prompt"))
    with pytest.raises(ValueError, match="duplicate"):
        asyncio.run(drafter.draft_sources(theme="ثيمة", sources=[source, source], system_prompt="prompt"))


def test_editorial_drafter_timeout_uses_shared_unknown_outcome_contract(monkeypatch):
    monkeypatch.setenv("GEMINI_RETRY_MAX_ATTEMPTS", "1")

    class TimeoutModels(FakeModels):
        def generate_content(self, **kwargs):
            self.calls.append(kwargs)
            raise TimeoutError("request timed out after send")

    client = FakeClient()
    client.models = TimeoutModels()
    drafter = GeminiEditorialDrafter(client=client, model="test-editorial-model")
    try:
        drafter._draft_sync("فكرة", "مادة المصدر", "كتاب.pdf", system_prompt="resolved editorial instruction")
    except ProviderOutcomeUnknownError as exc:
        assert exc.code == "PROVIDER_OUTCOME_UNKNOWN"
    else:
        raise AssertionError("Expected an ambiguous provider outcome to be held")
