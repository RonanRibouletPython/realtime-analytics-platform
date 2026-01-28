import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.kafka import get_kafka_producer
from app.models.metric import IngestionResponse, Metric
from app.schemas.metric import MetricCreate, MetricResponse

router = APIRouter()
logger = structlog.get_logger()


@router.post(
    "/metrics", response_model=IngestionResponse, status_code=status.HTTP_202_ACCEPTED
)
async def ingest_metric(metric_in: MetricCreate, db: AsyncSession = Depends(get_db)):
    """
    Step 2 of the project:

    Ingest a new metric data point and push to Kafka.

    NOTE: This is asynchronous. Data is queued but not yet persisted to DB.

    """

    # Create Kafka producer instance
    producer = await get_kafka_producer()

    try:
        # Send data to Kafka
        # The serializer will handle the JSON conversion
        await producer.send_and_wait(
            topic=settings.KAFKA_TOPIC_METRICS, value=metric_in.model_dump(mode="json")
        )
        logger.info("metric_queued", metric_name=metric_in.name, value=metric_in.value)

        # We return a status receipt and not the full DB object
        return {
            "status": "queued",
            "message": "Metric accepted for processing",
            "timestamp": metric_in.timestamp,
        }

    except Exception as e:
        logger.error("metric_ingestion_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details="Failed to queue metric",
        )


@router.get("/metrics", response_model=list[MetricResponse])
async def list_metrics(limit: int = 10, db: AsyncSession = Depends(get_db)):
    """
    List the latest metrics from the database

    Parameters:
    - limit: Number of metrics to return (default: 10, max: 100)

    NOTE: Until we build the Consumer Worker (next step),
    metrics sent to POST /metrics will NOT appear here yet.
    """
    if limit > 100:
        limit = 100

    try:
        result = await db.execute(
            select(Metric).order_by(Metric.timestamp.desc()).limit(limit)
        )
        metrics = result.scalars().all()

        return metrics

    except Exception as e:
        logger.error("metrics_list_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve metrics",
        )
