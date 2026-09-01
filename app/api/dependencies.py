from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db_session
from app.documents.parser import DocumentParser
from app.infrastructure.messaging.kafka import KafkaProducerService, get_kafka_service
from app.infrastructure.messaging.outbox import OutboxPublisher
from app.infrastructure.storage.minio import ObjectStorageService, get_object_storage_service
from app.rag.chunking import KnowledgeChunker
from app.rag.embedding import OpenAIEmbeddingService
from app.rag.vector_store import QdrantKnowledgeStore
from app.services.capability import CapabilityService
from app.services.customer import CustomerService
from app.services.knowledge import KnowledgeService
from app.services.proposal import ProposalService
from app.services.proposal_review import ProposalReviewService
from app.services.requirement import RequirementService
from app.services.rfp import RFPService


def get_customer_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CustomerService:
    return CustomerService(session)


def get_capability_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CapabilityService:
    return CapabilityService(session)


def get_rfp_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    storage: Annotated[ObjectStorageService, Depends(get_object_storage_service)],
    kafka: Annotated[KafkaProducerService, Depends(get_kafka_service)],
) -> RFPService:
    return RFPService(
        settings=get_settings(),
        session=session,
        storage=storage,
        outbox_publisher=OutboxPublisher(kafka),
    )


def get_requirement_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> RequirementService:
    return RequirementService(session)


def get_proposal_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    storage: Annotated[ObjectStorageService, Depends(get_object_storage_service)],
) -> ProposalService:
    return ProposalService(session, storage)


def get_proposal_review_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    storage: Annotated[ObjectStorageService, Depends(get_object_storage_service)],
    kafka: Annotated[KafkaProducerService, Depends(get_kafka_service)],
) -> ProposalReviewService:
    return ProposalReviewService(
        settings=get_settings(),
        session=session,
        storage=storage,
        outbox_publisher=OutboxPublisher(kafka),
    )


def get_knowledge_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    storage: Annotated[ObjectStorageService, Depends(get_object_storage_service)],
) -> KnowledgeService:
    settings = get_settings()
    return KnowledgeService(
        session=session,
        storage=storage,
        parser=DocumentParser(),
        chunker=KnowledgeChunker(settings),
        embeddings=OpenAIEmbeddingService(settings),
        vector_store=QdrantKnowledgeStore(settings),
    )
