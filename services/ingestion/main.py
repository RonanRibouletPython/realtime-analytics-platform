from contextlib import asynccontextmanager

import structlog
from app.core.config import settings
from app.core.database import engine
from app.core.logging import setup_logging
from fastapi import FastAPI

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Setup logging
    setup_logging()
    logger.info("startup", msg="Ingestion Service Starting...")
    yield
    # Shutdown: Close DB connection
    logger.info("shutdown", msg="Closing Database Connection...")
    await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    lifespan=lifespan,
    openapi_url=f"/{settings.API_V1}/openapi.json",
)


@app.get("/health")
async def health_check():
    """Basic health check endpoint"""
    return {
        "status": "healthy",
        "service": "ingestion",
        "environment": settings.ENV,
    }


if __name__ == "__main__":
    import uvicorn

    # Hot reload enabled for development
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
