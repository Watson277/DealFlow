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
