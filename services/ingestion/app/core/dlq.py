from datetime import datetime as dt
from datetime import timezone as tz
import json
import structlog

from app.core.config import settings
from confluent_kafka import Producer

logger = structlog.get_logger()

# Initialize a raw producer for the DLQ
# Note:
# We use a separate instance from kafka.py because the main producer 
# enforces Avro schemas
# The DLQ needs to accept any data structure (JSON)

dlq_producer = Producer({
    "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS
})

async def send_to_dlq(message: dict, error: str) -> None:
    """
    Send failed messages to the Dead Letter Queue synchronously

    Args:
        message: Message that failed
        error: Error description
    """

    # Construct the DLQ payload
    dlq_payload = {
        "original_message": message,
        "error": error,
        "dlq_ts": dt.now(tz.utc).isoformat(),
    }

    try:
        # Serialize dict to JSON bytes
        value_bytes = json.dumps(dlq_payload).encode("utf-8")

        # Send to Kafka (fire and forget)
        dlq_producer.produce(
            topic=settings.KAFKA_TOPIC_METRICS_DLQ,
            value=value_bytes
        )
        
        # Trigger internal driver loop to handle delivery callbacks
        dlq_producer.poll(0)

        logger.warning(
            "message_sent_to_dlq",
            error=error,
            topic=settings.KAFKA_TOPIC_METRICS_DLQ,
        )

    except Exception as e:
        # If writing to DLQ fails, log explicitly. 
        # In production, you might write this to a local disk file as a last resort.
        logger.error("dlq_send_failed", error=str(e))
