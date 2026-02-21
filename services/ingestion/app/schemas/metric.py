from datetime import datetime as dt
from datetime import timezone as tz
from typing import Dict

from pydantic import BaseModel, Field


class MetricBase(BaseModel):
    name: str = Field(..., description="Name of the metric (e.g., cpu_usage)")
    value: float = Field(..., description="Value of the metric")
    timestamp: dt = Field(default_factory=lambda: dt.now(tz.utc))
    environment: str | None = Field(
        default=None,
        description="Deployment environment (e.g., production, staging)",
    )
    labels: Dict[str, str] = Field(
        default_factory=dict, description="Metadata tags (e.g., host=server-1)"
    )


class MetricCreate(MetricBase):
    pass


class MetricResponse(MetricBase):
    id: int

    class Config:
        from_attributes = True
