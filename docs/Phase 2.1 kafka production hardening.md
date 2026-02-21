# Phase 2.1 — Kafka Integration: Production Hardening

**Project:** Real-Time Analytics & Monitoring Platform  
**Phase:** 2.1 — Kafka Producer/Consumer Production Readiness  
**Status:** Complete  
**Stack:** Python 3.13, FastAPI, confluent-kafka, Avro, Schema Registry, Prometheus, TimescaleDB, Redis, Docker Compose

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Changes by File](#changes-by-file)
   - [kafka.py](#kafkapy)
   - [worker.py](#workerpy)
   - [dlq.py](#dlqpy)
   - [metrics_tracker.py](#metrics_trackerpy)
   - [main.py](#mainpy)
   - [app/api/metrics.py](#appapimetricspy)
   - [Avro Schemas](#avro-schemas)
   - [docker-compose.yml](#docker-composeyml)
4. [ADR-001: Avro + Schema Registry over Plain JSON](#adr-001-avro--schema-registry-over-plain-json)
5. [ADR-002: Delivery Guarantee — At-Least-Once](#adr-002-delivery-guarantee--at-least-once)
6. [ADR-003: Schema Evolution Strategy](#adr-003-schema-evolution-strategy)
7. [Observability Reference](#observability-reference)
8. [Known Limitations & Future Work](#known-limitations--future-work)

---

## Overview

Phase 2.1 hardened the basic end-to-end Kafka data flow (FastAPI → Kafka → Consumer → TimescaleDB) into a production-grade pipeline. The work covered four pillars:

| Pillar | What Changed |
|---|---|
| **Schema Governance** | Avro serialization with Schema Registry, multi-version producer, backward-compatible v2 schema |
| **Failure Resilience** | Poison pill detection, DLQ routing with forensics envelope, DLQ circuit breaker |
| **Observability** | Prometheus metrics server on `:8001`, three instrumented metrics, Prometheus container in docker-compose |
| **Correctness Bugs** | Four runtime bugs fixed across `main.py`, `kafka.py`, `worker.py`, and `dlq.py` |

---

## Architecture

```
┌───────────────────────────────────────────────────────────────────────┐
│                          PRODUCER SIDE                                │
│                                                                       │
│  POST /api/v1/metrics                                                 │
│       │                                                               │
│       ▼                                                               │
│  FastAPI Route (metrics.py)                                           │
│       │                                                               │
│       ▼                                                               │
│  send_metric(payload, version=SchemaVersion.V2)                       │
│       │                                                               │
│       ▼                                                               │
│  AvroSerializer ──► Schema Registry (HTTP, cached)                   │
│       │             validates & registers schema on first produce     │
│       ▼                                                               │
│  SerializingProducer ──► Kafka Topic: metrics.raw                    │
│  (run_in_executor — non-blocking)                                     │
└───────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────────────────┐
│                          CONSUMER SIDE                                │
│                                                                       │
│  Kafka Topic: metrics.raw                                             │
│       │                                                               │
│       ▼                                                               │
│  DeserializingConsumer (confluent-kafka)                              │
│  poll() via run_in_executor — non-blocking                            │
│       │                                                               │
│       ├── Deserialization OK                                          │
│       │       │                                                       │
│       │       ▼                                                       │
│       │   process_message()                                           │
│       │       │                                                       │
│       │       ├── SUCCESS ──► TimescaleDB write ──► commit offset    │
│       │       │                                                       │
│       │       └── ValueError (permanent) ──► DLQ ──► commit offset  │
│       │                                                               │
│       │       └── Exception (transient) ──► no commit (retry)       │
│       │                                                               │
│       └── Deserialization FAIL (poison pill)                         │
│               │                                                       │
│               ▼                                                       │
│           send_to_dlq() ──► metrics.dlq (forensics envelope)        │
│               │                                                       │
│               ▼                                                       │
│           commit offset (skip the poison pill)                        │
│                                                                       │
│  Prometheus metrics server on :8001/metrics                          │
└───────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────────────────┐
│                        OBSERVABILITY                                  │
│                                                                       │
│  Prometheus (localhost:9090) ──► scrapes :8001/metrics every 15s    │
│                                                                       │
│  Metrics:                                                             │
│    kafka_messages_processed_total{status}                            │
│    kafka_message_processing_duration_seconds (histogram)             │
│    kafka_dlq_messages_total{reason}                                  │
└───────────────────────────────────────────────────────────────────────┘
```

---

## Changes by File

### `kafka.py`

#### Bug Fixes

**BUG 1 — `send_metric` blocked the event loop**

`producer.produce()` and `producer.poll()` are synchronous C-extension calls. Calling them directly inside an `async` FastAPI route froze the entire event loop for the duration of the call — every concurrent request stalled.

```python
# BEFORE — blocks event loop on every metric POST
def send_metric(metric: dict) -> None:
    producer.produce(topic=..., value=metric)
    producer.poll(0)

# AFTER — offloads to thread pool, event loop stays free
async def send_metric(metric: dict, version: SchemaVersion = SchemaVersion.V2) -> None:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        lambda: (producer.produce(...), producer.poll(0)),
    )
```

**BUG 2 — `metric_to_dict` silently crashed on missing timestamp**

`metric.get("timestamp")` returns `None` if the field is absent. Chaining `.astimezone()` on `None` raised `AttributeError` deep inside the Avro serializer — no useful context for the caller.

```python
# BEFORE — AttributeError with no context
"timestamp": int(metric.get("timestamp").astimezone(tz.utc).timestamp() * 1000)

# AFTER — explicit guard, clean ValueError surfaces to the route
timestamp = metric.get("timestamp")
if timestamp is None:
    raise ValueError("metric 'timestamp' field is required and cannot be None")
```

#### New Features

**Multi-Version Schema Producer**

Two `AvroSerializer` instances share one `SerializingProducer`. The caller selects the schema version via a `SchemaVersion` enum — prevents typos and makes version selection explicit at every call site.

```python
class SchemaVersion(str, Enum):
    V1 = "v1"
    V2 = "v2"

_SERIALIZERS: dict[SchemaVersion, AvroSerializer] = {
    SchemaVersion.V1: _serializer_v1,
    SchemaVersion.V2: _serializer_v2,
}
```

One producer is intentional — `SerializingProducer` holds a broker connection and an internal message buffer. Two producers would mean two connections, two buffers, and two `flush()` calls on shutdown.

**Kafka Health Probe**

`list_topics(timeout=3.0)` does a real round-trip to the broker. Exposed via `/kafka_health` in `main.py`. Runs in executor — `list_topics()` is also a blocking call.

```python
async def check_kafka_health() -> None:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, lambda: producer.list_topics(timeout=3.0))
```

---

### `worker.py`

#### Bug Fixes

**BUG 1 — `send_to_dlq` called without `await`**

`send_to_dlq` is a coroutine. Calling it without `await` creates a coroutine object and discards it silently — Python raises no error. The DLQ never received a single message.

```python
# BEFORE — DLQ silently never called
send_to_dlq(payload, str(e))

# AFTER — correctly awaited
await send_to_dlq(msg, error=str(e), reason="ValueError")
```

**BUG 2 — `consumer.poll(1.0)` blocked the event loop**

`poll()` with a 1-second timeout froze the event loop completely for 1 second per cycle. No DB writes, no other coroutines, nothing could run during that window.

```python
# BEFORE — freezes event loop for 1 second
msg = consumer.poll(1.0)

# AFTER — offloads to thread, event loop stays free
msg = await loop.run_in_executor(None, consumer.poll, 1.0)
```

#### Design Changes

**Full `Message` object passed through the pipeline**

The worker now passes the raw `confluent_kafka.Message` object to `process_message()` and `send_to_dlq()` instead of just `msg.value()`. This gives the DLQ access to topic, partition, offset, key, and raw bytes — all required for the forensics envelope.

**Explicit failure classification**

| Exception Type | Classification | Action |
|---|---|---|
| `ValueError` | Permanent | DLQ → commit offset |
| `Exception` (other) | Transient | No commit → Kafka redelivers |

Transient failures do not commit the offset — Kafka will redeliver on the next poll after a reconnect. Permanent failures commit after DLQ routing to prevent infinite reprocessing of a message that can never succeed.

---

### `dlq.py`

#### Design Changes

**Forensics Envelope**

The DLQ payload now contains everything needed to debug and replay a failed message:

```python
dlq_payload = {
    "dlq_metadata": {
        "routed_at_utc": "...",   # when it was routed
        "reason": "ValueError",   # machine-readable reason (Prometheus label)
        "error": "...",           # human-readable description
    },
    "source": {
        "topic": "metrics.raw",
        "partition": 0,
        "offset": 4821,           # exact position in the log — replayable
        "timestamp_ms": 1704067200000,
        "key": "cpu.usage",
        "raw_value_hex": "0000...",  # hex-safe for bytes that failed deserialization
    },
}
```

The `raw_value_hex` field is critical: if a message failed Avro deserialization, the bytes are corrupt or use an unknown encoding — storing them as hex is the only safe representation.

**`flush()` instead of `poll(0)`**

```python
# BEFORE — triggers callbacks but doesn't guarantee delivery
dlq_producer.poll(0)

# AFTER — blocks until DLQ message is confirmed delivered or timeout reached
dlq_producer.flush(timeout=5.0)
```

The DLQ must durably persist every message before the original offset is committed. `poll(0)` only drains the callback queue — it does not confirm delivery. `flush()` blocks until the broker acknowledges receipt.

**DLQ Circuit Breaker**

If the DLQ producer itself fails repeatedly (`_MAX_DLQ_FAILURES = 5`), the consumer stops. Silently dropping messages that fail DLQ routing is never acceptable — better to stop and alert.

**Dedicated Producer with `acks=all`**

The DLQ uses a separate `Producer` instance from the main Avro producer. Two reasons:

1. The main producer enforces Avro schemas. A message that failed deserialization cannot be Avro-serialized — the DLQ must accept raw JSON.
2. `acks=all` on the DLQ producer ensures forensics data is durably written. Losing a poison pill means losing the ability to debug and replay it.

---

### `metrics_tracker.py`

#### Design Changes

**Dual-Track Instrumentation**

The existing in-memory tracker and structlog output were preserved intact. Prometheus metrics were added alongside them — not as a replacement. The two systems complement each other:

- **structlog** → per-message structured logs, human-readable, queryable in log aggregators
- **Prometheus** → time-series counters and histograms, queryable with PromQL, dashboardable in Grafana

**`record_dlq()` now requires a `reason` string**

```python
# BEFORE
def record_dlq(self):
    self.dlq_count += 1

# AFTER
def record_dlq(self, reason: str = "unknown"):
    self.dlq_count += 1
    DLQ_MESSAGES.labels(reason=reason).inc()
```

The `reason` label on `kafka_dlq_messages_total` lets you distinguish schema errors from business logic errors in PromQL:

```promql
# Are we getting schema errors specifically?
rate(kafka_dlq_messages_total{reason="SchemaRegistryException"}[5m])
```

**Three Prometheus Metrics**

```python
# Throughput + error ratio in one metric
MESSAGES_PROCESSED = Counter(
    "kafka_messages_processed_total",
    "Total Kafka messages processed, by outcome.",
    ["status"],   # "success" | "failure"
)

# P99 latency — where production problems hide
PROCESSING_LATENCY = Histogram(
    "kafka_message_processing_duration_seconds",
    "End-to-end processing time per message (seconds).",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)

# Data quality canary — alert if rate > 0 for > 5 minutes
DLQ_MESSAGES = Counter(
    "kafka_dlq_messages_total",
    "Total messages routed to the Dead Letter Queue, by reason.",
    ["reason"],
)
```

---

### `main.py`

#### Bug Fixes

**BUG 1 — `db_health_check` always returned HTTP 200**

The database health endpoint never raised `HTTPException` on failure. Load balancers and Kubernetes liveness probes received a `200 OK` even when the database was unreachable.

```python
# ADDED — mirrors the existing pattern in redis_health_check
if health_status["status"] != "healthy":
    raise HTTPException(status_code=503, detail=health_status)
```

**BUG 2 — Parameter name shadowed the `redis` module import**

```python
import redis.asyncio as redis  # ← 'redis' bound to module

# BEFORE — parameter 'redis' shadows the module inside this function scope
async def redis_health_check(redis: redis.Redis = Depends(get_redis_client)):
    await redis.ping()   # works by accident; any redis.* reference inside breaks

# AFTER — parameter renamed, no shadowing
async def redis_health_check(redis_client: redis.Redis = Depends(get_redis_client)):
    await redis_client.ping()
```

#### New Features

**`/kafka_health` Endpoint**

```python
@app.get("/kafka_health")
async def kafka_health_check():
    """Check the health of the Kafka producer connection."""
    ...
    await check_kafka_health()   # delegates to kafka.py — list_topics(timeout=3.0)
    ...
```

Returns `503` with a component status dict on failure — consistent with the existing Redis and DB health endpoints.

---

### `app/api/metrics.py`

#### Bug Fixes

**BUG 1 — `ValueError` from `metric_to_dict` returned `500` instead of `422`**

A missing or invalid `timestamp` is a caller error, not a server error. The bare `except Exception` swallowed `ValueError` and returned `500 Internal Server Error`.

```python
# ADDED — catches ValueError before the generic Exception handler
except ValueError as e:
    logger.warning("metric_validation_failed", error=str(e))
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=str(e),
    )
```

**BUG 2 — `limit` parameter silently clamped instead of rejected**

```python
# BEFORE — silent correction hides client bugs, violates least-surprise principle
if limit > 100:
    limit = 100

# AFTER — explicit rejection with a clear error message
if limit < 1 or limit > 100:
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="limit must be between 1 and 100",
    )
```

---

### Avro Schemas

Both schemas live in `app/schemas/`. The Schema Registry subject is `metrics.raw-value`, configured with **BACKWARD** compatibility — new consumers can always read old messages.

**`metric_event_v1.avsc`**

```json
{
  "type": "record",
  "name": "MetricEvent",
  "namespace": "com.analytics.metrics",
  "doc": "A real-time metric event from a tenant. Version 1.",
  "fields": [
    { "name": "name",      "type": "string" },
    { "name": "value",     "type": "double" },
    { "name": "timestamp", "type": { "type": "long", "logicalType": "timestamp-millis" } },
    { "name": "labels",    "type": { "type": "map", "values": "string" }, "default": {} }
  ]
}
```

**`metric_event_v2.avsc`** — backward-compatible evolution

```json
{
  "type": "record",
  "name": "MetricEvent",
  "namespace": "com.analytics.metrics",
  "doc": "A real-time metric event from a tenant. Version 2.",
  "fields": [
    { "name": "name",      "type": "string" },
    { "name": "value",     "type": "double" },
    { "name": "timestamp", "type": { "type": "long", "logicalType": "timestamp-millis" } },
    { "name": "labels",    "type": { "type": "map", "values": "string" }, "default": {} },
    {
      "name": "environment",
      "type": ["null", "string"],
      "default": null,
      "doc": "Deployment environment. Optional — null default ensures backward compatibility with v1 messages."
    }
  ]
}
```

**Why this is backward compatible:** `environment` is a union type `["null", "string"]` with `"default": null`. A v2 consumer reading a v1 message (which has no `environment` field) will automatically use the `null` default — no deserialization error, no schema mismatch.

---

### `docker-compose.yml`

**Added:** Prometheus container and two new port mappings on the `db` service.

```yaml
# Added to db.ports:
- "9090:9090"   # Prometheus UI
- "8001:8001"   # Worker metrics endpoint (scraped by Prometheus)

# New service:
prometheus:
  image: prom/prometheus:latest
  network_mode: service:db          # shares localhost with all other services
  volumes:
    - ../infrastructure/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
    - prometheus-data:/prometheus
```

All services share `network_mode: service:db`, meaning `localhost` is the same address space across Kafka, Schema Registry, FastAPI, the worker, and Prometheus. The Prometheus scrape target is `localhost:8001` — no service discovery needed in this dev environment.

**`infrastructure/prometheus/prometheus.yml`**

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: "analytics_consumer"
    static_configs:
      - targets: ["localhost:8001"]
    metrics_path: "/metrics"
```

---

## ADR-001: Avro + Schema Registry over Plain JSON

**Status:** Accepted  
**Context:** Choosing a serialization format for the `metrics.raw` Kafka topic.

### Options Considered

| Option | Pro | Con | Verdict |
|---|---|---|---|
| **Plain JSON** | Simple, human-readable | No contract enforcement; schema mismatches discovered at runtime in production | Rejected |
| **Protobuf + Schema Registry** | Extremely compact; strong typing | Code generation required; Python/Kafka tooling less mature than Avro | Not selected for this phase |
| **Avro + Schema Registry** | Binary (compact); enforced compatibility; schema ID embedded in every message; first-class confluent-kafka support | Not human-readable without tooling; Schema Registry is a new operational dependency | **Accepted** |

### Consequences

- Schema mismatches are caught at **produce time** — before the message reaches the consumer.
- Schema Registry must be treated as a **critical service** — it should run with replication in production (minimum 3 nodes).
- Developers must use `kcat --key-format avro` or Kafka UI for manual message inspection.
- Schema evolution follows a strict procedure (see ADR-003).

---

## ADR-002: Delivery Guarantee — At-Least-Once

**Status:** Accepted  
**Context:** Choosing a Kafka delivery guarantee for the consumer.

### Decision

At-least-once delivery via **manual offset commits**.

```python
consumer = DeserializingConsumer({
    ...
    "enable.auto.commit": False,   # manual control
})

# Commit only after successful processing OR DLQ routing
await process_message(msg)
consumer.commit(message=msg)
```

The offset is committed to `__consumer_offsets` only after the message is successfully processed or successfully routed to the DLQ. If the consumer crashes between `process_message()` and `commit()`, the message is redelivered on restart.

### Operational Implication — Idempotent Writes Required

Because a message can be redelivered, all downstream writes to TimescaleDB must be idempotent:

```sql
INSERT INTO metrics (tenant_id, metric_name, timestamp_ms, value)
VALUES ($1, $2, $3, $4)
ON CONFLICT (tenant_id, metric_name, timestamp_ms)
DO UPDATE SET value = EXCLUDED.value;
```

### Why Not Exactly-Once?

True end-to-end exactly-once across Kafka + TimescaleDB requires a distributed transaction coordinator (e.g., the Outbox Pattern with Debezium). At-least-once + idempotent writes achieves the same effective guarantee with far less operational overhead. This decision will be revisited if duplicate processing becomes measurable in production.

---

## ADR-003: Schema Evolution Strategy

**Status:** Accepted  
**Context:** Governing how schemas may change over time without breaking active consumers.

### Compatibility Mode

The Schema Registry subject `metrics.raw-value` uses **BACKWARD** compatibility.

| Mode | Meaning | Who's Protected |
|---|---|---|
| Backward | New consumer schema can read old messages | Consumers |
| Forward | Old consumer schema can read new messages | Producers |
| Full | Both simultaneously | Everyone |

BACKWARD was chosen because we control the consumer deployment schedule. We can always upgrade consumers before or alongside producers.

### Rules

1. New fields **must** be optional with a default value.
2. Field renames are **prohibited**. A rename is a DELETE + ADD — a breaking change under any compatibility mode.
3. Field type changes are **prohibited**.
4. Every schema change must be registered in the Schema Registry and reviewed before producer deployment.

### Field Rename Procedure (When Unavoidable)

If a field must effectively be renamed (e.g., `metric_value` → `value`):

```
Step 1 — ADD new field as optional with default null (register as vN+1)
Step 2 — Deploy producers writing to BOTH old and new field names
Step 3 — Deploy consumers reading new field, falling back to old field if null
Step 4 — Deprecate old field in schema doc (register as vN+2)
Step 5 — Remove old field only after ALL consumers confirmed upgraded (register as vN+3)
```

This takes N+1 deployments but guarantees zero downtime and zero message loss.

---

## Observability Reference

### Metrics Server

The consumer worker exposes Prometheus metrics on `:8001/metrics`. The server starts before the consume loop — observability is up before any workload begins.

```bash
# Verify metrics server is running
curl http://localhost:8001/metrics | grep kafka_

# Verify Prometheus is scraping
open http://localhost:9090/targets   # expect State: UP
```

### Key PromQL Queries

```promql
# Throughput — messages per second over last 5 minutes
rate(kafka_messages_processed_total{status="success"}[5m])

# Error ratio — fraction of messages failing
rate(kafka_messages_processed_total{status="failure"}[5m])
/ rate(kafka_messages_processed_total[5m])

# P99 processing latency
histogram_quantile(
  0.99,
  rate(kafka_message_processing_duration_seconds_bucket[5m])
)

# DLQ rate by reason — spike here = schema change or upstream bug
rate(kafka_dlq_messages_total[5m])

# Is the consumer stuck in a retry loop vs truly idle?
# (Non-zero failure rate + zero success rate = stuck)
rate(kafka_messages_processed_total{status="failure"}[5m]) > 0
and
rate(kafka_messages_processed_total{status="success"}[5m]) == 0
```

### Suggested Alerts

| Alert | Condition | Severity |
|---|---|---|
| DLQ receiving messages | `rate(kafka_dlq_messages_total[5m]) > 0` for 5 min | Warning |
| High error ratio | Error ratio > 5% for 10 min | Critical |
| P99 latency spike | `histogram_quantile(0.99, ...) > 1.0` | Warning |
| Consumer stuck | Failure rate > 0 AND success rate == 0 for 5 min | Critical |

---

## Known Limitations & Future Work

| Limitation | Impact | Recommended Fix |
|---|---|---|
| `consumer.poll()` in default `ThreadPoolExecutor` | At high consumer parallelism, threads may be starved | Pass a dedicated `ThreadPoolExecutor(max_workers=N)` to `run_in_executor` |
| `dlq_producer.flush(timeout=5.0)` is synchronous | Blocks event loop for up to 5s in the worst case | Wrap in `run_in_executor` — same pattern as `send_metric` |
| DLQ circuit breaker state is in-process only | On pod restart, failure count resets — circuit may never trip in k8s | Use Redis atomic counter shared across pod instances |
| No consumer lag metric from within the consumer | Can't detect partition blocking from Prometheus alone | Deploy `kafka-lag-exporter` as a sidecar; lag is better measured externally |
| Schema Registry loaded at module import time | If Schema Registry is down at startup, the entire app fails to import | Lazy initialization with retry logic in `lifespan()` |
| `send_to_dlq` does not retry on transient DLQ failure | A brief network blip between worker and Kafka could drop a forensics record | Add `tenacity` retry with exponential backoff before the circuit breaker trips |