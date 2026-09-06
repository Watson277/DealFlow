from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)

from app.api.dependencies import get_knowledge_service
from app.core.exceptions import (
    DeletionConflictError,
    DocumentProcessingError,
    DuplicateKnowledgeError,
    EmbeddingError,
    EmptyUploadError,
    KnowledgeIndexError,
    KnowledgeNotFoundError,
    LLMConfigurationError,
    ObjectStorageError,
    UnsupportedDocumentError,
    UploadTooLargeError,
)
from app.schemas.knowledge import KnowledgeDocumentListResponse, KnowledgeDocumentResponse
from app.services.knowledge import KnowledgeService

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


def _duplicate_response(exc: DuplicateKnowledgeError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "KNOWLEDGE_DUPLICATE",
            "message": "该文件内容已存在，未重复写入知识库",
            "existing_document_id": exc.document_id,
            "existing_title": exc.title,
        },
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_knowledge_document(
    document_id: UUID,
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
) -> Response:
    try:
        await service.delete(str(document_id))
    except KnowledgeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DeletionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except KnowledgeIndexError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    finally:
        await service.close()
    return Response(status_code=204)


@router.post("", response_model=KnowledgeDocumentResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_knowledge_document(
    file: Annotated[
        UploadFile,
        File(description="Enterprise knowledge PDF, DOCX, MD, or MARKDOWN file"),
    ],
    title: Annotated[str, Form(min_length=1, max_length=255)],
    category: Annotated[str, Form(min_length=1, max_length=64)],
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
    version: Annotated[str | None, Form(max_length=32)] = None,
) -> KnowledgeDocumentResponse:
    try:
        document = await service.enqueue_ingestion(
            file,
            title=title,
            category=category,
            version=version,
        )
    except DuplicateKnowledgeError as exc:
        raise _duplicate_response(exc) from exc
    except UnsupportedDocumentError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(exc),
        ) from exc
    except UploadTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(exc),
        ) from exc
    except EmptyUploadError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except DocumentProcessingError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except (
        EmbeddingError,
        LLMConfigurationError,
        ObjectStorageError,
        KnowledgeIndexError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    finally:
        await file.close()
        await service.close()
    return KnowledgeDocumentResponse.model_validate(document)


@router.put("/{document_id}", response_model=KnowledgeDocumentResponse)
async def update_knowledge_document(
    document_id: UUID,
    file: Annotated[
        UploadFile,
        File(description="Replacement enterprise knowledge PDF, DOCX, MD, or MARKDOWN file"),
    ],
    title: Annotated[str, Form(min_length=1, max_length=255)],
    category: Annotated[str, Form(min_length=1, max_length=64)],
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
    version: Annotated[str | None, Form(max_length=32)] = None,
) -> KnowledgeDocumentResponse:
    try:
        document = await service.update(
            str(document_id),
            file,
            title=title,
            category=category,
            version=version,
        )
    except DuplicateKnowledgeError as exc:
        raise _duplicate_response(exc) from exc
    except KnowledgeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DeletionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except UnsupportedDocumentError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except UploadTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except EmptyUploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DocumentProcessingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (
        EmbeddingError,
        LLMConfigurationError,
        ObjectStorageError,
        KnowledgeIndexError,
    ) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    finally:
        await file.close()
        await service.close()
    return KnowledgeDocumentResponse.model_validate(document)


@router.get("", response_model=KnowledgeDocumentListResponse)
async def list_knowledge_documents(
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> KnowledgeDocumentListResponse:
    try:
        page = await service.list(offset=offset, limit=limit)
    finally:
        await service.close()
    return KnowledgeDocumentListResponse(
        items=[KnowledgeDocumentResponse.model_validate(item) for item in page.items],
        total=page.total,
    )


@router.get("/{document_id}", response_model=KnowledgeDocumentResponse)
async def get_knowledge_document(
    document_id: UUID,
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
) -> KnowledgeDocumentResponse:
    try:
        document = await service.get(str(document_id))
    except KnowledgeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        await service.close()
    return KnowledgeDocumentResponse.model_validate(document)
