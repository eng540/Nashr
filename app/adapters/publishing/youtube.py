"""Resumable upload edge, dormant until owner-approved production wiring.

No routes, credentials, scheduler, automatic retries or default audience. Session
URLs are capabilities and must be encrypted by a future durable orchestrator.
"""

from dataclasses import dataclass
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import math
from urllib.parse import urlsplit, parse_qs
import httpx

API = "https://www.googleapis.com/youtube/v3"
UPLOAD = "https://www.googleapis.com/upload/youtube/v3/videos"
CHANNEL = re.compile(r"^UC[A-Za-z0-9_-]{22}$")
VIDEO = re.compile(r"^[A-Za-z0-9_-]{11}$")


class YouTubeProviderError(RuntimeError):
    def __init__(self, code, *, outcome_unknown=False, retry_after_seconds=None):
        self.code = code
        self.outcome_unknown = outcome_unknown
        self.retry_after_seconds = retry_after_seconds
        super().__init__(code)


@dataclass(frozen=True)
class UploadProgress:
    state: str
    received_bytes: int
    video_id: str | None = None
    retry_after_seconds: int | None = None


class YouTubeResumablePublisher:
    def __init__(self, *, client: httpx.AsyncClient, token: str, channel_id: str):
        if (
            not isinstance(token, str)
            or not token
            or len(token) > 16000
            or not CHANNEL.fullmatch(channel_id)
        ):
            raise ValueError("Invalid YouTube identity")
        self.client = client
        self.token = token
        self.channel_id = channel_id

    async def _request(self, method, url, **kwargs):
        try:
            return await self.client.request(
                method,
                url,
                headers={
                    "Authorization": "Bearer " + self.token,
                    **kwargs.pop("headers", {}),
                },
                follow_redirects=False,
                **kwargs,
            )
        except httpx.HTTPError:
            raise YouTubeProviderError(
                "YOUTUBE_OUTCOME_UNKNOWN" if method != "GET" else "YOUTUBE_READ_FAILED",
                outcome_unknown=method != "GET",
            ) from None

    @staticmethod
    def retry_delay(response):
        value = response.headers.get("retry-after")
        if not value:
            return None
        if value.isdigit() and len(value) <= 9:
            return int(value)
        try:
            stamp = parsedate_to_datetime(value)
            if stamp.tzinfo is None:
                return None
            return max(
                0, math.ceil((stamp - datetime.now(timezone.utc)).total_seconds())
            )
        except (ValueError, TypeError, OverflowError):
            return None

    @staticmethod
    def _json(response, *, mutation=False):
        if response.status_code == 401:
            raise YouTubeProviderError("YOUTUBE_RECONNECT_REQUIRED")
        if response.status_code == 403:
            raise YouTubeProviderError("YOUTUBE_PERMISSION_OR_QUOTA_REQUIRED")
        if response.status_code < 200 or response.status_code >= 300:
            raise YouTubeProviderError(
                (
                    "YOUTUBE_OUTCOME_UNKNOWN"
                    if mutation and response.status_code >= 500
                    else "YOUTUBE_REQUEST_REJECTED"
                ),
                outcome_unknown=mutation and response.status_code >= 500,
                retry_after_seconds=YouTubeResumablePublisher.retry_delay(response),
            )
        try:
            body = response.json()
        except (ValueError, TypeError):
            raise YouTubeProviderError(
                "YOUTUBE_INVALID_RESPONSE", outcome_unknown=mutation
            ) from None
        if not isinstance(body, dict) or body.get("error"):
            raise YouTubeProviderError(
                "YOUTUBE_INVALID_RESPONSE", outcome_unknown=mutation
            )
        return body

    async def verify_channel(self):
        body = self._json(
            await self._request(
                "GET",
                API + "/channels",
                params={"part": "id,snippet", "mine": "true", "maxResults": 50},
            )
        )
        rows = body.get("items")
        if not isinstance(rows, list) or len(rows) > 50 or body.get("nextPageToken"):
            raise YouTubeProviderError("YOUTUBE_CHANNEL_CHECK_INCOMPLETE")
        matched = [
            x for x in rows if isinstance(x, dict) and x.get("id") == self.channel_id
        ]
        if len(matched) != 1:
            raise YouTubeProviderError("YOUTUBE_CHANNEL_MISMATCH")
        title = matched[0].get("snippet", {}).get("title")
        if not isinstance(title, str):
            raise YouTubeProviderError("YOUTUBE_INVALID_RESPONSE")
        return {
            "channel_id": self.channel_id,
            "title": title,
            "execution_authorized": False,
        }

    @staticmethod
    def validate_session(uri):
        if not isinstance(uri, str):
            raise ValueError("Invalid resumable session")
        u = urlsplit(uri)
        if (
            u.scheme != "https"
            or u.netloc != "www.googleapis.com"
            or u.path != "/upload/youtube/v3/videos"
            or u.username
            or u.password
            or u.fragment
            or not parse_qs(u.query).get("upload_id")
        ):
            raise ValueError("Invalid resumable session")
        return uri

    async def initiate(
        self,
        *,
        title,
        description,
        tags,
        category_id,
        privacy,
        made_for_kids,
        contains_synthetic_media,
        total_bytes,
        mime_type,
        authorized=False,
    ):
        if authorized is not True:
            raise ValueError("Explicit upload authority required")
        if (
            not isinstance(title, str)
            or not title.strip()
            or len(title) > 100
            or any(x in title for x in "<>")
        ):
            raise ValueError("Invalid title; not shortened")
        if (
            not isinstance(description, str)
            or len(description.encode("utf-8")) > 5000
            or any(x in description for x in "<>")
        ):
            raise ValueError("Invalid description; not shortened")
        if not isinstance(tags, list) or not all(
            isinstance(x, str) and x and not any(c in x for c in "<>") for x in tags
        ):
            raise ValueError("Invalid tags")
        if (
            sum(len(x) + (2 if " " in x else 0) for x in tags) + max(0, len(tags) - 1)
            > 500
        ):
            raise ValueError("Tag limit exceeded")
        if not isinstance(category_id, str) or not re.fullmatch(
            r"[0-9]{1,10}", category_id
        ):
            raise ValueError("Explicit category required")
        if (
            privacy not in {"private", "unlisted", "public"}
            or not isinstance(made_for_kids, bool)
            or not isinstance(contains_synthetic_media, bool)
        ):
            raise ValueError("Explicit privacy and audience declarations required")
        if (
            isinstance(total_bytes, bool)
            or not isinstance(total_bytes, int)
            or not 0 < total_bytes <= 256 * 1024**3
            or not isinstance(mime_type, str)
            or not re.fullmatch(r"video/[a-zA-Z0-9.+-]+", mime_type)
        ):
            raise ValueError("Invalid upload size or type")
        await self.verify_channel()
        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": category_id,
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": made_for_kids,
                "containsSyntheticMedia": contains_synthetic_media,
            },
        }
        response = await self._request(
            "POST",
            UPLOAD,
            params={"uploadType": "resumable", "part": "snippet,status"},
            json=body,
            headers={
                "X-Upload-Content-Length": str(total_bytes),
                "X-Upload-Content-Type": mime_type,
            },
        )
        if response.status_code not in {200, 201}:
            self._json(response, mutation=True)
            raise YouTubeProviderError("YOUTUBE_INVALID_RESPONSE", outcome_unknown=True)
        try:
            return self.validate_session(response.headers.get("location"))
        except ValueError:
            raise YouTubeProviderError(
                "YOUTUBE_SESSION_UNKNOWN", outcome_unknown=True
            ) from None

    @staticmethod
    def _progress(response, total_bytes, channel_id):
        delay = YouTubeResumablePublisher.retry_delay(response)
        if response.status_code == 308:
            value = response.headers.get("range")
            if not value:
                return UploadProgress("INCOMPLETE", 0, retry_after_seconds=delay)
            match = re.fullmatch(r"bytes=0-([0-9]+)", value)
            if not match:
                raise YouTubeProviderError("YOUTUBE_INVALID_RANGE")
            received = int(match[1]) + 1
            if received > total_bytes:
                raise YouTubeProviderError("YOUTUBE_INVALID_RANGE")
            return UploadProgress("INCOMPLETE", received, retry_after_seconds=delay)
        if response.status_code in {404, 410}:
            return UploadProgress("SESSION_EXPIRED", 0)
        body = YouTubeResumablePublisher._json(response, mutation=True)
        vid = body.get("id")
        snippet = body.get("snippet")
        if (
            not isinstance(vid, str)
            or not VIDEO.fullmatch(vid)
            or not isinstance(snippet, dict)
            or snippet.get("channelId") != channel_id
        ):
            raise YouTubeProviderError(
                "YOUTUBE_COMPLETION_UNVERIFIED", outcome_unknown=True
            )
        return UploadProgress("VIDEO_ID_KNOWN", total_bytes, vid)

    async def status(self, session_uri, *, total_bytes):
        if (
            isinstance(total_bytes, bool)
            or not isinstance(total_bytes, int)
            or total_bytes <= 0
        ):
            raise ValueError("Invalid upload size")
        response = await self._request(
            "PUT",
            self.validate_session(session_uri),
            content=b"",
            headers={
                "Content-Length": "0",
                "Content-Range": "bytes */" + str(total_bytes),
            },
        )
        return self._progress(response, total_bytes, self.channel_id)

    async def upload_chunk(
        self, session_uri, *, chunk, start, total_bytes, mime_type, authorized=False
    ):
        if authorized is not True:
            raise ValueError("Explicit upload authority required")
        if (
            not isinstance(chunk, bytes)
            or not chunk
            or isinstance(start, bool)
            or not isinstance(start, int)
            or start < 0
            or isinstance(total_bytes, bool)
            or not isinstance(total_bytes, int)
            or start + len(chunk) > total_bytes
        ):
            raise ValueError("Invalid chunk range")
        if not isinstance(mime_type, str) or not re.fullmatch(
            r"video/[a-zA-Z0-9.+-]+", mime_type
        ):
            raise ValueError("Invalid MIME type")
        if start + len(chunk) < total_bytes and len(chunk) % (256 * 1024):
            raise ValueError("Non-final chunk must be a multiple of256KiB")
        # Caller must persist the exact session, byte digest and confirmed offset.
        # Never assume an interrupted chunk was rejected and send it again.
        response = await self._request(
            "PUT",
            self.validate_session(session_uri),
            content=chunk,
            headers={
                "Content-Length": str(len(chunk)),
                "Content-Type": mime_type,
                "Content-Range": f"bytes {start}-{start+len(chunk)-1}/{total_bytes}",
            },
        )
        return self._progress(response, total_bytes, self.channel_id)

    async def video_status(self, video_id):
        if not isinstance(video_id, str) or not VIDEO.fullmatch(video_id):
            raise ValueError("Invalid video identity")
        body = self._json(
            await self._request(
                "GET",
                API + "/videos",
                params={"id": video_id, "part": "snippet,status,processingDetails"},
            )
        )
        items = body.get("items")
        if (
            not isinstance(items, list)
            or len(items) != 1
            or items[0].get("id") != video_id
            or items[0].get("snippet", {}).get("channelId") != self.channel_id
        ):
            raise YouTubeProviderError("YOUTUBE_COMPLETION_UNVERIFIED")
        status = items[0].get("status", {})
        processing = items[0].get("processingDetails", {})
        return {
            "video_id": video_id,
            "channel_id": self.channel_id,
            "upload_status": status.get("uploadStatus"),
            "privacy": status.get("privacyStatus"),
            "processing_status": processing.get("processingStatus"),
            "execution_authorized": False,
        }
