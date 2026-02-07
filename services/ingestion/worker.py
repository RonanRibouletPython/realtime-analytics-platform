import asyncio
import time
from datetime import datetime as dt
from datetime import timezone as tz

import structlog
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.dlq import send_to_dlq
from app.core.metrics_tracker import tracker
from app.models.metric import Metric
from confluent_kafka import DeserializingConsumer, KafkaException
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

avro_deserializer = AvroDeserializer(schema_registry)

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


async def process_message(payload: dict) -> bool:
    """
    Process one Kafka message.

    Returns:
        True  -> commit offset
        False -> retry
    """
    start_time = time.time()

    try:
        async with AsyncSessionLocal() as session:
            metric = Metric(
                name=payload["name"],
                value=payload["value"],
                timestamp=payload["timestamp"],
                labels=payload.get("labels", {}),
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
        logger.error("invalid_message", error=str(e), payload=payload)
        send_to_dlq(payload, str(e))
        tracker.record_dlq()
        return True

    except Exception as e:
        logger.error("processing_failed", error=str(e), payload=payload)
        tracker.record_failure()
        return False


async def consume():
    logger.info("worker_started", topic=settings.KAFKA_TOPIC_METRICS)

    try:
        while True:
            msg = consumer.poll(1.0)

            if msg is None:
                continue

            if msg.error():
                raise KafkaException(msg.error())

            payload = msg.value()

            success = await process_message(payload)

            if success:
                consumer.commit(msg)

    except Exception as e:
        logger.critical("worker_crashed", error=str(e))
    finally:
        consumer.close()
        logger.info("worker_stopped")


if __name__ == "__main__":
    import asyncio

    try:
        asyncio.run(consume())
    except KeyboardInterrupt:
        logger.info("worker_interrupted_manually")
