import asyncio
import hashlib
import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

from fastapi import UploadFile
from minio import Minio

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    EmptyUploadError,
    ObjectStorageError,
    UnsupportedDocumentError,
    UploadTooLargeError,
)

ALLOWED_EXTENSIONS = {".pdf", ".docx"}
CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


@dataclass(frozen=True, slots=True)
class StoredObject:
    bucket: str
    object_key: str
    original_filename: str
    content_type: str
    size_bytes: int
    checksum_sha256: str


class ObjectStorageService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )

    async def upload_rfp(
        self,
        upload: UploadFile,
        *,
        rfp_id: str,
        document_id: str,
    ) -> StoredObject:
        original_filename = Path(upload.filename or "upload").name
        extension = Path(original_filename).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise UnsupportedDocumentError("only PDF and DOCX files are supported")

        safe_filename = self._sanitize_filename(original_filename)
        object_key = f"rfp/{rfp_id}/source/{document_id}/{safe_filename}"
        return await self._upload_document(upload, object_key, extension)

    async def upload_knowledge(
        self,
        upload: UploadFile,
        *,
        document_id: str,
        category: str,
    ) -> StoredObject:
        original_filename = Path(upload.filename or "upload").name
        extension = Path(original_filename).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise UnsupportedDocumentError("only PDF and DOCX files are supported")
        safe_filename = self._sanitize_filename(original_filename)
        safe_category = self._sanitize_filename(category.lower())
        object_key = f"knowledge/{safe_category}/{document_id}/{safe_filename}"
        return await self._upload_document(upload, object_key, extension)

    async def _upload_document(
        self,
        upload: UploadFile,
        object_key: str,
        extension: str,
    ) -> StoredObject:
        original_filename = Path(upload.filename or "upload").name
        size_bytes, checksum = await asyncio.to_thread(
            self._inspect_stream,
            upload.file,
            self.settings.max_rfp_upload_size_bytes,
        )
        content_type = upload.content_type or CONTENT_TYPES[extension]

        try:
            await asyncio.to_thread(
                self.client.put_object,
                self.settings.minio_bucket,
                object_key,
                upload.file,
                size_bytes,
                content_type=content_type,
            )
        except Exception as exc:
            raise ObjectStorageError("failed to upload document to object storage") from exc

        return StoredObject(
            bucket=self.settings.minio_bucket,
            object_key=object_key,
            original_filename=original_filename,
            content_type=content_type,
            size_bytes=size_bytes,
            checksum_sha256=checksum,
        )

    async def remove(self, bucket: str, object_key: str) -> None:
        try:
            await asyncio.to_thread(self.client.remove_object, bucket, object_key)
        except Exception as exc:
            raise ObjectStorageError("failed to remove object from storage") from exc

    async def download(self, bucket: str, object_key: str) -> bytes:
        try:
            return await asyncio.to_thread(self._download, bucket, object_key)
        except Exception as exc:
            raise ObjectStorageError("failed to download object from storage") from exc

    async def upload_text(
        self,
        object_key: str,
        text: str,
        *,
        content_type: str = "text/plain; charset=utf-8",
    ) -> StoredObject:
        content = text.encode("utf-8")
        checksum = hashlib.sha256(content).hexdigest()
        try:
            await asyncio.to_thread(
                self.client.put_object,
                self.settings.minio_bucket,
                object_key,
                BytesIO(content),
                len(content),
                content_type=content_type,
            )
        except Exception as exc:
            raise ObjectStorageError("failed to upload text object") from exc
        return StoredObject(
            bucket=self.settings.minio_bucket,
            object_key=object_key,
            original_filename=Path(object_key).name,
            content_type=content_type,
            size_bytes=len(content),
            checksum_sha256=checksum,
        )

    def _download(self, bucket: str, object_key: str) -> bytes:
        response = self.client.get_object(bucket, object_key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    @staticmethod
    def _inspect_stream(stream: BinaryIO, max_size: int) -> tuple[int, str]:
        stream.seek(0)
        size = 0
        digest = hashlib.sha256()
        try:
            while chunk := stream.read(1024 * 1024):
                size += len(chunk)
                if size > max_size:
                    raise UploadTooLargeError(f"file exceeds the {max_size}-byte limit")
                digest.update(chunk)
        finally:
            stream.seek(0)

        if size == 0:
            raise EmptyUploadError("uploaded file is empty")
        return size, digest.hexdigest()

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", filename).strip("._")
        return sanitized[:200] or "document"


def get_object_storage_service() -> ObjectStorageService:
    return ObjectStorageService(get_settings())
