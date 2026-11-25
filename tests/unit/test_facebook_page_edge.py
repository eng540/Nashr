import json, hashlib
import httpx, pytest
from app.adapters.publishing.facebook import (
    FacebookPagePublisher as Page,
    FacebookProviderError,
)

PAGE = "12345"
POST = PAGE + "_99887"


def publisher(client):
    return Page(client=client, token="synthetic-only", page_id=PAGE, version="v27.0")


@pytest.mark.asyncio
async def test_exact_text_and_explicit_public_decision_no_retry():
    seen = []
    message = "نص كامل\nدون قص أو تغيير"

    async def handler(r):
        seen.append(r)
        assert r.headers["authorization"] == "Bearer synthetic-only"
        assert "synthetic-only" not in str(r.url)
        if r.method == "GET":
            return httpx.Response(200, json={"id": PAGE, "name": "صفحة اصطناعية"})
        assert json.loads(r.content) == {"message": message, "published": True}
        return httpx.Response(200, json={"id": POST})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        p = publisher(c)
        for authority, audience in [(False, False), (True, False), (False, True)]:
            with pytest.raises(ValueError):
                await p.publish_text(
                    message=message,
                    authorized=authority,
                    public_page_acknowledged=audience,
                )
        assert not seen
        result = await p.publish_text(
            message=message, authorized=True, public_page_acknowledged=True
        )
        assert result.state == "POST_ID_KNOWN" and result.post_id == POST
    assert [r.method for r in seen] == ["GET", "POST"]


@pytest.mark.asyncio
async def test_private_photo_bytes_multipart_never_public_url():
    content = b"synthetic-only-not-real-photo"
    digest = hashlib.sha256(content).hexdigest()
    seen = []

    async def handler(r):
        seen.append(r)
        if r.method == "GET":
            return httpx.Response(200, json={"id": PAGE, "name": "selected"})
        assert "multipart/form-data" in r.headers["content-type"]
        assert (
            content in r.content
            and b'name="source"' in r.content
            and b'name="url"' not in r.content
        )
        assert b'name="published"\r\n\r\ntrue' in r.content
        return httpx.Response(200, json={"id": "111", "post_id": POST})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        p = publisher(c)
        with pytest.raises(ValueError):
            await p.publish_photo(
                message="",
                content=content,
                mime_type="image/png",
                sha256="0" * 64,
                authorized=True,
                public_page_acknowledged=True,
            )
        assert not seen
        r = await p.publish_photo(
            message="الصورة دون تغيير",
            content=content,
            mime_type="image/png",
            sha256=digest,
            authorized=True,
            public_page_acknowledged=True,
        )
        assert r.photo_id == "111" and r.post_id == POST
    assert len(seen) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode", ["timeout", "bad-json", "server", "wrong-post", "redirect", "wrong-page"]
)
async def test_unknown_or_mismatched_result_never_assumes_retry(mode):
    calls = []

    async def handler(r):
        calls.append(r)
        if r.method == "GET":
            return httpx.Response(
                200,
                json={"id": "999" if mode == "wrong-page" else PAGE, "name": "name"},
            )
        if mode == "timeout":
            raise httpx.ReadTimeout("private diagnostics", request=r)
        if mode == "bad-json":
            return httpx.Response(200, text="not-json-private")
        if mode == "server":
            return httpx.Response(503, json={"error": {"message": "private"}})
        if mode == "redirect":
            return httpx.Response(302, headers={"location": "https://evil.invalid/"})
        return httpx.Response(200, json={"id": "999_11"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        with pytest.raises(FacebookProviderError) as exc:
            await publisher(c).publish_text(
                message="نص", authorized=True, public_page_acknowledged=True
            )
        assert "private" not in str(exc.value)
    assert len(calls) == (1 if mode == "wrong-page" else 2)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change,state",
    [
        ({}, "PUBLISHED_AT_LAST_CHECK"),
        ({"message": "changed"}, "RESULT_CHANGED"),
        ({"is_published": False}, "NOT_CONFIRMED_PUBLISHED"),
    ],
)
async def test_known_id_readback_checks_page_text_and_published(change, state):
    async def handler(r):
        assert r.method == "GET" and r.url.path.endswith("/" + POST)
        return httpx.Response(
            200,
            json={
                **{
                    "id": POST,
                    "from": {"id": PAGE},
                    "message": "النص",
                    "is_published": True,
                    "permalink_url": "https://www.facebook.com/permalink.php?story_fbid=99887&id=12345",
                },
                **change,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        result = await publisher(c).verify_post(POST, expected_message="النص")
        assert result.state == state
        if state == "PUBLISHED_AT_LAST_CHECK":
            assert result.permalink is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "https://evil.invalid/a",
        "https://facebook.com.evil.invalid/a",
        "javascript:alert(1)",
        "https://user@facebook.com/a",
        "https://facebook.com:bad/a",
    ],
)
async def test_invalid_provider_permalink_not_forwarded(url):
    async def handler(r):
        return httpx.Response(
            200,
            json={
                "id": POST,
                "from": {"id": PAGE},
                "message": "",
                "is_published": True,
                "permalink_url": url,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        result = await publisher(c).verify_post(POST, expected_message="")
        assert result.permalink is None

@pytest.mark.asyncio
async def test_readback_diagnostic_keeps_newline_mismatch_and_safe_link():
    async def handler(r):
        assert r.method == 'GET'
        return httpx.Response(200,json={'id':POST,'from':{'id':PAGE},
            'message':'first\n\nsecond','is_published':True,
            'permalink_url':'https://www.facebook.com/permalink.php?story_fbid=99887&id=12345'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        result=await publisher(c).verify_post(POST,expected_message='first\r\n\r\nsecond')
    assert result.state=='RESULT_CHANGED'
    assert result.observed_message=='first\n\nsecond'
    assert result.observed_published is True
    assert result.permalink is not None
