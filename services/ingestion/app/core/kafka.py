import asyncio
import time
from datetime import timezone as tz
from enum import Enum
from pathlib import Path

import structlog
from confluent_kafka import SerializingProducer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
from confluent_kafka.serialization import (
    MessageField,
    SerializationContext,
    StringSerializer,
)

from app.core.config import settings

logger = structlog.get_logger()


# SCHEMA VERSION ENUM
# The caller imports this and passes it to send_metric().
# Using an Enum instead of a raw string prevents typos like "v 1" or "V1"
# from silently falling through to a wrong serializer.
class SchemaVersion(str, Enum):
    V1 = "v1"
    V2 = "v2"


# SCHEMA REGISTRY & AVRO SETUP
_schema_registry = SchemaRegistryClient({"url": settings.SCHEMA_REGISTRY_URL})

_schemas_dir = Path(__file__).parent.parent / "schemas"


def _load_schema(filename: str) -> str:
    path = _schemas_dir / filename
    with open(path) as f:
        return f.read()


def metric_to_dict(metric: dict, ctx) -> dict:
    """
    Shared conversion function for both v1 and v2.
    v2's extra 'environment' field is passed through naturally via .get()
    — if the caller doesn't provide it, it defaults to None, which maps
    to Avro null, matching the schema default.
    """
    timestamp = metric.get("timestamp")

    # FIX 1: explicit guard instead of chaining .astimezone() on a potential None.
    # Previously, a missing timestamp would raise AttributeError inside the Avro
    # serializer with no useful context. Now it raises ValueError here, caught
    # cleanly by the route and by the consumer's DLQ routing logic.
    if timestamp is None:
        raise ValueError("metric 'timestamp' field is required and cannot be None")

    return {
        "name": metric.get("name"),
        "value": metric.get("value"),
        "timestamp": int(timestamp.astimezone(tz.utc).timestamp() * 1000),
        "labels": metric.get("labels"),
        # v1 serializer will ignore this key — it's not in the v1 schema.
        # v2 serializer will use it. One conversion function, both versions.
        "environment": metric.get("environment", None),
    }


_serializer_v1 = AvroSerializer(
    schema_registry_client=_schema_registry,
    schema_str=_load_schema("metric_event_v1.avsc"),
    to_dict=metric_to_dict,
)

_serializer_v2 = AvroSerializer(
    schema_registry_client=_schema_registry,
    schema_str=_load_schema("metric_event_v2.avsc"),
    to_dict=metric_to_dict,
)

# Map enum → serializer for O(1) lookup, no if/elif chain
_SERIALIZERS: dict[SchemaVersion, AvroSerializer] = {
    SchemaVersion.V1: _serializer_v1,
    SchemaVersion.V2: _serializer_v2,
}

# Single shared producer — no value.serializer set here because we inject
# it per-message via the produce() call's own serialization context
_base_producer = SerializingProducer(
    {
        "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
        "key.serializer": StringSerializer("utf_8"),
        # No value.serializer here — we pass it per-produce() call below
    }
)


# DELIVERY CALLBACK
def delivery_report(err: object, msg: object) -> None:
    if err:
        logger.error("kafka_delivery_failed", error=str(err), topic=msg.topic())
    else:
        logger.info(
            "kafka_message_sent",
            topic=msg.topic(),
            partition=msg.partition(),
            offset=msg.offset(),
        )


# PUBLIC API
async def send_metric(
    metric: dict,
    version: SchemaVersion = SchemaVersion.V2,  # default to latest
) -> None:
    """
    Produce a metric event to Kafka using the specified schema version.

    Args:
        metric: The metric payload as a dict.
        version: Schema version to serialize with. Defaults to V2 (latest).
                 Pass SchemaVersion.V1 for legacy routes that haven't migrated.

    Usage:
        # Default — uses v2
        await send_metric(metric.model_dump())

        # Explicit version — for routes that haven't migrated yet
        await send_metric(metric.model_dump(), version=SchemaVersion.V1)
    """
    serializer = _SERIALIZERS[version]
    loop = asyncio.get_running_loop()

    # FIX: build a proper SerializationContext so the AvroSerializer
    # can resolve the subject name (metrics.raw-value) from the topic.
    # MessageField.VALUE tells it we're serializing the message value,
    # not the key — subject name strategy depends on this distinction.
    ctx = SerializationContext(settings.KAFKA_TOPIC_METRICS, MessageField.VALUE)

    await loop.run_in_executor(
        None,
        lambda: (
            _base_producer.produce(
                topic=settings.KAFKA_TOPIC_METRICS,
                key=metric.get("name"),
                value=serializer(metric, ctx),  # serialize manually before produce
                on_delivery=delivery_report,
            ),
            _base_producer.poll(0),
        ),
    )

    logger.debug("metric_queued", version=version.value, name=metric.get("name"))


async def check_kafka_health() -> None:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        lambda: _base_producer.list_topics(timeout=3.0),
    )
    logger.debug("kafka_health_check_passed")


def flush_producer() -> None:
    logger.info("kafka_flushing_messages")
    start = time.time()
    remaining = _base_producer.flush(timeout=10.0)
    if remaining > 0:
        logger.error("kafka_flush_incomplete", remaining=remaining)
    else:
        logger.info("kafka_flush_complete", duration_sec=round(time.time() - start, 3))
