from datetime import datetime as dt
from datetime import timezone as tz
from typing import Dict

from pydantic import BaseModel, ConfigDict, Field


class MetricBase(BaseModel):
    name: str = Field(..., description="Name of the metric (e.g., cpu_usage)")
    tenant_id: str | None = Field(default=None, description="Tenant ID")
    value: float = Field(..., description="Value of the metric")
    timestamp: dt = Field(default_factory=lambda: dt.now(tz.utc))
    environment: str | None = Field(
        default=None,
        description="Deployment environment (e.g., production, staging)",
    )
    labels: Dict[str, str] = Field(
        default_factory=dict, description="Metadata tags (e.g., host=server-1)"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "tenant_id": "tenant-1",
                "name": "cpu_usage",
                "value": 75.32,
                "timestamp": dt.now(tz.utc),
                "environment": "production",
                "labels": {
                    "host": "server-1",
                    "location": "rack-3",
                    "sensor_id": "s001",
                },
            },
        }
    )


class MetricCreate(MetricBase):
    pass


class MetricResponse(MetricBase):
    id: int

    class Config:
        from_attributes = True
