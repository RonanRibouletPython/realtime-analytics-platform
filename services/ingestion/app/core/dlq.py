from datetime import datetime as dt
from datetime import timezone as tz

import structlog
from aiokafka import AIOKafkaProducer

from app.core.config import settings

logger = structlog.get_logger()


async def send_to_dlq(producer: AIOKafkaProducer, message: dict, error: str) -> None:
    """
    Send failed messages to the Dead Letter Queue

    Args:
        producer: Kafka producer instance
        message: Message that failed
        error: Error description
    """

    dlq_message = {
        "original_message": message,
        "error": error,
        "dlq_ts": dt.now(tz.utc).isoformat(),
    }

    try:
        await producer.send_and_wait(
            topic=f"{settings.KAFKA_TOPIC_METRICS}_dlq",
            value=dlq_message,
        )
        logger.warning(
            "message_sent_to_dlq",
            error=error,
            original_topic=settings.KAFKA_TOPIC_METRICS,
        )
    except Exception as e:
        logger.error("dlq_send_failed", error=str(e), message=message)
