"""Object storage adapters."""

from app.infrastructure.storage.local_artifacts import LocalArtifactExporter
from app.infrastructure.storage.minio import (
    ObjectStorageService,
    StoredObject,
    get_object_storage_service,
)

__all__ = [
    "LocalArtifactExporter",
    "ObjectStorageService",
    "StoredObject",
    "get_object_storage_service",
]
