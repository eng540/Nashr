"""Dormant Page text/photo edge. No live route, scheduler or retry policy.

An approved caller must pin page, exact copy and inspected bytes durably before
using a write. A failed/unknown POST is never repeated automatically.
"""

from dataclasses import dataclass
import hashlib
import re
import httpx

ID = re.compile(r"^[0-9]{1,100}$")
POST_ID = re.compile(r"^([0-9]{1,100})_([0-9]{1,100})$")


class FacebookProviderError(RuntimeError):
    def __init__(self, code, *, outcome_unknown=False):
        self.code = code
        self.outcome_unknown = outcome_unknown
        super().__init__(code)


@dataclass(frozen=True)
class FacebookResult:
    state: str
    post_id: str | None = None
    photo_id: str | None = None
    permalink: str | None = None
    observed_message: str | None = None
    observed_published: bool | None = None


class FacebookPagePublisher:
    def __init__(
        self, *, client: httpx.AsyncClient, token: str, page_id: str, version: str
    ):
        if (
            not isinstance(token, str)
            or not token
            or len(token) > 16000
            or not isinstance(page_id, str)
            or not ID.fullmatch(page_id)
            or not isinstance(version, str)
            or not re.fullmatch(r"v[0-9]{1,2}\.0", version)
        ):
            raise ValueError("Explicit Page token, Page and API version required")
        self.client = client
        self.token = token
        self.page_id = page_id
        self.base = "https://graph.facebook.com/" + version

    async def _request(self, method, path, **kwargs):
        try:
            response = await self.client.request(
                method,
                self.base + "/" + path,
                headers={"Authorization": "Bearer " + self.token},
                follow_redirects=False,
                **kwargs,
            )
        except httpx.HTTPError:
            raise FacebookProviderError(
                (
                    "FACEBOOK_OUTCOME_UNKNOWN"
                    if method == "POST"
                    else "FACEBOOK_READ_FAILED"
                ),
                outcome_unknown=method == "POST",
            ) from None
        try:
            body = response.json()
        except (ValueError, TypeError):
            raise FacebookProviderError(
                "FACEBOOK_INVALID_RESPONSE", outcome_unknown=method == "POST"
            ) from None
        if response.status_code == 401:
            raise FacebookProviderError("FACEBOOK_RECONNECT_REQUIRED")
        if response.status_code == 403:
            raise FacebookProviderError("FACEBOOK_PERMISSION_OR_LIMIT_REQUIRED")
        if (
            not 200 <= response.status_code < 300
            or not isinstance(body, dict)
            or body.get("error")
        ):
            raise FacebookProviderError(
                (
                    "FACEBOOK_OUTCOME_UNKNOWN"
                    if method == "POST"
                    else "FACEBOOK_READ_FAILED"
                ),
                outcome_unknown=method == "POST",
            )
        return body

    async def verify_page(self):
        body = await self._request("GET", "me", params={"fields": "id,name"})
        if body.get("id") != self.page_id or not isinstance(body.get("name"), str):
            raise FacebookProviderError("FACEBOOK_PAGE_MISMATCH")
        return {
            "page_id": self.page_id,
            "name": body["name"],
            "publishing_authorized": False,
            "permission_verified": False,
        }

    @staticmethod
    def validate_message(message, *, allow_empty=False):
        if (
            not isinstance(message, str)
            or (not allow_empty and not message.strip())
            or len(message) > 60000
        ):
            raise ValueError(
                "Exact message required within local preparation limit; never shortened"
            )

    def post_identity(self, value):
        match = POST_ID.fullmatch(value) if isinstance(value, str) else None
        if not match or match[1] != self.page_id:
            raise FacebookProviderError(
                "FACEBOOK_POST_ID_UNVERIFIED", outcome_unknown=True
            )
        return value

    async def publish_text(
        self, *, message, authorized=False, public_page_acknowledged=False
    ):
        if authorized is not True or public_page_acknowledged is not True:
            raise ValueError("Explicit Page publication decision required")
        self.validate_message(message)
        await self.verify_page()
        body = await self._request(
            "POST", self.page_id + "/feed", json={"message": message, "published": True}
        )
        return FacebookResult("POST_ID_KNOWN", self.post_identity(body.get("id")))

    async def publish_photo(
        self,
        *,
        message,
        content,
        mime_type,
        sha256,
        authorized=False,
        public_page_acknowledged=False,
    ):
        if authorized is not True or public_page_acknowledged is not True:
            raise ValueError(
                "Explicit Page publication and byte disclosure decision required"
            )
        self.validate_message(message, allow_empty=True)
        if (
            not isinstance(content, bytes)
            or not content
            or len(content) > 4_000_000
            or mime_type not in {"image/jpeg", "image/png"}
            or hashlib.sha256(content).hexdigest() != sha256
        ):
            raise ValueError("Pinned inspected JPEG/PNG up to4MB required")
        await self.verify_page()
        # Private bytes go directly to Meta only under a future approved write.
        # Never generate a public URL merely for preview or provider convenience.
        body = await self._request(
            "POST",
            self.page_id + "/photos",
            data={"caption": message, "published": "true"},
            files={
                "source": (
                    "photo.jpg" if mime_type == "image/jpeg" else "photo.png",
                    content,
                    mime_type,
                )
            },
        )
        photo = body.get("id")
        if not isinstance(photo, str) or not ID.fullmatch(photo):
            raise FacebookProviderError(
                "FACEBOOK_PHOTO_ID_UNVERIFIED", outcome_unknown=True
            )
        post = self.post_identity(body.get("post_id"))
        return FacebookResult("POST_ID_KNOWN", post, photo)

    async def verify_post(self, post_id, *, expected_message):
        self.validate_message(expected_message, allow_empty=True)
        self.post_identity(post_id)
        body = await self._request(
            "GET",
            post_id,
            params={"fields": "id,from,message,is_published,permalink_url"},
        )
        author = body.get("from")
        if (
            body.get("id") != post_id
            or not isinstance(author, dict)
            or author.get("id") != self.page_id
        ):
            raise FacebookProviderError("FACEBOOK_RESULT_MISMATCH")
        # Provider URLs are facts, not execution instructions. Return only valid
        # Facebook HTTPS permalinks and never invent one from a known ID.
        from urllib.parse import urlsplit

        link = body.get("permalink_url")
        try:
            parsed = urlsplit(link) if isinstance(link, str) else None
            port = parsed.port if parsed else None
        except ValueError:
            parsed = None
            port = None
        if (
            not parsed
            or parsed.scheme != "https"
            or parsed.hostname not in {"www.facebook.com", "facebook.com"}
            or parsed.username
            or parsed.password
            or port
            or parsed.fragment
        ):
            link = None
        observed = body.get("message", "")
        published = body.get("is_published") is True
        # Meta converts CRLF pairs to LF on photo captions. Preserve all other
        # characters, whitespace and bare CR; this is readback-only equivalence.
        same = isinstance(observed,str) and observed.replace("\r\n","\n") == expected_message.replace("\r\n","\n")
        state = ("RESULT_CHANGED" if not same else
                 "PUBLISHED_AT_LAST_CHECK" if published else "NOT_CONFIRMED_PUBLISHED")
        # Diagnostic data never relaxes exact comparison or author validation.
        return FacebookResult(state, post_id, permalink=link,
                              observed_message=observed if isinstance(observed,str) else None,
                              observed_published=published)
