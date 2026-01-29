import asyncio
import json
import time
from datetime import datetime as dt

import structlog
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.dlq import send_to_dlq
from app.core.metrics_tracker import tracker
from app.models.metric import Metric
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


async def process_message(
    session: AsyncSession, message_value: dict, producer: AIOKafkaProducer
) -> bool:
    """
    Process a single message from Kafka and save to DB.

    Returns:
        bool:
            True if successful and sent to the DLQ
            False if should retry
    """
    start_time = time.time()

    try:
        # Convert the timestamp string into a datetime object
        message_value["timestamp"] = dt.fromisoformat(message_value["timestamp"])

        # Convert the raw dictionnary into SQLAlchemy model
        metric = Metric(
            name=message_value.get("name"),
            value=message_value.get("value"),
            timestamp=message_value.get("timestamp"),
            labels=message_value.get("labels", {}),
        )

        session.add(metric)
        await session.commit()

        logger.info(
            "metric_processed",
            name=metric.name,
            value=metric.value,
            partition=message_value.get("partition"),
            offset=message_value.get("offset"),
        )

        processing_time = (time.time() - start_time) * 1000
        tracker.record_success(processing_time)
        return True

    except ValueError as e:
        # Invalid data format - send directly to the DLQ
        logger.error("invalid_message_format", error=str(e), payload=message_value)
        await send_to_dlq(producer, message_value, f"Invalid format: {str(e)}")
        await session.rollback()
        tracker.record_dlq()
        return True  # mark as resolved to avoid retries

    except Exception as e:
        # Database error
        logger.error("processing_error", error=str(e), payload=message_value)
        await session.rollback()
        tracker.record_failure()
        return False  # retry


async def consume():
    """
    Main consumer loop with error handling
    """
    logger.info("Worker starting!", topic=settings.KAFKA_TOPIC_METRICS)

    # Initialize the Consumer
    consumer = AIOKafkaConsumer(
        settings.KAFKA_TOPIC_METRICS,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id="metrics_worker_group",
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        auto_offset_reset="earliest",  # Start from beginning if no history exists
        enable_auto_commit=False,  # manual commit for reliability
    )

    # Init Producer for DLQ
    producer = AIOKafkaProducer(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )

    await consumer.start()
    await producer.start()

    try:
        logger.info("Worker listening!")

        # Continuous loop: Wait for messages
        async for msg in consumer:
            # We create a NEW database session for every batch/message
            # to ensure fresh connections and transaction isolation
            async with AsyncSessionLocal() as session:
                # Inject partition/offset info for debugging
                payload = msg.value
                payload["partition"] = msg.partition
                payload["offset"] = msg.offset

                success = await process_message(session, payload, producer)

                if success:
                    # Commit offset only if proceed successfully
                    await consumer.commit()
                else:
                    # Log failure but no flow block
                    logger.warning(
                        "message_processing_failed",
                        partition=msg.partition,
                        offset=msg.offset,
                    )

    except Exception as e:
        logger.critical("Worker crashed", error=str(e))
    finally:
        await consumer.stop()
        await producer.stop()
        logger.info("Worker stopped")


if __name__ == "__main__":
    # Run the async loop
    try:
        asyncio.run(consume())
    except KeyboardInterrupt:
        logger.info("Worker interrupted by user")
