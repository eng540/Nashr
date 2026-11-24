import json
import httpx
import pytest
from app.adapters.publishing.youtube import (
    YouTubeResumablePublisher as Publisher,
    YouTubeProviderError,
)

CHANNEL = "UC" + "a" * 22
VIDEO = "Abcdef012_-"
SESSION = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&upload_id=synthetic"
BODY = dict(
    title="عنوان كامل",
    description="وصف محفوظ",
    tags=["وسم واحد"],
    category_id="27",
    privacy="private",
    made_for_kids=False,
    contains_synthetic_media=False,
    total_bytes=3,
    mime_type="video/mp4",
    authorized=True,
)


@pytest.mark.asyncio
async def test_initiation_verifies_selected_channel_and_exact_explicit_metadata():
    seen = []

    async def handler(r):
        seen.append(r)
        assert r.headers["authorization"] == "Bearer synthetic-only"
        assert "synthetic-only" not in str(r.url)
        if r.method == "GET":
            return httpx.Response(
                200,
                json={"items": [{"id": CHANNEL, "snippet": {"title": "قناة اختبار"}}]},
            )
        body = json.loads(r.content)
        assert body == {
            "snippet": {
                "title": BODY["title"],
                "description": BODY["description"],
                "tags": BODY["tags"],
                "categoryId": "27",
            },
            "status": {
                "privacyStatus": "private",
                "selfDeclaredMadeForKids": False,
                "containsSyntheticMedia": False,
            },
        }
        assert (
            "publishAt" not in str(body) and r.headers["x-upload-content-length"] == "3"
        )
        return httpx.Response(200, headers={"location": SESSION})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        assert (
            await Publisher(
                client=c, token="synthetic-only", channel_id=CHANNEL
            ).initiate(**BODY)
            == SESSION
        )
    assert len(seen) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("authorized", False),
        ("privacy", None),
        ("made_for_kids", None),
        ("contains_synthetic_media", None),
        ("description", "ع" * 2501),
        ("title", "a" * 101),
        ("category_id", ""),
        ("total_bytes", True),
        ("mime_type", "video/mp4\r\nX: y"),
        ("tags", ["a b" * 200]),
    ],
)
async def test_invalid_or_unreviewed_values_fail_before_network(field, value):
    async def forbidden(r):
        raise AssertionError("Must not send")

    async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden)) as c:
        with pytest.raises(ValueError):
            await Publisher(client=c, token="synthetic", channel_id=CHANNEL).initiate(
                **{**BODY, field: value}
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "http://www.googleapis.com/upload/youtube/v3/videos?upload_id=x",
        "https://evil.invalid/upload/youtube/v3/videos?upload_id=x",
        "https://www.googleapis.com.evil.invalid/upload/youtube/v3/videos?upload_id=x",
        "https://www.googleapis.com/upload/youtube/v3/videos",
        "https://www.googleapis.com:443/upload/youtube/v3/videos?upload_id=x",
        "https://user@www.googleapis.com/upload/youtube/v3/videos?upload_id=x",
    ],
)
async def test_session_capability_never_follows_arbitrary_host(url):
    async def forbidden(r):
        raise AssertionError("Must not send")

    async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden)) as c:
        with pytest.raises(ValueError):
            await Publisher(client=c, token="synthetic", channel_id=CHANNEL).status(
                url, total_bytes=3
            )


@pytest.mark.asyncio
async def test_unknown_chunk_reconciles_existing_session_no_new_upload_or_retry():
    seen = []

    async def handler(r):
        seen.append(r)
        if r.content:
            raise httpx.ReadTimeout("secret diagnostic", request=r)
        assert r.headers["content-range"] == "bytes */3"
        return httpx.Response(
            201, json={"id": VIDEO, "snippet": {"channelId": CHANNEL}}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        p = Publisher(client=c, token="synthetic", channel_id=CHANNEL)
        with pytest.raises(YouTubeProviderError) as exc:
            await p.upload_chunk(
                SESSION,
                chunk=b"abc",
                start=0,
                total_bytes=3,
                mime_type="video/mp4",
                authorized=True,
            )
        assert exc.value.outcome_unknown and "secret" not in str(exc.value)
        result = await p.status(SESSION, total_bytes=3)
        assert result.state == "VIDEO_ID_KNOWN" and result.video_id == VIDEO
    assert len(seen) == 2 and all(r.method == "PUT" for r in seen)


@pytest.mark.asyncio
@pytest.mark.parametrize("range_value,received", [(None, 0), ("bytes=0-1", 2)])
async def test_incomplete_status_offset_and_retry_after(range_value, received):
    async def handler(r):
        return httpx.Response(
            308,
            headers={
                **({"range": range_value} if range_value else {}),
                "retry-after": "60",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        result = await Publisher(
            client=c, token="synthetic", channel_id=CHANNEL
        ).status(SESSION, total_bytes=3)
        assert result.received_bytes == received and result.retry_after_seconds == 60


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode",
    ["wrong-channel", "paging", "expired", "wrong-completion", "bad-range", "server"],
)
async def test_fail_closed_provider_states(mode):
    async def handler(r):
        if mode == "wrong-channel":
            return httpx.Response(
                200,
                json={
                    "items": [{"id": "UC" + "z" * 22, "snippet": {"title": "other"}}]
                },
            )
        if mode == "paging":
            return httpx.Response(
                200,
                json={
                    "items": [{"id": CHANNEL, "snippet": {"title": "a"}}],
                    "nextPageToken": "next",
                },
            )
        if mode == "expired":
            return httpx.Response(404)
        if mode == "wrong-completion":
            return httpx.Response(
                201, json={"id": VIDEO, "snippet": {"channelId": "UC" + "z" * 22}}
            )
        if mode == "bad-range":
            return httpx.Response(308, headers={"range": "bytes=0-9999"})
        return httpx.Response(503, json={"error": {"message": "secret"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        p = Publisher(client=c, token="synthetic", channel_id=CHANNEL)
        if mode == "expired":
            assert (await p.status(SESSION, total_bytes=3)).state == "SESSION_EXPIRED"
        else:
            with pytest.raises(YouTubeProviderError):
                if mode in {"paging", "wrong-channel"}:
                    await p.initiate(**BODY)
                else:
                    await p.status(SESSION, total_bytes=3)


@pytest.mark.asyncio
async def test_chunks_require_authority_alignment_and_do_not_send_until_valid():
    seen = []

    async def handler(r):
        seen.append(r)
        return httpx.Response(
            201, json={"id": VIDEO, "snippet": {"channelId": CHANNEL}}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        p = Publisher(client=c, token="synthetic", channel_id=CHANNEL)
        with pytest.raises(ValueError):
            await p.upload_chunk(
                SESSION, chunk=b"a", start=0, total_bytes=3, mime_type="video/mp4"
            )
        with pytest.raises(ValueError):
            await p.upload_chunk(
                SESSION,
                chunk=b"a",
                start=0,
                total_bytes=3,
                mime_type="video/mp4",
                authorized=True,
            )
        r = await p.upload_chunk(
            SESSION,
            chunk=b"abc",
            start=0,
            total_bytes=3,
            mime_type="video/mp4",
            authorized=True,
        )
        assert r.state == "VIDEO_ID_KNOWN"
    assert len(seen) == 1 and seen[0].headers["content-range"] == "bytes 0-2/3"


def test_upload_session_capability_redacted_in_http_logs():
    import logging
    from app.infrastructure.connection_logging import CredentialFilter

    r = logging.LogRecord("httpx", logging.INFO, "", 0, "PUT " + SESSION, (), None)
    CredentialFilter().filter(r)
    assert (
        "upload_id=[REDACTED]" in r.getMessage() and "synthetic" not in r.getMessage()
    )


@pytest.mark.asyncio
async def test_video_status_not_uploaded_equals_published():
    async def handler(r):
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": VIDEO,
                        "snippet": {"channelId": CHANNEL},
                        "status": {
                            "uploadStatus": "uploaded",
                            "privacyStatus": "private",
                        },
                        "processingDetails": {"processingStatus": "processing"},
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        r = await Publisher(
            client=c, token="synthetic", channel_id=CHANNEL
        ).video_status(VIDEO)
        assert (
            r["upload_status"] == "uploaded"
            and r["processing_status"] == "processing"
            and r["privacy"] == "private"
        )
        assert not r["execution_authorized"]


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [308, 503])
async def test_retry_after_date_or_long_wait_never_silently_shortened(code):
    from email.utils import format_datetime
    from datetime import datetime, timezone, timedelta

    future = format_datetime(
        datetime.now(timezone.utc) + timedelta(days=2), usegmt=True
    )

    async def handler(r):
        return httpx.Response(code, headers={"retry-after": future})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        p = Publisher(client=c, token="synthetic", channel_id=CHANNEL)
        if code == 308:
            delay = (await p.status(SESSION, total_bytes=3)).retry_after_seconds
        else:
            with pytest.raises(YouTubeProviderError) as exc:
                await p.status(SESSION, total_bytes=3)
            delay = exc.value.retry_after_seconds
        assert 172790 <= delay <= 172800
