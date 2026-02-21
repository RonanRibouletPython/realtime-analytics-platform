import asyncio
import time
from datetime import datetime as dt
from datetime import timezone as tz
from pathlib import Path

import structlog
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.dlq import send_to_dlq
from app.core.metrics_tracker import start_metrics_server, tracker
from app.models.metric import Metric
from confluent_kafka import DeserializingConsumer, KafkaException, Message
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer
from confluent_kafka.serialization import StringDeserializer

logger = structlog.get_logger()

# Note
# Consumer fetches the schema automatically
# Deserialize Avro into a Python dictionary
# Convert timestamp into a datetime object
# Writes to the DB
# Commits the offset automatically

# Schema registry
schema_registry = SchemaRegistryClient({"url": settings.SCHEMA_REGISTRY_URL})

_schema_path = Path(__file__).parent / "schemas" / "metric_event_v2.avsc"
with open(_schema_path) as f:
    _reader_schema_str = f.read()

avro_deserializer = AvroDeserializer(
    schema_registry,
    _reader_schema_str,  # reader schema — tells deserializer to return 'environment'
)

# Kafka consumer
consumer = DeserializingConsumer(
    {
        "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
        "group.id": "metrics_worker_group",
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
        "key.deserializer": StringDeserializer("utf_8"),
        "value.deserializer": avro_deserializer,
    }
)

consumer.subscribe([settings.KAFKA_TOPIC_METRICS])


async def process_message(message: Message) -> bool:
    """
    Process one Kafka message.

    Args:
        message: The raw confluent_kafka.Message — we pass the full object now,
             not just the payload, so we can forward it to the DLQ with
             full forensics context if processing fails.

    Returns:
        True  → commit offset (success or permanent failure routed to DLQ)
        False → do not commit (transient failure, will retry on next poll)
    """
    start_time = time.time()
    payload = message.value()

    try:
        async with AsyncSessionLocal() as session:
            metric = Metric(
                name=payload["name"],
                value=payload["value"],
                timestamp=payload["timestamp"],
                labels=payload.get("labels", {}),
                environment=payload.get("environment"),
            )

            session.add(metric)
            await session.commit()

        processing_time = (time.time() - start_time) * 1000
        tracker.record_success(processing_time)

        logger.info(
            "metric_processed",
            name=metric.name,
            value=metric.value,
        )

        return True

    except ValueError as e:
        # Permanent failure: malformed data. No retry will fix this.
        # Route to DLQ and commit the offset to skip past it.
        logger.error("invalid_message_routed_to_dlq", error=str(e), payload=payload)
        # FIX 1: was missing 'await' — DLQ was silently never called
        await send_to_dlq(message, error=str(e), reason="ValueError")
        # FIX 2: pass reason string so Prometheus label is meaningful
        tracker.record_dlq(reason="ValueError")
        return True  # Commit: we've handled it (via DLQ), move on

    except Exception as e:
        # Transient failure: DB might be down, connection pool exhausted, etc.
        # Do not commit — let Kafka redeliver this message after a reconnect.
        logger.error("processing_failed_will_retry", error=str(e), payload=payload)
        tracker.record_failure()
        return False


async def consume():
    # Start Prometheus metrics server before the consume loop.
    # ODD principle: observability up before workload begins.
    start_metrics_server(port=8001)

    logger.info("worker_started", topic=settings.KAFKA_TOPIC_METRICS)

    loop = asyncio.get_running_loop()

    try:
        while True:
            # FIX 3: Run blocking poll() in a thread executor.
            # Without this, consumer.poll(1.0) freezes the entire event loop
            # for 1 second — no DB writes, no coroutines, nothing.
            # run_in_executor offloads it to a thread while the loop stays free.
            message: Message | None = await loop.run_in_executor(
                None,  # uses the default ThreadPoolExecutor
                consumer.poll,  # the blocking function
                1.0,  # poll timeout in seconds
            )

            if message is None:
                continue

            if message.error():
                raise KafkaException(message.error())

            success = await process_message(message)

            if success:
                consumer.commit(message=message)

    except Exception as e:
        logger.critical("worker_crashed", error=str(e))
    finally:
        consumer.close()
        logger.info("worker_stopped")


if __name__ == "__main__":
    try:
        asyncio.run(consume())
    except KeyboardInterrupt:
        logger.info("worker_interrupted_manually")
