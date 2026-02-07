from datetime import timezone as tz
from pathlib import Path
import time
import structlog
from confluent_kafka import SerializingProducer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
from confluent_kafka.serialization import StringSerializer

from app.core.config import settings

logger = structlog.get_logger()

# Notes:
# Producer auto registers schemas for us
# Subject name defaults to topic name metrics-topic-value
# Schema versioning is handled automatically
# FastAPI no longer cares about the consumer and just calls send_metric(metric.dict())

# Schema Registry client
_schema_registry = SchemaRegistryClient({"url": settings.SCHEMA_REGISTRY_URL})

# Open the metrics AVRO schema
schema_path = Path(__file__).parent.parent / "schemas" / "metric_event.avsc"
with open(schema_path) as f:
    metric_schema_str = f.read()


def metric_to_dict(metric: dict, ctx) -> dict:
    """
    Convert a metric dictionary into a format suitable for serialization.

    This function takes a dictionary representing a metric and returns a new dictionary
    containing the same information, but in a format that can be serialized by the Avro
    serializer.

    The returned dictionary has the following keys:

    - name (string): the name of the metric
    - value (float): the value of the metric
    - timestamp (integer): the timestamp of the metric in milliseconds since the epoch
    - labels (dict): a dictionary of labels associated with the metric
    """
    return {
        "name": metric.get("name"),
        "value": metric.get("value"),
        "timestamp": int(metric.get("timestamp").astimezone(tz.utc).timestamp() * 1000),
        "labels": metric.get("labels"),
    }


# Avro serializer
avro_serializer = AvroSerializer(
    schema_registry_client=_schema_registry,
    schema_str=metric_schema_str,
    to_dict=metric_to_dict,
)

# Kafka producer
producer = SerializingProducer(
    {
        "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
        "key.serializer": StringSerializer("utf_8"),
        "value.serializer": avro_serializer,
    }
)


def delivery_report(err: object, msg: object) -> None:
    """
    A callback function used by the SerializingProducer to report the delivery status of
    messages sent to Kafka.

    Args:
        err (object): An error object if the delivery failed, otherwise None.
        msg (object): The message object that was sent to Kafka.

    If an error occurred, logs an error message with the topic of the message and the error
    message. If no error occurred, logs a success message with the topic, partition, and offset
    of the message.
    """
    if err:
        logger.error("kafka_delivery_failed", error=str(err), topic=msg.topic())
    else:
        logger.info(
            "kafka_message_sent",
            topic=msg.topic(),
            partition=msg.partition(),
            offset=msg.offset(),
        )


def send_metric(metric: dict) -> None:
    producer.produce(
        topic=settings.KAFKA_TOPIC_METRICS,
        key=metric.get("name"),
        value=metric,
        on_delivery=delivery_report,
    )
    # Required to serve delivery callbacks
    producer.poll(0)

def flush_producer() -> None:
    """
    Flush the producer to ensure all messages are delivered before shutdown.
    Blocking operation.
    """
    logger.info("kafka_flushing_messages")
    start = time.time()
    # Wait up to 10 seconds for messages to be delivered
    left_msg = producer.flush(timeout=10.0)
    
    if left_msg > 0:
        logger.error("kafka_flush_incomplete", remaining=left_msg)
    else:
        logger.info("kafka_flush_complete", duration=time.time() - start)