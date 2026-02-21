import json
from datetime import datetime as dt
from datetime import timezone as tz

import structlog
from confluent_kafka import Message, Producer

from app.core.config import settings

logger = structlog.get_logger()

# Separate producer from main Avro producer — intentional.
# The DLQ must accept any payload (we can't Avro-serialize a message that
# failed Avro deserialization — that's circular).
_dlq_producer = Producer(
    {
        "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
        # acks=all: DLQ messages MUST be durable. Losing forensics data means
        # losing the ability to debug and replay. Don't compromise here.
        "acks": "all",
    }
)


async def send_to_dlq(message: Message, error: str, reason: str = "unknown") -> None:
    """
    Route a failed Kafka message to the Dead Letter Queue.

    Wraps the original message in a forensics envelope containing everything
    needed to debug, replay, or alert on the failure later.

    Args:
        message: The original confluent_kafka.Message object (carries topic,
             partition, offset, key, and raw value bytes).
        error: Human-readable error description.
        reason: Short machine-readable reason code for Prometheus labeling.
                e.g. "ValueError", "deserialization_error", "db_write_error"
    """

    # We build the forensic envelope
    # raw value as hex: the ONLY safe representation when the bytes themselves
    # may have caused a deserialization failure (can't assume UTF-8).

    # Construct the DLQ payload
    raw_value_hex: str | None = None
    if message.value() is not None:
        try:
            raw_value_hex = message.value().hex()
        except Exception:
            raw_value_hex = "<unreadable>"

    dlq_payload = {
        # Context to reconstruct what happened
        "dlq_metadata": {
            "routed_at_utc": dt.now(tz.utc).isoformat(),
            "reason": reason,
            "error": error,
        },
        # Context to find the original message in Kafka for manual replay
        "source": {
            "topic": message.topic(),
            "partition": message.partition(),
            "offset": message.offset(),
            "timestamp_ms": message.timestamp()[1] if message.timestamp() else None,
            "key": message.key().decode("utf-8", errors="replace")
            if message.key()
            else None,
            # Hex-encoded raw bytes — reconstruct the original with:
            # bytes.fromhex(raw_value_hex)
            "raw_value_hex": raw_value_hex,
        },
    }

    try:
        # Serialize dict to JSON bytes
        value_bytes = json.dumps(dlq_payload).encode("utf-8")

        _dlq_producer.produce(
            topic=settings.KAFKA_TOPIC_METRICS_DLQ,
            value=value_bytes,
            # Preserve the original key for traceability
            key=message.key(),
        )

        # flush() instead of poll(0): ensures the message is actually delivered
        # before we commit the original offset. poll(0) only triggers callbacks
        # — it doesn't guarantee delivery.
        _dlq_producer.flush(timeout=5.0)

        logger.warning(
            "message_routed_to_dlq",
            reason=reason,
            error=error,
            source_topic=message.topic(),
            source_partition=message.partition(),
            source_offset=message.offset(),
            dlq_topic=settings.KAFKA_TOPIC_METRICS_DLQ,
        )

    except Exception as e:
        # If DLQ itself fails, log at CRITICAL level.
        # This is a last-resort safety net — in production you'd also
        # write to a local disk file or a secondary alerting channel.
        logger.critical(
            "dlq_send_failed",
            error=str(e),
            source_topic=message.topic(),
            source_partition=message.partition(),
            source_offset=message.offset(),
        )
