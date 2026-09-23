from pathlib import Path
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from app.infrastructure.database.models import SourceModel
from app.infrastructure.database.session import SessionFactory, engine
from app.main import app

@pytest.mark.integration
async def test_upload_real_pdf_is_stored_and_registered() -> None:
    """Verify a real PDF upload is stored and registered as STORED."""
    pdf = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/sources", files={"file": ("real.pdf", pdf, "application/pdf")})
    assert response.status_code == 200
    source_id = response.json()["id"]
    async with SessionFactory() as session:
        result = await session.execute(select(SourceModel).where(SourceModel.id == source_id))
        source = result.scalar_one()
        assert source.status == "STORED"
        assert Path(source.storage_path).read_bytes() == pdf
    await engine.dispose()
