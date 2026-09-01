import asyncio
from typing import Any

import orjson
from aiokafka import AIOKafkaProducer  # type: ignore[import-untyped]

from app.core.config import Settings, get_settings


class KafkaProducerService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._producer: AIOKafkaProducer | None = None
        self._start_lock = asyncio.Lock()

    async def start(self) -> None:
        if self._producer is not None:
            return
        async with self._start_lock:
            if self._producer is not None:
                return
            producer = AIOKafkaProducer(
                bootstrap_servers=self.settings.kafka_bootstrap_servers,
                client_id=self.settings.kafka_client_id,
                value_serializer=orjson.dumps,
            )
            try:
                await producer.start()
            except Exception:
                await producer.stop()
                raise
            self._producer = producer

    async def stop(self) -> None:
        if self._producer is None:
            return
        producer = self._producer
        self._producer = None
        await producer.stop()

    async def publish(self, *, topic: str, event_key: str, payload: dict[str, Any]) -> None:
        await self.start()
        if self._producer is None:
            raise RuntimeError("Kafka producer is not available")
        await self._producer.send_and_wait(
            topic,
            value=payload,
            key=event_key.encode("utf-8"),
        )


_kafka_service: KafkaProducerService | None = None


def get_kafka_service() -> KafkaProducerService:
    global _kafka_service
    if _kafka_service is None:
        _kafka_service = KafkaProducerService(get_settings())
    return _kafka_service
