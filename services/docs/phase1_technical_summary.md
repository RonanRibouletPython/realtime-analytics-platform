# Phase 1: Foundation - Complete Technical Summary

**Project:** Real-Time Analytics & Monitoring Platform  
**Phase:** 1 of 7 - Foundation  
**Date Completed:** January 26, 2025  
**Status:** COMPLETED  
**Time Invested:** ~8 hours

---

## 📋 Table of Contents

1. [What We Built](#what-we-built)
2. [Technical Stack Deep Dive](#technical-stack-deep-dive)
3. [Core Concepts Learned](#core-concepts-learned)
4. [Architecture Patterns](#architecture-patterns)
5. [Code Examples & Explanations](#code-examples--explanations)
6. [Real-World Applications](#real-world-applications)
7. [Problems Solved](#problems-solved)
8. [Testing & Validation](#testing--validation)
9. [Performance Considerations](#performance-considerations)
10. [Security & Best Practices](#security--best-practices)
11. [What's Next (Phase 2)](#whats-next-phase-2)

---

## 🎯 What We Built

### High-Level Overview

A **production-grade metrics ingestion service** that:
- Accepts HTTP POST requests with metric data
- Validates incoming data with type safety
- Stores time-series data in PostgreSQL
- Provides health monitoring endpoints
- Integrates with real-world APIs (CoinGecko)
- Runs in a reproducible DevContainer environment

### System Architecture

```
┌─────────────────────────────────────────────┐
│         External Sources                     │
│  (CoinGecko API, Future: Weather, etc.)     │
└────────────────┬────────────────────────────┘
                 │ HTTP Requests
                 ▼
┌─────────────────────────────────────────────┐
│      FastAPI Ingestion Service              │
│  ┌────────────────────────────────────┐     │
│  │  POST /api/v1/metrics              │     │
│  │  - Pydantic Validation             │     │
│  │  - Type Checking                   │     │
│  │  - Request Logging                 │     │
│  └────────────┬───────────────────────┘     │
│               │                              │
│  ┌────────────▼───────────────────────┐     │
│  │  SQLAlchemy ORM                    │     │
│  │  - Async Session Management        │     │
│  │  - Connection Pooling              │     │
│  └────────────┬───────────────────────┘     │
└───────────────┼──────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────┐
│         PostgreSQL 16                        │
│  ┌────────────────────────────────────┐     │
│  │  metrics Table                     │     │
│  │  - id (PK, Auto-increment)         │     │
│  │  - name (String, Indexed)          │     │
│  │  - value (Float)                   │     │
│  │  - timestamp (DateTime, Indexed)   │     │
│  │  - labels (JSONB)                  │     │
│  │                                    │     │
│  │  Indexes:                          │     │
│  │  - idx_metrics_name_timestamp      │     │
│  └────────────────────────────────────┘     │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│         Redis 7 (Ready for Phase 2)          │
│  - Caching                                   │
│  - Rate Limiting                             │
│  - Session Storage                           │
└─────────────────────────────────────────────┘
```

### API Endpoints Created

| Method | Endpoint | Purpose | Response |
|--------|----------|---------|----------|
| GET | `/` | Root endpoint | Service info |
| GET | `/health` | Basic health check | Status |
| GET | `/db_health` | PostgreSQL health | DB connection status |
| GET | `/redis_health` | Redis health | Redis connection status |
| POST | `/api/v1/metrics` | Ingest metric | Created metric with ID |
| GET | `/api/v1/metrics` | List metrics | Latest metrics (limit 10) |
| GET | `/docs` | API documentation | Swagger UI |

---

## Technical Stack Deep Dive

### 1. **Python 3.13**

**Why we chose it:**
- Latest stable version with performance improvements
- Better async support
- Improved error messages
- Type hints enhancements

**What we learned:**
- Installing Python from source on Debian
- Virtual environment management with `uv`
- Async/await syntax and event loops
- Type hints with Pydantic

**Key Syntax:**
```python
# Async function definition
async def fetch_data() -> dict:
    return await some_async_operation()

# Type hints
from typing import Dict, List, Optional

def process_metrics(
    metrics: List[dict], 
    labels: Optional[Dict[str, str]] = None
) -> int:
    pass

# Async context managers
async with AsyncSessionLocal() as session:
    result = await session.execute(query)
```

---

### 2. **FastAPI**

**Why FastAPI:**
- Automatic API documentation (Swagger/OpenAPI)
- Built-in data validation with Pydantic
- High performance (ASGI-based)
- Async support out of the box
- Dependency injection system

**What we learned:**

#### a) Route Decorators
```python
from fastapi import APIRouter, status

router = APIRouter()

@router.post("/metrics", status_code=status.HTTP_201_CREATED)
async def create_metric(metric: MetricCreate):
    pass
```

#### b) Dependency Injection
```python
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

@router.post("/metrics")
async def ingest_metric(
    metric_in: MetricCreate,
    db: AsyncSession = Depends(get_db)  # Automatically injected
):
    # db is provided by FastAPI via get_db dependency
    pass
```

**How it works:**
1. FastAPI sees `Depends(get_db)`
2. Calls `get_db()` function
3. Injects the result into `db` parameter
4. Automatically cleans up after request

#### c) Automatic Validation
```python
class MetricCreate(BaseModel):
    name: str
    value: float
    
@router.post("/metrics")
async def ingest(metric: MetricCreate):
    # If request body is invalid, FastAPI automatically:
    # 1. Returns 422 Unprocessable Entity
    # 2. Shows which field failed validation
    # 3. Never reaches this code
    pass
```

#### d) Lifespan Management
```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # STARTUP
    setup_logging()
    await create_database_tables()
    print("App started!")
    
    yield  # App runs here
    
    # SHUTDOWN
    await close_database_connections()
    print("App stopped!")

app = FastAPI(lifespan=lifespan)
```

---

### 3. **PostgreSQL 16 + SQLAlchemy 2.0**

**Why PostgreSQL:**
- JSONB support (flexible schema)
- Advanced indexing
- ACID compliance
- Industry standard

**What we learned:**

#### a) JSONB for Flexible Data
```python
# Table definition
labels = Column(JSONB, nullable=False, server_default='{}')

# Store any structure
{
  "host": "server-01",
  "region": "us-east",
  "custom_field": "any_value"
}

# Query JSONB efficiently
SELECT * FROM metrics 
WHERE labels->>'coin' = 'bitcoin';  # -> extracts as text

SELECT * FROM metrics 
WHERE labels @> '{"region": "us-east"}';  # Contains operator
```

**Why JSONB is powerful:**
- No schema migrations for new labels
- Indexed for fast queries
- JSON operators in SQL
- Perfect for analytics/tagging

#### b) Async SQLAlchemy
```python
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker
)

# Create engine
engine = create_async_engine(
    "postgresql+asyncpg://user:pass@localhost/db",
    pool_size=10,        # Connection pool
    max_overflow=20,     # Extra connections when pool full
    pool_pre_ping=True   # Verify connection before use
)

# Session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

# Usage
async with AsyncSessionLocal() as session:
    result = await session.execute(select(Metric))
    metrics = result.scalars().all()
```

#### c) Database Models
```python
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import Column, Integer, String, Float

class Base(DeclarativeBase):
    pass

class Metric(Base):
    __tablename__ = "metrics"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    value = Column(Float, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    labels = Column(JSONB, server_default='{}')
    
    # Composite index for fast time-range queries
    __table_args__ = (
        Index('idx_metrics_name_timestamp', 'name', 'timestamp'),
    )
```

**Why this index matters:**
```sql
-- WITHOUT INDEX: Full table scan (slow!)
SELECT * FROM metrics 
WHERE name = 'cpu_usage' 
  AND timestamp BETWEEN '2025-01-26 10:00' AND '2025-01-26 11:00';

-- WITH INDEX: Uses idx_metrics_name_timestamp (fast!)
-- PostgreSQL can quickly find all 'cpu_usage' rows, 
-- then scan only that time range
```

#### d) Async Queries
```python
# INSERT
new_metric = Metric(name="cpu_usage", value=85.5)
session.add(new_metric)
await session.commit()
await session.refresh(new_metric)  # Get auto-generated ID

# SELECT with filtering
result = await session.execute(
    select(Metric)
    .where(Metric.name == "cpu_usage")
    .where(Metric.timestamp > some_date)
    .order_by(Metric.timestamp.desc())
    .limit(100)
)
metrics = result.scalars().all()

# AGGREGATION
result = await session.execute(
    select(
        Metric.name,
        func.count(Metric.id).label('count'),
        func.avg(Metric.value).label('avg_value')
    )
    .group_by(Metric.name)
)
```

---

### 4. **Pydantic**

**Why Pydantic:**
- Runtime data validation
- Type safety
- Auto-generated JSON schemas
- Works seamlessly with FastAPI

**What we learned:**

#### a) Schema Definition
```python
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Dict

class MetricBase(BaseModel):
    name: str = Field(..., description="Metric name")
    value: float = Field(..., description="Metric value")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    labels: Dict[str, str] = Field(default_factory=dict)

class MetricCreate(MetricBase):
    """Schema for creating a metric (input)"""
    pass

class MetricResponse(MetricBase):
    """Schema for returning a metric (output)"""
    id: int
    
    class Config:
        from_attributes = True  # Allow ORM models
```

#### b) Validation in Action
```python
# Valid request
{
  "name": "cpu_usage",
  "value": 85.5,
  "labels": {"host": "server-01"}
}
✅ Creates MetricCreate object

# Invalid request (value is string, not float)
{
  "name": "cpu_usage",
  "value": "hello",  # ❌ Should be float
  "labels": {"host": "server-01"}
}
❌ FastAPI automatically returns:
{
  "detail": [
    {
      "loc": ["body", "value"],
      "msg": "value is not a valid float",
      "type": "type_error.float"
    }
  ]
}
```

#### c) Why Separate Schemas
```python
# INPUT (MetricCreate)
# - User doesn't provide ID (auto-generated)
# - May omit timestamp (defaults to now)

# OUTPUT (MetricResponse)
# - Always includes ID
# - Always includes actual timestamp from DB
# - Prevents exposing internal fields

# Example:
@router.post("/metrics", response_model=MetricResponse)
async def create(metric: MetricCreate, db: AsyncSession = Depends(get_db)):
    # metric: MetricCreate (no ID)
    db_metric = Metric(**metric.model_dump())
    db.add(db_metric)
    await db.commit()
    await db.refresh(db_metric)
    # return: MetricResponse (includes ID)
    return db_metric
```

---

### 5. **Pydantic Settings**

**Configuration Management Done Right**

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Ingestion Service"
    ENV: Literal["development", "production"] = "development"
    
    POSTGRES_USER: str = "analytics"
    POSTGRES_PASSWORD: str = "analytics"
    POSTGRES_SERVER: str = "localhost"
    
    @property
    def DB_URL(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}/analytics"
    
    model_config = SettingsConfigDict(
        env_file=".env",      # Load from .env file
        case_sensitive=True,   # POSTGRES_USER != postgres_user
        extra="ignore"         # Ignore unknown env vars
    )

settings = Settings()  # Loads from environment automatically
```

**How it works:**
1. Checks environment variables first
2. Falls back to `.env` file
3. Uses default values if not found
4. Validates types automatically

**Usage:**
```python
# Development: uses defaults
settings.ENV  # "development"

# Production: set environment variables
# export ENV=production
# export POSTGRES_SERVER=prod-db.company.com
settings.ENV  # "production"
settings.DB_URL  # Uses prod database
```

---

### 6. **Structlog (Structured Logging)**

**Why Structured Logging:**
- Machine-parseable logs (JSON)
- Easy to search/filter
- Contextual information
- Different formats for dev/prod

**What we learned:**

```python
import structlog

logger = structlog.get_logger()

# Development (console, pretty colors)
logger.info("metric_ingested", metric_name="cpu_usage", value=85.5)
# Output: 2025-01-26 10:00:00 [info] metric_ingested metric_name='cpu_usage' value=85.5

# Production (JSON, machine-parseable)
logger.info("metric_ingested", metric_name="cpu_usage", value=85.5)
# Output: {"event":"metric_ingested","level":"info","timestamp":"2025-01-26T10:00:00Z","metric_name":"cpu_usage","value":85.5}
```

**Why this matters:**
```bash
# In production, you can easily search logs:
# Find all errors related to database
grep '"component":"database"' logs.json | grep '"level":"error"'

# Find all metrics ingested for bitcoin
grep '"coin":"bitcoin"' logs.json
```

---

### 7. **Docker DevContainers**

**What we learned:**

#### a) Dockerfile Structure
```dockerfile
FROM debian:bookworm-slim

# Install dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    postgresql-client

# Compile Python 3.13 from source
RUN wget https://www.python.org/ftp/python/3.13.1/Python-3.13.1.tgz \
    && tar -xzf Python-3.13.1.tgz \
    && cd Python-3.13.1 \
    && ./configure --enable-optimizations \
    && make -j$(nproc) \
    && make altinstall

# Create non-root user
RUN useradd -m -s /bin/bash vscode
USER vscode
```

#### b) Docker Compose Multi-Service
```yaml
services:
  devcontainer:
    build: .
    volumes:
      - ..:/workspace
    network_mode: service:db  # Share db's network
    depends_on:
      db:
        condition: service_healthy
  
  db:
    image: postgres:16-alpine
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "analytics"]
      interval: 10s
```

**Why network_mode: service:db:**
- devcontainer can access `localhost:5432` (PostgreSQL)
- devcontainer can access `localhost:6379` (Redis)
- No need for complex networking

---

### 8. **uv (Package Manager)**

**Why uv over pip:**
- 10-100x faster
- Better dependency resolution
- Lockfile support
- Works with any Python version

**Commands we used:**
```bash
# Initialize project
uv init --name ingestion-service

# Add dependencies
uv add fastapi uvicorn sqlalchemy asyncpg

# Add dev dependencies
uv add --dev pytest pytest-asyncio ruff mypy

# Install everything
uv sync

# Run commands
uv run uvicorn app.main:app --reload
uv run pytest
```

---

## 🧠 Core Concepts Learned

### 1. **Async Programming**

**The Problem:**
```python
# SYNCHRONOUS (Blocking)
def fetch_data():
    response = requests.get("https://api.example.com")  # Waits here
    return response.json()

# If this takes 2 seconds, your server is BLOCKED for 2 seconds
# Can't handle other requests during this time
```

**The Solution:**
```python
# ASYNCHRONOUS (Non-blocking)
async def fetch_data():
    async with httpx.AsyncClient() as client:
        response = await client.get("https://api.example.com")
        # While waiting, server can handle OTHER requests
        return response.json()
```

**Key Concepts:**

#### a) Event Loop
```python
# The event loop manages all async operations
import asyncio

async def task1():
    print("Task 1 start")
    await asyncio.sleep(1)  # Simulate I/O
    print("Task 1 done")

async def task2():
    print("Task 2 start")
    await asyncio.sleep(1)
    print("Task 2 done")

# Run concurrently
asyncio.run(asyncio.gather(task1(), task2()))

# Output:
# Task 1 start
# Task 2 start
# (both sleep at the same time)
# Task 1 done
# Task 2 done
# Total time: ~1 second, not 2!
```

#### b) Async Context Managers
```python
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session  # Give session to caller
        finally:
            await session.close()  # Always cleanup
```

#### c) When to use async
**Use async for:**
- Database queries
- HTTP requests
- File I/O
- Network operations

**Don't use async for:**
- CPU-intensive tasks (use multiprocessing)
- Quick operations (dict lookup, math)

---

### 2. **Dependency Injection**

**Without DI (Bad):**
```python
@router.post("/metrics")
async def create_metric(metric: MetricCreate):
    # Create DB connection every time
    engine = create_async_engine(DB_URL)
    session = AsyncSession(engine)
    
    try:
        session.add(Metric(**metric.dict()))
        await session.commit()
    finally:
        await session.close()
        await engine.dispose()
    # Repeating this in every endpoint!
```

**With DI (Good):**
```python
# Define once
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

# Use everywhere
@router.post("/metrics")
async def create_metric(
    metric: MetricCreate,
    db: AsyncSession = Depends(get_db)  # ✨ Magic!
):
    db.add(Metric(**metric.dict()))
    await db.commit()
    # FastAPI handles cleanup automatically
```

**Benefits:**
- DRY (Don't Repeat Yourself)
- Easy to test (mock dependencies)
- Automatic cleanup
- Centralized configuration

---

### 3. **Database Indexing**

**What is an index?**
Think of it like a book's index:
- Without index: Read entire book to find "Python" mentions
- With index: Look up "Python" in index → jump to pages 45, 78, 102

**In databases:**
```sql
-- WITHOUT INDEX
SELECT * FROM metrics WHERE name = 'cpu_usage';
-- Scans ALL rows (slow if millions of rows)

-- WITH INDEX
CREATE INDEX idx_metrics_name ON metrics(name);
SELECT * FROM metrics WHERE name = 'cpu_usage';
-- Uses index to jump directly to cpu_usage rows (fast!)
```

**Our composite index:**
```python
Index('idx_metrics_name_timestamp', 'name', 'timestamp')
```

**Why composite?**
```sql
-- This query uses BOTH fields
SELECT * FROM metrics 
WHERE name = 'cpu_usage' 
  AND timestamp > '2025-01-26 10:00:00';

-- With composite index:
-- 1. Jump to 'cpu_usage' rows
-- 2. Within those, jump to rows after 10:00
-- = Very fast!
```

---

### 4. **Type Safety**

**Why types matter:**
```python
# WITHOUT type hints
def process_metric(metric):
    # What is metric? A dict? An object? 
    # Does it have .name or ["name"]?
    # No way to know without running code!
    return metric.value * 2

# WITH type hints
def process_metric(metric: Metric) -> float:
    # IDE knows: metric is a Metric object
    # Autocomplete works: metric.name, metric.value
    # mypy catches errors BEFORE running
    return metric.value * 2
```

**Pydantic adds runtime validation:**
```python
class MetricCreate(BaseModel):
    name: str
    value: float

# This works
MetricCreate(name="cpu", value=85.5)  ✅

# This fails at runtime (before hitting database!)
MetricCreate(name="cpu", value="hello")  ❌
# ValidationError: value is not a valid float
```

---

### 5. **Time-Series Data Patterns**

**What makes data "time-series"?**
- Every data point has a timestamp
- Usually append-only (no updates)
- Queries often involve time ranges
- Need aggregations (avg, max, percentiles)

**Optimization techniques we used:**

#### a) Indexed Timestamps
```python
timestamp = Column(DateTime(timezone=True), index=True)
```

#### b) Partitioning (Future - Phase 3)
```sql
-- Split table by time range
CREATE TABLE metrics_2025_01 PARTITION OF metrics
FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');

-- Old data goes to separate partition
-- Queries only scan relevant partitions
```

#### c) Continuous Aggregations (Future - Phase 3)
```sql
-- Pre-calculate hourly averages
CREATE MATERIALIZED VIEW metrics_hourly AS
SELECT 
    date_trunc('hour', timestamp) as hour,
    name,
    AVG(value) as avg_value
FROM metrics
GROUP BY hour, name;

-- Refresh periodically
REFRESH MATERIALIZED VIEW metrics_hourly;
```

---

## 🏗️ Architecture Patterns

### 1. **Layered Architecture**

```
┌─────────────────────────────────────┐
│      Presentation Layer             │  (FastAPI routes)
│  - HTTP endpoints                   │
│  - Request validation               │
│  - Response formatting              │
└───────────────┬─────────────────────┘
                │
┌───────────────▼─────────────────────┐
│      Business Logic Layer           │  (Service functions)
│  - Domain logic                     │
│  - Data transformation              │
│  - Business rules                   │
└───────────────┬─────────────────────┘
                │
┌───────────────▼─────────────────────┐
│      Data Access Layer              │  (SQLAlchemy)
│  - Database queries                 │
│  - ORM models                       │
│  - Connection management            │
└─────────────────────────────────────┘
```

**Why this matters:**
- Change database? Only update Data Access Layer
- Add validation? Only update Business Logic
- Different API version? Add new routes in Presentation

---

### 2. **Repository Pattern (Implicit)**

```python
# models/metric.py - Data structure
class Metric(Base):
    __tablename__ = "metrics"
    # ...

# schemas/metric.py - API contract
class MetricCreate(BaseModel):
    name: str
    value: float

# api/metrics.py - Endpoints
@router.post("/metrics")
async def create_metric(
    metric: MetricCreate,  # API schema
    db: AsyncSession = Depends(get_db)
):
    db_metric = Metric(**metric.dict())  # DB model
    db.add(db_metric)
    await db.commit()
    return db_metric
```

---

### 3. **Health Check Pattern**

```python
# Liveness: Is the service running?
@app.get("/health")
async def health():
    return {"status": "healthy"}

# Readiness: Can it handle requests?
@app.get("/ready")
async def ready(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ready"}
    except:
        raise HTTPException(status_code=503, detail="Not ready")
```

**Used by:**
- Kubernetes: Checks `/ready` before sending traffic
- Load balancers: Remove unhealthy instances
- Monitoring: Alert if `/health` fails

---

## Code Examples & Explanations

### Complete Request Flow

Let's trace a metric from HTTP request to database:

**1. Client sends request:**
```bash
POST http://localhost:8000/api/v1/metrics
Content-Type: application/json

{
  "name": "cpu_usage",
  "value": 85.5,
  "labels": {"host": "server-01"}
}
```

**2. FastAPI receives request:**
```python
@router.post("/metrics", response_model=MetricResponse)
async def ingest_metric(
    metric_in: MetricCreate,  # Pydantic validates here
    db: AsyncSession = Depends(get_db)  # FastAPI injects session
):
```

**3. Pydantic validation:**
```python
# FastAPI automatically:
# - Parses JSON
# - Validates types (value is float? ✓)
# - Creates MetricCreate object
# - If invalid, returns 422 error

metric_in = MetricCreate(
    name="cpu_usage",
    value=85.5,
    labels={"host": "server-01"}
)
```

**4. Create database model:**
```python
    new_metric = Metric(
        name=metric_in.name,
        value=metric_in.value,
        timestamp=metric_in.timestamp,
        labels=metric_in.labels
    )
```

**5. Save to database:**
```python
    db.add(new_metric)  # Add to session
    await db.commit()   # Execute INSERT
    await db.refresh(new_metric)  # Get auto-generated ID
```

**6. Return response:**
```python
    return new_metric  # Pydantic converts to MetricResponse
    # {
    #   "id": 1,
    #   "name": "cpu_usage",
    #   "value": 85.5,
    #   "timestamp": "2025-01-26T10:00:00Z",
    #   "labels": {"host": "server-01"}
    # }
```

---

## Real-World Applications

### What We Can Build With This

**Current Capability:**
```python
# E-commerce site tracking
await track_metric("order_total", 99.99, {
    "country": "US",
    "payment": "stripe",
    "category": "electronics"
})

# Server monitoring
await track_metric("cpu_usage", 85.5, {
    "host": "server-01",
    "datacenter": "aws-east"
})

# User analytics
await track_metric("page_load_time", 145.2, {
    "page": "/checkout",
    "browser": "chrome"
})
```

**Query Examples:**
```sql
-- Revenue by country
SELECT 
    labels->>'country' as country,
    SUM(value) as total_revenue
FROM metrics 
WHERE name = 'order_total'
GROUP BY country;

-- Average CPU by datacenter
SELECT 
    labels->>'datacenter' as dc,
    AVG(value) as avg_cpu
FROM metrics 
WHERE name = 'cpu_usage'
GROUP BY dc;

-- Page performance
SELECT 
    labels->>'page' as page,
    percentile_cont(0.95) WITHIN GROUP (ORDER BY value) as p95_load_time
FROM metrics 
WHERE name = 'page_load_time'
GROUP BY page;
```

---

## Problems Solved

### Problem 1: DevContainer File Not Found

**Error:**
```
CreateFile docker-compose.yml: The system cannot find the file specified
```

**Root Cause:** File named `docker-compose.yaml` instead of `docker-compose.yml`

**Solution:** 
```bash
mv docker-compose.yaml docker-compose.yml
```

**Learning:** Pay attention to exact file extensions in configuration

---

### Problem 2: Connection Failed

**Error:**
```
Error sending metric: All connection attempts failed
```

**Root Cause:** FastAPI server wasn't running

**Solution:** Run server in separate terminal:
```bash
uv run uvicorn app.main:app --reload
```

**Learning:** Multi-service systems need orchestration. Check dependencies are running.

---

### Problem 3: Import Errors

**Error:**
```python
ModuleNotFoundError: No module named 'app'
```

**Root Cause:** Missing `__init__.py` files

**Solution:**
```bash
touch app/__init__.py
touch app/api/__init__.py
touch app/core/__init__.py
```

**Learning:** Python packages require `__init__.py` in each directory

---
    