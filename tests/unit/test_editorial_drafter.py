from app.adapters.drafting.gemini import GeminiEditorialDrafter


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

    result = drafter._draft_sync("فكرة", "مادة المصدر", "كتاب.pdf")

    assert result.startswith("**افتتاحية**")
    call = client.models.calls[0]
    assert call["config"]["response_mime_type"] == "application/json"
    assert "الفهارس" in call["contents"][0]
    assert "المراجع" in call["contents"][0]
    assert "مقدمات التحقيق" in call["contents"][0]
