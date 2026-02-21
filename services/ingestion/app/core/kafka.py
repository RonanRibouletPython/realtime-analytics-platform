import asyncio
import time
from datetime import timezone as tz
from pathlib import Path

import structlog
from confluent_kafka import SerializingProducer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
from confluent_kafka.serialization import StringSerializer

from app.core.config import settings

logger = structlog.get_logger()


# ── SCHEMA REGISTRY & AVRO SETUP ─────────────────────────────────────────────
_schema_registry = SchemaRegistryClient({"url": settings.SCHEMA_REGISTRY_URL})

schema_path = Path(__file__).parent.parent / "schemas" / "metric_event_v1.avsc"
with open(schema_path) as f:
    metric_schema_str = f.read()


def metric_to_dict(metric: dict, ctx) -> dict:
    """
    Convert a metric dictionary to Avro-serializable format.

    Raises:
        ValueError: if timestamp is missing or not a datetime object.
                    Surfaces as a clean error rather than a cryptic
                    AttributeError deep inside the Avro serializer.
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
    }


avro_serializer = AvroSerializer(
    schema_registry_client=_schema_registry,
    schema_str=metric_schema_str,
    to_dict=metric_to_dict,
)

producer = SerializingProducer(
    {
        "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
        "key.serializer": StringSerializer("utf_8"),
        "value.serializer": avro_serializer,
    }
)


# ── DELIVERY CALLBACK ─────────────────────────────────────────────────────────
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


# ── PRODUCER FUNCTIONS ────────────────────────────────────────────────────────
async def send_metric(metric: dict) -> None:
    """
    Async wrapper around confluent-kafka's synchronous produce() call.

    WHY run_in_executor:
    producer.produce() and producer.poll() are blocking C-extension calls.
    Calling them directly in an async FastAPI route freezes the entire event
    loop for the duration of the call — every other request waits.
    run_in_executor() offloads the blocking work to a thread pool, keeping
    the event loop free to serve other requests while Kafka is being written to.

    NOTE: this function is now async — any caller must await it.
    Update your route: `await send_metric(metric.model_dump())`
    """
    loop = asyncio.get_running_loop()

    # FIX 2: offload blocking produce() + poll() to a thread
    # We wrap both calls in a single lambda so they execute together
    # in the same thread, maintaining the correct poll-after-produce ordering.
    await loop.run_in_executor(
        None,  # default ThreadPoolExecutor
        lambda: (
            producer.produce(
                topic=settings.KAFKA_TOPIC_METRICS,
                key=metric.get("name"),
                value=metric,
                on_delivery=delivery_report,
            ),
            producer.poll(0),
        ),
    )


async def check_kafka_health() -> None:
    """
    Probe broker reachability by fetching cluster metadata.

    list_topics() does a real round-trip to the broker — if it completes
    within the timeout, the broker is up and the producer is connected.
    If it times out or throws, we let the exception propagate to the
    /kafka_health endpoint which catches it and returns 503.

    Raises:
        Exception: any broker connectivity or timeout error.
    """
    loop = asyncio.get_running_loop()

    # NEW: same run_in_executor pattern — list_topics() is also a
    # blocking call so we keep it off the event loop.
    await loop.run_in_executor(
        None,
        lambda: producer.list_topics(timeout=3.0),
    )

    logger.debug("kafka_health_check_passed")


def flush_producer() -> None:
    """
    Flush the producer buffer on shutdown.
    Blocking by design — called from lifespan() after yield,
    outside the async context, so no run_in_executor needed here.
    """
    logger.info("kafka_flushing_messages")
    start = time.time()
    remaining = producer.flush(timeout=10.0)

    if remaining > 0:
        logger.error("kafka_flush_incomplete", remaining=remaining)
    else:
        logger.info("kafka_flush_complete", duration_sec=round(time.time() - start, 3))
