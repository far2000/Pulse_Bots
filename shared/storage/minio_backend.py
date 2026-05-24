"""S3-compatible storage via aioboto3 (works with MinIO and any S3 provider)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import aioboto3
from botocore.config import Config
from botocore.exceptions import ClientError
from loguru import logger

from shared.storage.base import StorageBackend, StoredObject


class MinioStorage(StorageBackend):
    def __init__(
        self,
        *,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        region: str = "us-east-1",
        public_domain: str | None = None,
        use_ssl: bool = False,
    ) -> None:
        self.endpoint = endpoint
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket = bucket
        self.region = region
        self.public_domain = public_domain.rstrip("/") if public_domain else None
        self.use_ssl = use_ssl
        self._session = aioboto3.Session()
        self._config = Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},  # MinIO requires path-style
            retries={"max_attempts": 3, "mode": "standard"},
        )

    @asynccontextmanager
    async def _client(self) -> AsyncIterator[object]:
        async with self._session.client(
            "s3",
            endpoint_url=self.endpoint,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region,
            use_ssl=self.use_ssl,
            config=self._config,
        ) as client:
            yield client

    async def ensure_ready(self) -> None:
        """Create the bucket if missing. Safe to call repeatedly."""
        async with self._client() as s3:
            try:
                await s3.head_bucket(Bucket=self.bucket)
            except ClientError as exc:
                code = exc.response.get("Error", {}).get("Code", "")
                if code in {"404", "NoSuchBucket", "NotFound"}:
                    logger.info("Creating bucket: {}", self.bucket)
                    create_args: dict[str, object] = {"Bucket": self.bucket}
                    if self.region != "us-east-1":
                        create_args["CreateBucketConfiguration"] = {
                            "LocationConstraint": self.region
                        }
                    await s3.create_bucket(**create_args)
                else:
                    raise

    async def put(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
        cache_control: str | None = "public, max-age=31536000, immutable",
    ) -> StoredObject:
        kwargs: dict[str, object] = {
            "Bucket": self.bucket,
            "Key": key,
            "Body": data,
            "ContentType": content_type,
        }
        if cache_control:
            kwargs["CacheControl"] = cache_control
        async with self._client() as s3:
            await s3.put_object(**kwargs)
        return StoredObject(
            key=key,
            public_url=self.public_url(key),
            size=len(data),
            content_type=content_type,
        )

    async def exists(self, key: str) -> bool:
        async with self._client() as s3:
            try:
                await s3.head_object(Bucket=self.bucket, Key=key)
                return True
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
                    return False
                raise

    async def delete(self, key: str) -> None:
        async with self._client() as s3:
            await s3.delete_object(Bucket=self.bucket, Key=key)

    def public_url(self, key: str) -> str | None:
        if self.public_domain:
            return f"{self.public_domain}/{key}"
        # Fallback to a direct endpoint URL — only useful in dev.
        return f"{self.endpoint.rstrip('/')}/{self.bucket}/{key}"
