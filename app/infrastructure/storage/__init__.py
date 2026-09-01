"""Object storage adapters."""

from app.infrastructure.storage.minio import (
    ObjectStorageService,
    StoredObject,
    get_object_storage_service,
)

__all__ = ["ObjectStorageService", "StoredObject", "get_object_storage_service"]
