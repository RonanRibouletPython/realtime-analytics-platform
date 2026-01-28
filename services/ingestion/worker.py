import asyncio
import json
from datetime import datetime as dt

import structlog
from aiokafka import AIOKafkaConsumer
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.metric import Metric
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


async def process_message(session: AsyncSession, message_value: dict):
    """
    Process a single message from Kafka and save to DB.
    """

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
    except Exception as e:
        logger.error("processing_error", error=str(e), payload=message_value)
        await session.rollback()


async def consume():
    """
    Main consumer loop.
    """
    logger.info("Worker starting!", topic=settings.KAFKA_TOPIC_METRICS)

    # Initialize the Consumer
    consumer = AIOKafkaConsumer(
        settings.KAFKA_TOPIC_METRICS,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id="metrics_worker_group",
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        auto_offset_reset="earliest",  # Start from beginning if no history exists
    )

    await consumer.start()

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

                await process_message(session, payload)

    except Exception as e:
        logger.critical("Worker crashed :(", error=str(e))
    finally:
        await consumer.stop()
        logger.info("Worker stopped")


if __name__ == "__main__":
    # Run the async loop
    try:
        asyncio.run(consume())
    except KeyboardInterrupt:
        pass
