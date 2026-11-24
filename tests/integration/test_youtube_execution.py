import hashlib
from datetime import datetime, timezone, timedelta
from cryptography.fernet import Fernet
import pytest
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.database.models import ArtifactModel, PlatformCopyModel
from app.application.distribution_readiness import source_fingerprint
from app.application import youtube_execution as flow
from app.adapters.publishing.youtube import UploadProgress, YouTubeProviderError
from tests.integration.test_media_scheduling import _media_artifact

CHANNEL = "UC" + "a" * 22
CONTENT = b"synthetic video bytes, never a real upload"
SESSION = "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=private-synthetic-session"


@pytest.fixture(autouse=True)
def crypt(monkeypatch):
    monkeypatch.setenv(
        "NASHR_CONNECTION_ENCRYPTION_KEY", Fernet.generate_key().decode()
    )


async def seed():
    uid = await _media_artifact()
    async with SessionFactory() as s:
        row = await s.get(ArtifactModel, uid)
        row.kind = "VIDEO"
        row.mime_type = "video/mp4"
        s.add(
            PlatformCopyModel(
                artifact_id=uid,
                platform="youtube",
                source_fingerprint=source_fingerprint(row),
                fields={
                    "title": "عنوان صريح",
                    "description": "وصف كامل",
                    "tags": [],
                    "alt_text": "",
                },
                origin="USER_EDITED",
                version=1,
            )
        )
        await s.commit()
        job = await flow.prepare(
            s,
            uid,
            channel_id=CHANNEL,
            media_sha256=hashlib.sha256(CONTENT).hexdigest(),
            total_bytes=len(CONTENT),
            privacy="private",
            made_for_kids=False,
            contains_synthetic_media=False,
            category_id="27",
        )
        return uid, job.id


class Provider:
    channel_id = CHANNEL

    def __init__(self):
        self.calls = []

    async def initiate(self, **kw):
        self.calls.append("init")
        assert kw["privacy"] == "private"
        return SESSION

    async def upload_chunk(self, *args, **kw):
        self.calls.append("chunk")
        assert kw["chunk"] == CONTENT
        return UploadProgress("VIDEO_ID_KNOWN", len(CONTENT), "Abcdef012_-")

    async def video_status(self, video_id):
        self.calls.append("verify")
        return {
            "video_id": video_id,
            "channel_id": CHANNEL,
            "privacy": "private",
            "upload_status": "processed",
            "processing_status": "succeeded",
        }

    async def status(self, *args, **kw):
        self.calls.append("status")
        return UploadProgress("VIDEO_ID_KNOWN", len(CONTENT), "Abcdef012_-")


@pytest.mark.asyncio
async def test_durable_encrypted_session_and_one_claim():
    uid, jid = await seed()
    p = Provider()
    async with SessionFactory() as s:
        with pytest.raises(ValueError):
            await flow.initiate(s, jid, provider=p, content=CONTENT)
        job = await flow.initiate(s, jid, provider=p, content=CONTENT, authorized=True)
        assert job.state == "SESSION_READY" and "private-synthetic-session" not in str(
            vars(job)
        )
        with pytest.raises(ValueError):
            await flow.initiate(s, jid, provider=p, content=CONTENT, authorized=True)
        job = await flow.send_next(s, jid, provider=p, content=CONTENT, authorized=True)
        assert job.state == "VIDEO_ID_KNOWN" and job.received_bytes == len(CONTENT)
        with pytest.raises(ValueError):
            await flow.send_next(s, jid, provider=p, content=CONTENT, authorized=True)
        job = await flow.verify_result(s, jid, provider=p)
        assert job.state == "PROCESSED"
    assert p.calls == ["init", "chunk", "verify"]


@pytest.mark.asyncio
async def test_lost_chunk_only_reconciles_same_session_no_resend():
    uid, jid = await seed()

    class Lost(Provider):
        async def upload_chunk(self, *a, **kw):
            self.calls.append("chunk")
            raise YouTubeProviderError("YOUTUBE_OUTCOME_UNKNOWN", outcome_unknown=True)

    p = Lost()
    async with SessionFactory() as s:
        await flow.initiate(s, jid, provider=p, content=CONTENT, authorized=True)
        job = await flow.send_next(s, jid, provider=p, content=CONTENT, authorized=True)
        assert job.state == "UPLOAD_UNKNOWN"
        with pytest.raises(ValueError):
            await flow.send_next(s, jid, provider=p, content=CONTENT, authorized=True)
        job = await flow.reconcile(s, jid, provider=p)
        assert job.state == "VIDEO_ID_KNOWN"
    assert p.calls == ["init", "chunk", "status"]


@pytest.mark.asyncio
async def test_initiation_unknown_never_restarts():
    uid, jid = await seed()

    class Lost(Provider):
        async def initiate(self, **kw):
            self.calls.append("init")
            raise YouTubeProviderError("YOUTUBE_OUTCOME_UNKNOWN", outcome_unknown=True)

    p = Lost()
    async with SessionFactory() as s:
        job = await flow.initiate(s, jid, provider=p, content=CONTENT, authorized=True)
        assert job.state == "INIT_UNKNOWN" and job.session_ciphertext is None
        with pytest.raises(ValueError):
            await flow.initiate(s, jid, provider=p, content=CONTENT, authorized=True)
        with pytest.raises(ValueError):
            await flow.reconcile(s, jid, provider=p)
    assert p.calls == ["init"]


@pytest.mark.asyncio
async def test_changed_bytes_or_copy_prevent_provider_edges():
    uid, jid = await seed()
    p = Provider()
    async with SessionFactory() as s:
        with pytest.raises(ValueError):
            await flow.initiate(
                s, jid, provider=p, content=CONTENT + b"x", authorized=True
            )
        copy = await s.get(PlatformCopyModel, (uid, "youtube"))
        copy.fields = {**copy.fields, "description": "تغير دون رفع"}
        await s.commit()
        with pytest.raises(ValueError):
            await flow.initiate(s, jid, provider=p, content=CONTENT, authorized=True)
    assert not p.calls


@pytest.mark.asyncio
async def test_retry_after_expired_and_operator_claim_recovery():
    uid, jid = await seed()

    class Pending(Provider):
        async def upload_chunk(self, *a, **kw):
            self.calls.append("chunk")
            return UploadProgress("INCOMPLETE", 0, retry_after_seconds=60)

        async def status(self, *a, **kw):
            self.calls.append("status")
            return UploadProgress("SESSION_EXPIRED", 0)

    p = Pending()
    async with SessionFactory() as s:
        await flow.initiate(s, jid, provider=p, content=CONTENT, authorized=True)
        job = await flow.send_next(s, jid, provider=p, content=CONTENT, authorized=True)
        with pytest.raises(ValueError):
            await flow.send_next(s, jid, provider=p, content=CONTENT, authorized=True)
        with pytest.raises(ValueError):
            await flow.reconcile(s, jid, provider=p)
        job.retry_not_before = datetime.now(timezone.utc) - timedelta(seconds=1)
        await s.commit()
        job = await flow.reconcile(s, jid, provider=p)
        assert job.state == "SESSION_EXPIRED"
        with pytest.raises(ValueError):
            await flow.initiate(s, jid, provider=p, content=CONTENT, authorized=True)
        job.state = "SENDING"
        await s.commit()
        stamp = job.updated_at
        with pytest.raises(ValueError):
            await flow.interrupted_claim(
                s, jid, expected_state="SENDING", expected_updated_at=stamp
            )
        job = await flow.interrupted_claim(
            s,
            jid,
            expected_state="SENDING",
            expected_updated_at=stamp,
            worker_confirmed_stopped=True,
        )
        assert job.state == "UPLOAD_UNKNOWN"


@pytest.mark.asyncio
async def test_concurrent_initiation_one_provider_edge():
    import asyncio

    uid, jid = await seed()
    p = Provider()

    async def attempt():
        async with SessionFactory() as s:
            try:
                return await flow.initiate(
                    s, jid, provider=p, content=CONTENT, authorized=True
                )
            except ValueError:
                return None

    await asyncio.gather(attempt(), attempt())
    assert p.calls == ["init"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "progress",
    [
        UploadProgress("PROCESSED", 0),
        UploadProgress("VIDEO_ID_KNOWN", len(CONTENT), "invalid"),
        UploadProgress("INCOMPLETE", len(CONTENT) + 1),
        UploadProgress("INCOMPLETE", -1),
        UploadProgress("INCOMPLETE", True),
        UploadProgress("INCOMPLETE", 0, retry_after_seconds=-1),
    ],
)
async def test_bad_provider_progress_fails_closed(progress):
    uid, jid = await seed()

    class Bad(Provider):
        async def upload_chunk(self, *a, **kw):
            return progress

    p = Bad()
    async with SessionFactory() as s:
        await flow.initiate(s, jid, provider=p, content=CONTENT, authorized=True)
        job = await flow.send_next(s, jid, provider=p, content=CONTENT, authorized=True)
        assert (
            job.state == "UPLOAD_UNKNOWN"
            and job.received_bytes == 0
            and job.video_id is None
        )


@pytest.mark.asyncio
async def test_provider_delay_not_shortened_and_changed_privacy_not_processed():
    uid, jid = await seed()

    class Delay(Provider):
        async def upload_chunk(self, *a, **kw):
            raise YouTubeProviderError(
                "YOUTUBE_OUTCOME_UNKNOWN",
                outcome_unknown=True,
                retry_after_seconds=172800,
            )

    p = Delay()
    async with SessionFactory() as s:
        await flow.initiate(s, jid, provider=p, content=CONTENT, authorized=True)
        job = await flow.send_next(s, jid, provider=p, content=CONTENT, authorized=True)
        assert job.retry_not_before > datetime.now(timezone.utc) + timedelta(hours=47)
        with pytest.raises(ValueError):
            await flow.reconcile(s, jid, provider=p)
        job.retry_not_before = None
        await s.commit()
        await flow.reconcile(s, jid, provider=p)

        class Changed(Provider):
            async def video_status(self, vid):
                return {**await super().video_status(vid), "privacy": "public"}

        job = await flow.verify_result(s, jid, provider=Changed())
        assert job.state == "RESULT_CHANGED"
