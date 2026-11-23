"""Integration coverage of the authenticated, retry-safe archive endpoint."""
import io
import zipfile
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select, func

from app.api.auth import issue_token, SESSION_COOKIE
from app.application.media_bank import IngestReadyMedia
from app.infrastructure.artifact_storage import S3ArtifactStorage
from app.infrastructure.database.models import ArtifactModel
from app.infrastructure.database.session import SessionFactory
from app.main import app
from tests.integration.test_media_bank_ingest import _FakeS3Client


def topic_zip(key):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as z:
        z.writestr(f'content/P1/{key}.md', f'---\nرقم_الموضوع: {key}\nالعنوان: Test\n---\nFull source body')
    return stream.getvalue()


@pytest.mark.asyncio
async def test_archive_auth_and_idempotency(monkeypatch):
    monkeypatch.setenv('NASHR_AUTH_PASSWORD', 'unit-test-only')
    key = 'P1-' + uuid4().hex
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url='https://test') as client:
        assert (await client.post('/api/library/import', files={'file': ('x.zip', topic_zip(key))})).status_code == 401
        client.cookies.set(SESSION_COOKIE, issue_token('admin'))
        for first in (True, False):
            r = await client.post('/api/library/import', files={'file': ('x.zip', topic_zip(key))})
            assert r.status_code == 201, r.text
            result = r.json()['collections']['topics']
            assert result['imported' if first else 'skipped'] == [key]
            assert not result['failed']
        async with SessionFactory() as session:
            rows = list((await session.execute(select(ArtifactModel).where(ArtifactModel.artifact_metadata['import_key'].astext == key))).scalars())
            assert len(rows) == 1
            assert rows[0].review_status == 'DRAFT'
            assert rows[0].content == 'Full source body'


@pytest.mark.asyncio
async def test_design_metadata_is_atomic_with_ingest(monkeypatch):
    from app.application.engineering540_import import import_designs
    from tempfile import TemporaryDirectory
    from pathlib import Path
    import csv
    storage = S3ArtifactStorage(client=_FakeS3Client(), bucket='atomic-test')
    monkeypatch.setattr(S3ArtifactStorage, 'from_environment', lambda: storage)
    key = f'batch-{uuid4().hex}/d01.webp'
    with TemporaryDirectory() as directory:
        root = Path(directory)
        file = root / 'designs' / key
        file.parent.mkdir(parents=True)
        file.write_bytes(b'RIFFxxxxWEBPvalid')
        with (root / 'designs/index.csv').open('w') as handle:
            writer = csv.DictWriter(handle, fieldnames=['الملف', 'نص النشر (تيك توك)', 'جاهزية النشر'])
            writer.writeheader()
            writer.writerow({'الملف': f'designs/{key}', 'نص النشر (تيك توك)': 'x' * 2000, 'جاهزية النشر': 'مراجعة'})
        async with SessionFactory() as session:
            result = await import_designs(session, root, None, False)
            assert result['imported'] == [key], result
            again = await import_designs(session, root, None, False)
            assert again['skipped'] == [key]
            row = (await session.execute(select(ArtifactModel).where(ArtifactModel.artifact_metadata['import_key'].astext == key))).scalar_one()
            assert row.review_status == 'DRAFT'
            assert len(row.artifact_metadata['full_caption']) == 2000
            assert row.artifact_metadata['caption_truncated'] is True
            assert row.artifact_metadata['readiness'] == 'مراجعة'
        assert len(storage.client.puts) == 1
