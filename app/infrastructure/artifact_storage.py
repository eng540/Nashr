"""Durable, private S3-compatible storage for generic media Artifacts."""
import asyncio
import os
import re
from urllib.parse import unquote, urlsplit

import boto3
from botocore.config import Config


class ArtifactStorageConfigurationError(RuntimeError):
    """Required object-storage configuration is missing or invalid."""


class ArtifactStorageError(RuntimeError):
    """An object-storage operation failed without exposing provider details."""


_MIME_TYPE = re.compile(r"^[A-Za-z0-9._+-]+/[A-Za-z0-9._+-]+$")


def _validate_key(key: str) -> str:
    if (
        not isinstance(key, str)
        or not key.startswith("artifacts/")
        or len(key) > 900
        or re.fullmatch(r"[A-Za-z0-9._/-]+", key) is None
    ):
        raise ValueError("Artifact object key must be a bounded ASCII key under artifacts/.")
    if key.startswith("/") or "\\" in key or any(part in {"", ".", ".."} for part in key.split("/")):
        raise ValueError("Artifact object key contains an unsafe path segment.")
    return key


class S3ArtifactStorage:
    """Store private media objects and issue short-lived signed read URLs.

    The adapter works with S3-compatible providers (including Railway Object
    Storage) and never makes generated media public by default.
    """

    def __init__(self, *, client, bucket: str) -> None:
        if not isinstance(bucket, str) or not bucket.strip():
            raise ArtifactStorageConfigurationError("Artifact storage bucket is required.")
        self.client = client
        self.bucket = bucket.strip()

    @classmethod
    def from_environment(cls) -> "S3ArtifactStorage":
        required = {
            "ARTIFACT_STORAGE_ENDPOINT_URL": os.getenv("ARTIFACT_STORAGE_ENDPOINT_URL"),
            "ARTIFACT_STORAGE_BUCKET": os.getenv("ARTIFACT_STORAGE_BUCKET"),
            "ARTIFACT_STORAGE_ACCESS_KEY_ID": os.getenv("ARTIFACT_STORAGE_ACCESS_KEY_ID"),
            "ARTIFACT_STORAGE_SECRET_ACCESS_KEY": os.getenv("ARTIFACT_STORAGE_SECRET_ACCESS_KEY"),
        }
        missing = [name for name, value in required.items() if not value or not value.strip()]
        if missing:
            raise ArtifactStorageConfigurationError(
                "Artifact media storage is not configured; missing: " + ", ".join(missing)
            )
        region = os.getenv("ARTIFACT_STORAGE_REGION", "us-east-1").strip()
        configured_url_style = os.getenv("ARTIFACT_STORAGE_URL_STYLE", "path").strip()
        url_style = {"path": "path", "virtual": "virtual", "virtual-host": "virtual"}.get(configured_url_style)
        if url_style is None:
            raise ArtifactStorageConfigurationError(
                "ARTIFACT_STORAGE_URL_STYLE must be 'path' or 'virtual-host'."
            )
        client = boto3.client(
            "s3",
            endpoint_url=required["ARTIFACT_STORAGE_ENDPOINT_URL"],
            region_name=region,
            aws_access_key_id=required["ARTIFACT_STORAGE_ACCESS_KEY_ID"],
            aws_secret_access_key=required["ARTIFACT_STORAGE_SECRET_ACCESS_KEY"],
            config=Config(s3={"addressing_style": url_style}),
        )
        return cls(client=client, bucket=required["ARTIFACT_STORAGE_BUCKET"])


    async def ensure_available(self) -> None:
        """Verify the configured bucket and credentials before activating media products."""
        try:
            await asyncio.to_thread(self.client.head_bucket, Bucket=self.bucket)
        except Exception as exc:
            raise ArtifactStorageError("Configured Artifact media storage is not reachable.") from exc

    async def put(self, *, key: str, content: bytes, content_type: str) -> str:
        safe_key = _validate_key(key)
        if not isinstance(content, bytes) or not content:
            raise ValueError("Artifact media content must be non-empty bytes.")
        if not isinstance(content_type, str) or _MIME_TYPE.fullmatch(content_type) is None:
            raise ValueError("Artifact media content type is invalid.")
        try:
            await asyncio.to_thread(
                self.client.put_object,
                Bucket=self.bucket,
                Key=safe_key,
                Body=content,
                ContentType=content_type,
            )
        except Exception as exc:
            raise ArtifactStorageError("Unable to store Artifact media.") from exc
        return f"s3://{self.bucket}/{safe_key}"

    async def presign_get(self, storage_uri: str, *, expires_seconds: int = 300) -> str:
        bucket, key = self._parse_uri(storage_uri)
        if bucket != self.bucket:
            raise ValueError("Artifact storage URI points to an unexpected bucket.")
        if isinstance(expires_seconds, bool) or not isinstance(expires_seconds, int) or not 60 <= expires_seconds <= 900:
            raise ValueError("Signed media URL expiry must be between 60 and 900 seconds.")
        try:
            return await asyncio.to_thread(
                self.client.generate_presigned_url,
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=expires_seconds,
            )
        except Exception as exc:
            raise ArtifactStorageError("Unable to create an Artifact media URL.") from exc


    async def delete(self, storage_uri: str) -> None:
        bucket, key = self._parse_uri(storage_uri)
        if bucket != self.bucket:
            raise ValueError("Artifact storage URI points to an unexpected bucket.")
        try:
            await asyncio.to_thread(
                self.client.delete_object,
                Bucket=self.bucket,
                Key=key,
            )
        except Exception as exc:
            raise ArtifactStorageError("Unable to delete an Artifact media object.") from exc

    @staticmethod
    def _parse_uri(storage_uri: str) -> tuple[str, str]:
        if not isinstance(storage_uri, str):
            raise ValueError("Artifact storage URI must be a string.")
        parsed = urlsplit(storage_uri)
        if parsed.scheme != "s3" or not parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError("Artifact storage URI must be a valid private s3:// URI.")
        key = _validate_key(unquote(parsed.path.lstrip("/")))
        return parsed.netloc, key
