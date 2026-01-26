import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.metric import Metric
from app.schemas.metric import MetricCreate, MetricResponse

router = APIRouter()
logger = structlog.get_logger()


@router.post(
    "/metrics", response_model=MetricResponse, status_code=status.HTTP_201_CREATED
)
async def ingest_metric(metric_in: MetricCreate, db: AsyncSession = Depends(get_db)):
    """
        Ingest a new metric data point.

        Example:
    ```json
        {
          "name": "cpu_usage",
          "value": 85.5,
          "labels": {"host": "server-01", "region": "us-east"}
        }
    ```
    """
    try:
        # Create new metric instance
        new_metric = Metric(
            name=metric_in.name,
            value=metric_in.value,
            timestamp=metric_in.timestamp,
            labels=metric_in.labels,
        )

        db.add(new_metric)
        await db.commit()
        await db.refresh(new_metric)

        logger.info(
            "metric_ingested",
            metric_id=new_metric.id,
            metric_name=new_metric.name,
            value=new_metric.value,
        )

        return new_metric

    except Exception as e:
        await db.rollback()
        logger.error("metric_ingestion_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to ingest metric",
        )


@router.get("/metrics", response_model=list[MetricResponse])
async def list_metrics(limit: int = 10, db: AsyncSession = Depends(get_db)):
    """
    List the latest metrics (for debugging/testing).

    Parameters:
    - limit: Number of metrics to return (default: 10, max: 100)
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
