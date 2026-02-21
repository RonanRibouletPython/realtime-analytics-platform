from contextlib import asynccontextmanager

import redis.asyncio as redis
import structlog
import uvicorn
from app.api.metrics import router as metrics_router
from app.core.config import settings
from app.core.database import Base, engine, get_db
from app.core.kafka import check_kafka_health, flush_producer
from app.core.logging import setup_logging
from app.core.redis_client import get_redis_client
from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Setup logging
    setup_logging()
    logger.info("startup", msg="Ingestion Service Starting...")

    # Create the DB tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("db_tables_creation", msg="database tables created")

    # confluent-kafka initializes the producer globally in kafka.py file
    yield

    # Shutdown: Close DB connection
    logger.info("shutdown", msg="Closing Database Connection...")
    await engine.dispose()

    # Shutdown: Flush Kafka messages
    # This ensures items in the buffer are sent before the container dies
    flush_producer()


app = FastAPI(
    title=settings.PROJECT_NAME,
    lifespan=lifespan,
    openapi_url=f"/{settings.API_V1}/openapi.json",
)

app.include_router(metrics_router, prefix=f"/{settings.API_V1}", tags=["metrics"])


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "status": "Root endpoint healthy",
        "message": "Enjoy your time with the API :)",
    }


@app.get("/health")
async def health_check():
    """Basic health check endpoint"""
    return {
        "status": "healthy",
        "service": "ingestion",
        "environment": settings.ENV,
    }


@app.get("/redis_health")
async def redis_health_check(
    # FIX 1: renamed from 'redis' to 'redis_client'
    # 'redis' was shadowing the `import redis.asyncio as redis` module binding.
    # Inside this function, the name 'redis' now correctly still refers to the module.
    redis_client: redis.Redis = Depends(get_redis_client),
):
    """Check the health of the Redis connection"""
    health_status = {
        "status": "healthy",
        "service": "ingestion",
        "environment": settings.ENV,
        "components": {"redis": "unknown"},
    }

    try:
        await redis_client.ping()
        health_status["components"]["redis"] = "up"
    except Exception as e:
        health_status["status"] = "degraded"
        health_status["components"]["redis"] = "down"
        logger.error("health_check_failed", component="redis", error=str(e))

    if health_status["status"] != "healthy":
        raise HTTPException(status_code=503, detail=health_status)

    return health_status


@app.get("/db_health")
async def db_health_check(
    db: AsyncSession = Depends(get_db),
):
    """Check the health of the Postrgres DB connection"""
    health_status = {
        "status": "healthy",
        "service": "ingestion",
        "environment": settings.ENV,
        "components": {
            "database": "unknown",
        },
    }

    try:
        await db.execute(text("SELECT 1"))
        health_status["components"]["database"] = "up"
    except Exception as e:
        health_status["status"] = "degraded"
        health_status["components"]["database"] = "down"
        logger.error("health_check_failed", component="database", error=str(e))

    # FIX 2: was missing entirely — db_health_check always returned 200
    # even when the database was down. Load balancers and k8s liveness probes
    # were getting a 200 "healthy" response during a DB outage.
    if health_status["status"] != "healthy":
        raise HTTPException(status_code=503, detail=health_status)

    return health_status


@app.get("/kafka_health")
async def kafka_health_check():
    """Check the health of the Kafka producer connection."""
    health_status = {
        "status": "healthy",
        "service": "ingestion",
        "environment": settings.ENV,
        "components": {"kafka": "unknown"},
    }

    try:
        # NEW: delegates to check_kafka_health() in kafka.py
        # We implement that function next — it will do a metadata fetch
        # with a short timeout, which is the standard Kafka health probe pattern.
        await check_kafka_health()
        health_status["components"]["kafka"] = "up"
    except Exception as e:
        health_status["status"] = "degraded"
        health_status["components"]["kafka"] = "down"
        logger.error("health_check_failed", component="kafka", error=str(e))

    if health_status["status"] != "healthy":
        raise HTTPException(status_code=503, detail=health_status)

    return health_status


if __name__ == "__main__":
    # Hot reload enabled for development
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
