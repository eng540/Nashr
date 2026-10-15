import pytest

from app.application.control_plane import ControlPlaneResolver
from app.domain.products import ProductionProductDefinition
from tests.integration.conftest import SessionFactory


@pytest.mark.asyncio
async def test_builtin_text_product_has_versioned_presentation_instructions() -> None:
    async with SessionFactory() as session:
        product = await ControlPlaneResolver().resolve_product(session, "ARABIC_LITERATURE_TEXT")
        assert product is not None
        definition = ProductionProductDefinition.from_dict(product.definition)
        assert product.version >= 2
        assert "سطر فارغ واحد" in definition.presentation_instructions
        assert "لا تضف عنوانًا" in definition.presentation_instructions
