from datetime import datetime

from sqlalchemy import BigInteger, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin, utc_now


class ConsumedEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "consumed_events"
    __table_args__ = (
        UniqueConstraint(
            "consumer_group",
            "event_id",
            name="uq_consumed_events_group_event",
        ),
        UniqueConstraint(
            "consumer_group",
            "topic",
            "partition",
            "offset",
            name="uq_consumed_events_group_topic_partition_offset",
        ),
        Index("ix_consumed_events_consumed_at", "consumed_at"),
    )

    consumer_group: Mapped[str] = mapped_column(String(100), nullable=False)
    event_id: Mapped[str] = mapped_column(String(100), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    partition: Mapped[int] = mapped_column(Integer, nullable=False)
    offset: Mapped[int] = mapped_column(BigInteger, nullable=False)
    consumed_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6),
        nullable=False,
        default=utc_now,
    )
