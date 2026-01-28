import json

import structlog
from aiokafka import AIOKafkaProducer

from app.core.config import settings

logger = structlog.get_logger()

# Global producer instance
_producer: AIOKafkaProducer | None = None


async def get_kafka_producer() -> AIOKafkaProducer:
    """
    Get a global instance of AIOKafkaProducer.

    The instance is created lazily when this function is first called.
    The instance is configured with the bootstrap servers from the environment
    variables, and it serializes messages as JSON.

    Returns:
        AIOKafkaProducer: The global Kafka producer instance.
    """
    global _producer

    if _producer is None:
        _producer = AIOKafkaProducer(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            # Serialize JSON automatically
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )
        await _producer.start()
        logger.info("startup", msg="Kafka producer started!")
    return _producer


async def stop_kafka_producer():
    """
    Stop the global Kafka producer instance.

    This function should be called when the application is shutting down.
    It will stop the producer and release any system resources it was using.
    """
    global _producer
    if _producer:
        await _producer.stop()
        _producer = None
        logger.info("shutdown", msg="Kafka producer stopped")
