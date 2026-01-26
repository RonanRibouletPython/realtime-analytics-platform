from contextlib import asynccontextmanager

import redis.asyncio as redis
import structlog
from app.api.metrics import router as metrics_router
from app.core.config import settings
from app.core.database import Base, engine, get_db
from app.core.logging import setup_logging
from app.core.redis_client import get_redis_client
from app.models.metric import Metric
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

    yield
    # Shutdown: Close DB connection
    logger.info("shutdown", msg="Closing Database Connection...")
    await engine.dispose()


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
async def redis_health_check(redis: redis.Redis = Depends(get_redis_client)):
    """Check the health of the Redis connection"""
    health_status = {
        "status": "healthy",
        "service": "ingestion",
        "environment": settings.ENV,
        "components": {"redis": "unknown"},
    }

    try:
        await redis.ping()
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

    return health_status


if __name__ == "__main__":
    import uvicorn

    # Hot reload enabled for development
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
