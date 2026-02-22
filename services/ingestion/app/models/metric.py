from datetime import datetime as dt

from app.core.database import Base
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, Float, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func


class Metric(Base):
    """Metric table for storing time-series data."""

    __tablename__ = "metrics"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    value = Column(Float, nullable=False)
    timestamp = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,  # Database sets timestamp if not provided
    )
    labels = Column(
        JSONB, nullable=False, server_default="{}"
    )  # JSONB: PostgreSQL's efficient JSON storage
    environment = Column(String, nullable=True)
    tenant_id = Column(String, nullable=False, index=True)
    # Composite index for efficient time-range queries
    # This will be crucial when we query "cpu_usage for the last hour"
    __table_args__ = (Index("idx_metrics_name_timestamp", "name", "timestamp"),)


class IngestionResponse(BaseModel):
    status: str
    message: str
    timestamp: dt
