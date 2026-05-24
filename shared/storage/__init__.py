from shared.storage.base import StorageBackend, StoredObject
from shared.storage.minio_backend import MinioStorage
from shared.storage.local_backend import LocalStorage


def build_storage() -> StorageBackend:
    """Construct the configured storage backend (MinIO by default)."""
    from shared.config import get_settings

    settings = get_settings()
    return MinioStorage(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        bucket=settings.minio_bucket,
        region=settings.minio_region,
        public_domain=settings.minio_public_domain,
        use_ssl=settings.minio_use_ssl,
    )


__all__ = ["StorageBackend", "StoredObject", "MinioStorage", "LocalStorage", "build_storage"]
