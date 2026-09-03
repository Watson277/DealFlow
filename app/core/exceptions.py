class DealFlowError(Exception):
    """Base class for expected application errors."""


class CustomerNotFoundError(DealFlowError):
    pass


class CustomerCodeConflictError(DealFlowError):
    pass


class DeletionConflictError(DealFlowError):
    pass


class KnowledgeNotFoundError(DealFlowError):
    pass


class DuplicateKnowledgeError(DealFlowError):
    def __init__(self, document_id: str, title: str) -> None:
        self.document_id = document_id
        self.title = title
        super().__init__(f"知识文档内容重复：{title} ({document_id})")


class UnsupportedDocumentError(DealFlowError):
    pass


class UploadTooLargeError(DealFlowError):
    pass


class EmptyUploadError(DealFlowError):
    pass


class RFPConflictError(DealFlowError):
    pass


class RFPNotFoundError(DealFlowError):
    pass


class RFPRetryConflictError(DealFlowError):
    pass


class DocumentProcessingError(DealFlowError):
    pass


class LLMConfigurationError(DealFlowError):
    pass


class RequirementExtractionError(DealFlowError):
    pass


class KnowledgeIndexError(DealFlowError):
    pass


class CapabilityEvaluationError(DealFlowError):
    pass


class EmbeddingError(DealFlowError):
    pass


class ProposalGenerationError(DealFlowError):
    pass


class ProposalNotFoundError(DealFlowError):
    pass


class ProposalReviewConflictError(DealFlowError):
    pass


class LockNotAcquiredError(DealFlowError):
    pass


class ObjectStorageError(DealFlowError):
    pass
