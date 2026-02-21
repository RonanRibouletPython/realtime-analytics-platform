import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.kafka import SchemaVersion, send_metric
from app.models.metric import IngestionResponse, Metric
from app.schemas.metric import MetricCreate, MetricResponse

router = APIRouter()
logger = structlog.get_logger()


@router.post(
    "/metrics", response_model=IngestionResponse, status_code=status.HTTP_202_ACCEPTED
)
async def ingest_metric(metric_in: MetricCreate):
    """
    Step 2 of the project:
    Ingest a new metric data point and push to Kafka.
    """

    try:
        # Convert Pydantic model to dict (keeping datetime objects for the Avro serializer)
        payload = metric_in.model_dump()

        # Send data to Kafka using the confluent_kafka producer
        # Note: This puts the message in the local buffer. It is non-blocking.
        await send_metric(payload, version=SchemaVersion.V1)

        logger.info("metric_queued", metric_name=metric_in.name, value=metric_in.value)

        return {
            "status": "queued",
            "message": "Metric accepted for processing",
            "timestamp": metric_in.timestamp,
        }

    except ValueError as e:
        # FIX 1: catch ValueError from metric_to_dict separately.
        # A missing/invalid timestamp is a caller error (422), not a
        # server error (500). Returning 500 here would mask schema issues
        # and make your DLQ alerts fire for client-side mistakes.
        logger.warning("metric_validation_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    except Exception as e:
        logger.error("metric_ingestion_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to queue metric",
        )


@router.get("/metrics", response_model=list[MetricResponse])
async def list_metrics(limit: int = 10, db: AsyncSession = Depends(get_db)):
    """
    List the latest metrics from the database

    Parameters:
    - limit: Number of metrics to return (default: 10, max: 100)
    """

    # FIX 2: reject invalid limit explicitly instead of silently clamping.
    # Silent correction hides bugs in callers and violates the principle
    # of least surprise. A client sending limit=500 should know it's wrong.

    if limit < 1 or limit > 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="limit must be between 1 and 100",
        )

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
