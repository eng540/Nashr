import hashlib
import hmac
import mimetypes
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlencode, urlsplit, urlunsplit
from uuid import uuid4

import httpx


class StorageConfigurationError(ValueError):
    pass


class LocalFileStorage:
    """Store uploaded source files under a configured local directory."""

    def __init__(self, root: str) -> None:
        self.root = Path(root)

    async def save(self, filename: str, content: bytes, prefix: str | None = None) -> str:
        self.root.mkdir(parents=True, exist_ok=True)
        extension = Path(filename).suffix.lower() or ".pdf"
        unique_prefix = prefix or str(uuid4())
        unique_name = f"{unique_prefix}_source{extension}"
        path = self.root / unique_name
        path.write_bytes(content)
        return str(path)


def object_storage_is_configured() -> bool:
    required = (
        "OBJECT_STORAGE_ENDPOINT_URL",
        "OBJECT_STORAGE_BUCKET",
        "OBJECT_STORAGE_ACCESS_KEY_ID",
        "OBJECT_STORAGE_SECRET_ACCESS_KEY",
        "OBJECT_STORAGE_REGION",
    )
    return all(os.getenv(name, "").strip() for name in required)


class S3CompatibleObjectStorage:
    """S3-compatible object storage with SigV4 PUT and short-lived GET URLs."""

    def __init__(
        self,
        *,
        endpoint_url: str,
        bucket: str,
        access_key_id: str,
        secret_access_key: str,
        region: str,
        url_style: str = "path",
        http_client=None,
    ) -> None:
        if url_style not in {"path", "virtual-host"}:
            raise StorageConfigurationError("OBJECT_STORAGE_URL_STYLE must be 'path' or 'virtual-host'.")
        self.endpoint_url = endpoint_url.rstrip("/")
        self.bucket = bucket
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.region = region
        self.url_style = url_style
        self.http_client = http_client

    @classmethod
    def from_env(cls, http_client=None) -> "S3CompatibleObjectStorage":
        if not object_storage_is_configured():
            raise StorageConfigurationError(
                "Durable media storage is not configured. Set OBJECT_STORAGE_ENDPOINT_URL, "
                "OBJECT_STORAGE_BUCKET, OBJECT_STORAGE_ACCESS_KEY_ID, "
                "OBJECT_STORAGE_SECRET_ACCESS_KEY, and OBJECT_STORAGE_REGION."
            )
        return cls(
            endpoint_url=os.environ["OBJECT_STORAGE_ENDPOINT_URL"],
            bucket=os.environ["OBJECT_STORAGE_BUCKET"],
            access_key_id=os.environ["OBJECT_STORAGE_ACCESS_KEY_ID"],
            secret_access_key=os.environ["OBJECT_STORAGE_SECRET_ACCESS_KEY"],
            region=os.environ["OBJECT_STORAGE_REGION"],
            url_style=os.getenv("OBJECT_STORAGE_URL_STYLE", "path").strip() or "path",
            http_client=http_client,
        )

    def _target(self, key: str) -> tuple[str, str, str]:
        endpoint = urlsplit(self.endpoint_url)
        encoded_key = quote(key.lstrip("/"), safe="/-_.~")
        if self.url_style == "path":
            canonical_uri = f"{endpoint.path.rstrip('/')}/{quote(self.bucket, safe='-_.~')}/{encoded_key}"
            host = endpoint.netloc
        else:
            host = f"{self.bucket}.{endpoint.netloc}"
            canonical_uri = f"{endpoint.path.rstrip('/')}/{encoded_key}"
        canonical_uri = canonical_uri or "/"
        url = urlunsplit((endpoint.scheme, host, canonical_uri, "", ""))
        return url, host, canonical_uri

    @staticmethod
    def _signing_key(secret: str, date_stamp: str, region: str) -> bytes:
        def sign(key: bytes, message: str) -> bytes:
            return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()
        date_key = sign(("AWS4" + secret).encode("utf-8"), date_stamp)
        region_key = sign(date_key, region)
        service_key = sign(region_key, "s3")
        return sign(service_key, "aws4_request")

    def _signature(self, canonical_request: str, amz_date: str, date_stamp: str) -> tuple[str, str]:
        scope = f"{date_stamp}/{self.region}/s3/aws4_request"
        string_to_sign = (
            f"AWS4-HMAC-SHA256\n{amz_date}\n{scope}\n"
            f"{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
        )
        signature = hmac.new(
            self._signing_key(self.secret_access_key, date_stamp, self.region),
            string_to_sign.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return signature, scope

    async def save(
        self,
        filename: str,
        content: bytes,
        prefix: str | None = None,
        mime_type: str | None = None,
    ) -> str:
        extension = Path(filename).suffix.lower() or mimetypes.guess_extension(mime_type or "") or ".bin"
        safe_prefix = re.sub(r"[^A-Za-z0-9._-]+", "-", prefix or str(uuid4())).strip("-") or str(uuid4())
        key = f"artifacts/{safe_prefix}/{uuid4()}{extension}"
        url, host, canonical_uri = self._target(key)
        now = datetime.now(timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        payload_hash = hashlib.sha256(content).hexdigest()
        headers = {
            "content-type": mime_type or mimetypes.guess_type(filename)[0] or "application/octet-stream",
            "host": host,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date,
        }
        signed_headers = "content-type;host;x-amz-content-sha256;x-amz-date"
        canonical_headers = "".join(f"{name}:{headers[name].strip()}\n" for name in signed_headers.split(";"))
        canonical_request = f"PUT\n{canonical_uri}\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}"
        signature, scope = self._signature(canonical_request, amz_date, date_stamp)
        headers["authorization"] = (
            f"AWS4-HMAC-SHA256 Credential={self.access_key_id}/{scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        if self.http_client is not None:
            response = await self.http_client.put(url, content=content, headers=headers)
        else:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.put(url, content=content, headers=headers)
        response.raise_for_status()
        return f"s3://{self.bucket}/{key}"

    async def download_url(self, storage_uri: str, expires_seconds: int = 900) -> str:
        if expires_seconds < 1 or expires_seconds > 604800:
            raise ValueError("Presigned URL expiry must be between 1 and 604800 seconds.")
        parsed = urlsplit(storage_uri)
        if parsed.scheme != "s3" or parsed.netloc != self.bucket or not parsed.path.strip("/"):
            raise ValueError("Storage URI does not belong to the configured S3 bucket.")
        key = parsed.path.lstrip("/")
        url, host, canonical_uri = self._target(key)
        now = datetime.now(timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        scope = f"{date_stamp}/{self.region}/s3/aws4_request"
        params = [
            ("X-Amz-Algorithm", "AWS4-HMAC-SHA256"),
            ("X-Amz-Credential", f"{self.access_key_id}/{scope}"),
            ("X-Amz-Date", amz_date),
            ("X-Amz-Expires", str(expires_seconds)),
            ("X-Amz-SignedHeaders", "host"),
        ]
        canonical_query = urlencode(sorted(params), quote_via=quote, safe="-_.~")
        canonical_request = f"GET\n{canonical_uri}\n{canonical_query}\nhost:{host}\n\nhost\nUNSIGNED-PAYLOAD"
        signature, _ = self._signature(canonical_request, amz_date, date_stamp)
        final_query = f"{canonical_query}&X-Amz-Signature={signature}"
        return urlunsplit((urlsplit(url).scheme, urlsplit(url).netloc, canonical_uri, final_query, ""))
