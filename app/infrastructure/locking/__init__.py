"""Distributed locking adapters."""

from app.infrastructure.locking.redis import DistributedLockService

__all__ = ["DistributedLockService"]
