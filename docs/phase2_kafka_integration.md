# Phase 2: Kafka Integration - Event-Driven Architecture

**Completed:** February 07, 2026 
**Duration:** ~8 hours 
**Status:** COMPLETE  
**Previous Phase:** [Phase 1 - Foundation](./phase1_technical_summary.md)

---

## What We Built

Transformed the synchronous metrics ingestion API into an **event-driven, asynchronous system** using Apache Kafka and Confluent Schema Registry. This enables:
- Strict Data Validation via Avro Schemas
- Non-blocking API responses (Fire and Forget)
- Decoupled ingestion from database writing
- Dead Letter Queue for poison messages

### Architecture Evolution

**Phase 1 (Synchronous):**
```
Client → FastAPI → PostgreSQL
         (Blocks until DB write completes)
```

**Phase 2 (Event-Driven):**
```
Client → FastAPI → [Schema Registry Check] → Kafka (Avro) → Consumer Worker → PostgreSQL
         (Returns immediately)   (Background processing)
```

---

## System Architecture (TODO: update the schema to add schema registry and Avro serialisation)
```
┌─────────────────────────────────────────────────────────┐
│                  HTTP Clients                            │
│  (External APIs, Load Test Scripts, Real Apps)          │
└────────────────┬────────────────────────────────────────┘
                 │ POST /api/v1/metrics
                 │ (Returns 202 Accepted immediately)
                 ▼
┌─────────────────────────────────────────────────────────┐
│            FastAPI Ingestion Service                     │
│  ┌──────────────────────────────────────────────┐       │
│  │  Kafka Producer (Singleton)                  │       │
│  │  - Connection pooling                        │       │
│  │  - JSON serialization                        │       │
│  │  - Async send_and_wait                       │       │
│  └────────────┬─────────────────────────────────┘       │
└───────────────┼──────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────┐
│              Apache Kafka (KRaft Mode)                   │
│  ┌──────────────────────────────────────────────┐       │
│  │  Topic: metrics                              │       │
│  │  - Partitions: 3 (default)                   │       │
│  │  - Replication: 1 (dev)                      │       │
│  │  - Retention: 7 days                         │       │
│  └──────────┬───────────────────────────────────┘       │
│             │                                            │
│  ┌──────────▼───────────────────────────────────┐       │
│  │  Topic: metrics_dlq (Dead Letter Queue)      │       │
│  │  - Failed/Invalid messages                   │       │
│  └──────────────────────────────────────────────┘       │
└───────────────┼──────────────────────────────────────────┘
                │
                │ Consumer Group: metrics_worker_group
                │ (Multiple instances for scalability)
                ▼
┌─────────────────────────────────────────────────────────┐
│            Consumer Worker Service                       │
│  ┌──────────────────────────────────────────────┐       │
│  │  Message Processing                          │       │
│  │  - Deserialize JSON                          │       │
│  │  - Validate data                             │       │
│  │  - Transform to DB model                     │       │
│  │  - Error handling                            │       │
│  │  - DLQ routing                               │       │
│  └────────────┬─────────────────────────────────┘       │
│               │                                          │
│  ┌────────────▼─────────────────────────────────┐       │
│  │  Performance Monitoring                      │       │
│  │  - Messages/second                           │       │
│  │  - Processing time                           │       │
│  │  - Error rates                               │       │
│  └──────────────────────────────────────────────┘       │
└───────────────┼──────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────┐
│                   PostgreSQL 16                          │
│  - Metrics table (persisted data)                       │
│  - JSONB labels                                         │
│  - Time-series indexes                                  │
└─────────────────────────────────────────────────────────┘
```

---

## Technical Stack Additions

### 1. **Confluent Kafka (Python Client)**
We chose confluent-kafka (based on librdkafka) over aiokafka or kafka-python
**Why Kafka:**
- Industry-standard event streaming platform
- Used by Uber, Netflix, LinkedIn, Airbnb
- Handles millions of messages per second
- Durable message storage (not just a queue)
- Horizontal scalability

**Why Confluent Kafka**
- Performance: High-performance C-binding
- Reliability: Industry standard for production Python services.
- Schema Registry Support: Native integration for Avro/Protobuf
- Synchronous Producer: Allows "fire-and-forget" with internal buffering for maximum throughput

### 2. **Avro Serialization & Schema Registry**
Instead of sending raw JSON, we now send Avro binary data
**Why Avro**
- Compact: Binary format is smaller than JSON (faster network transfer)
- Strict Typing: Ensures downstream consumers don't crash due to missing fields
- Schema Evolution: Allows us to add fields later without breaking existing consumers

The Schema (metric_event.avsc):
```json
{
  "type": "record",
  "name": "MetricEvent",
  "fields": [
    {"name": "name", "type": "string"},
    {"name": "value", "type": "double"},
    {"name": "timestamp", "type": "long", "logicalType": "timestamp-millis"},
    {"name": "labels", "type": {"type": "map", "values": "string"}}
  ]
}
```
### 3. **The Producer Pattern (Fire-and-Forget)**
We moved from await send_and_wait to a high-throughput synchronous pattern
**How it works**
1. API calls producer.produce()
2. Message is added to a local C-buffer immediately
3. The request returns 202 Accepted to the user (< 10ms)
4. A background thread sends the batch to Kafka efficiently
5. Shutdown Safety: We implemented a flush() method in lifespan to ensure buffer is emptied before the app exits

**Key Concepts Learned:**

#### a) Topics & Partitions
```
Topic: metrics
├── Partition 0: [msg1, msg5, msg9, ...]
├── Partition 1: [msg2, msg6, msg10, ...]
└── Partition 2: [msg3, msg7, msg11, ...]
```

**Why partitions matter:**
- Parallel processing (each consumer gets different partitions)
- Ordering guaranteed **within** a partition
- Scalability (add more partitions = more consumers)

#### b) Consumer Groups
**Scaling pattern:**
```bash
# Run multiple workers (same group_id)
# Kafka balances load automatically
python worker.py &  # Consumer 1
python worker.py &  # Consumer 2
python worker.py &  # Consumer 3
```

#### c) Offset Management
**Why manual commits:**
- Prevent data loss (commit only after DB write succeeds)
- Enable retry logic (don't commit if processing fails)
- Exactly-once semantics possible
---

### 2. Confluent Kafka (documentation to add)

### 3. **Dead Letter Queue (DLQ) Pattern**

**Problem:** What happens when a message can't be processed?
- Malformed JSON
- Invalid data types
- Business rule violations

**DLQ Message Structure:**
```json
{
  "original_message": {...},
  "error": "Invalid timestamp format",
  "dlq_timestamp": "2025-01-27T10:30:00Z",
  "partition": 0,
  "offset": 12345
}
```

**Monitoring DLQ:**
- Check Kafka UI at http://localhost:8080
- Alert if DLQ has messages
- Investigate and fix data issues
- Replay from DLQ after fixing

---

### 4. **KRaft Mode (Kafka without Zookeeper)**

**Old Kafka:**
```
Kafka Broker → Zookeeper (coordination service)
```

**New Kafka (KRaft):**
```
Kafka Broker (self-managed consensus)
```

**Benefits:**
- Simpler deployment (one less service)
- Faster startup
- Better scalability
- Industry moving to KRaft

**Configuration:**
```yaml
environment:
  KAFKA_NODE_ID: 1
  KAFKA_PROCESS_ROLES: broker,controller
  KAFKA_LISTENERS: PLAINTEXT://:9092,CONTROLLER://:9093
  KAFKA_CONTROLLER_QUORUM_VOTERS: 1@localhost:9093
```

---

## Core Concepts Learned

### 1. **Event-Driven Architecture**

**Traditional (Request-Response):**
```
Client → Service A → Service B → Service C
         (waits)     (waits)     (returns)
```
If Service C is slow/down, everything blocks.

**Event-Driven (Publish-Subscribe):**
```
Client → Service A → [Event Bus] → Service B
                                  → Service C
                                  → Service D
```
Services are **decoupled**. Service A doesn't wait.

**Benefits:**
- Non-blocking responses
- Independent scaling
- Fault isolation
- Easy to add new consumers

---

### 2. **At-Least-Once vs Exactly-Once Delivery**

**At-Least-Once (What we have):**
```python
# Process message
await save_to_db(message)

# Commit offset
await consumer.commit()  # ← If crashes here, message reprocessed

# Result: Message might be processed 2+ times
```

**Why it's OK for us:**
- Metrics are idempotent (duplicate = same value)
- Cost of preventing duplicates > cost of duplicates

**Exactly-Once (Advanced - Phase 4):**
```python
# Use transactions
async with db.begin():
    await save_to_db(message)
    await save_offset_to_db(offset)
    # Both succeed or both fail
```

---

### 3. **Backpressure Handling**

**Problem:** Producer sends faster than consumer processes

**Solution 1: Kafka Buffers**
```
Producer (1000 msg/sec) → Kafka (buffer) → Consumer (100 msg/sec)
                          ↑
                    Messages queue up here
```

**Solution 2: Add More Consumers**
```
Producer (1000 msg/sec) → Kafka → Consumer 1 (100 msg/sec)
                                → Consumer 2 (100 msg/sec)
                                → Consumer 3 (100 msg/sec)
                                ... (scale to match load)
```

**Monitoring:**
```python
# Track consumer lag
lag = latest_offset - committed_offset

# Alert if lag > threshold
if lag > 10000:
    send_alert("Consumer falling behind!")
```

### 4. ***Schema Registry Workflow***
TODO

---

## Performance Improvements

### Before (Phase 1)

**Single Request:**
- HTTP → Validate → DB Write → Return
- **Latency:** 50-100ms per request
- **Throughput:** ~10-20 requests/sec (single-threaded)

**Under Load:**
- Database becomes bottleneck
- Requests queue up
- Timeouts occur
- Users see slow responses

### After (Phase 2)

**Single Request:**
- HTTP → Validate → Kafka → Return
- **Latency:** <10ms per request
- **Throughput:** 100+ requests/sec

**Under Load:**
- API stays fast (just queues to Kafka)
- Kafka buffers messages
- Consumers process in background
- Scale consumers independently

### Scalability

**Vertical Scaling (Phase 1):**
```
Bigger server = More expensive
Limited by single DB connection
```

**Horizontal Scaling (Phase 2):**
```
More API servers = Handle more requests
More consumers = Process more messages
Kafka in middle = Buffer and coordinate
Cost grows linearly
```

---

## Monitoring & Observability

### Consumer Metrics Tracked
```python
class MetricsTracker:
    processed_count: int      # Total messages processed
    failed_count: int         # Failures (retries)
    dlq_count: int           # Sent to DLQ
    processing_times: list   # Latency distribution
    uptime: timedelta        # Worker uptime
```

**Log Output:**
```
consumer_stats processed=1000 failed=5 dlq=2 
               rate_per_sec=95.2 avg_processing_ms=12.5 
               uptime_sec=10.5
```

### Kafka UI

Access at http://localhost:8080

**What you can see:**
- Topics and partitions
- Message count per topic
- Consumer groups and lag
- Individual messages (inspect payload)
- Broker health

**Key Metrics:**
- **Consumer Lag:** How far behind is consumer?
- **Messages/sec:** Throughput
- **Partition distribution:** Is load balanced?

---

## Debugging Tips

### Problem: Messages not appearing in database

**Check 1: Is consumer running?**
```bash
# Should see "Worker listening!"
ps aux | grep worker.py
```

**Check 2: Are messages in Kafka?**
- Open Kafka UI: http://localhost:8080
- Topics → metrics → Messages
- See count increasing?

**Check 3: Consumer lag?**
- Kafka UI → Consumers → metrics_worker_group
- Check "Lag" column
- High lag = consumer slow or crashed

**Check 4: Check DLQ**
```bash
# Messages in DLQ?
curl http://localhost:8080/api/topics/metrics_dlq/messages
```

### Problem: Consumer crashes repeatedly

**Check logs:**
```bash
# Run worker in foreground
uv run python app/worker.py

# Watch for errors
```

**Common issues:**
- Database connection lost (check PostgreSQL)
- Invalid message format (check DLQ)
- Memory issues (check resource limits)

---

## Testing

### End-to-End Test
```bash
# 1. Start services
docker-compose up -d

# 2. Start API
bash run.sh

# 3. Start consumer
bash worker.sh

# 4. Send test data
bash test_kafka_pipeline.sh

# Expected output:
# Metric 1 queued
# Metric 2 queued
# ...
# Pipeline test PASSED!
```

### Load Test
```bash
# Send 1000 messages as fast as possible
time for i in {1..1000}; do
  curl -X POST http://localhost:8000/api/v1/metrics \
    -H "Content-Type: application/json" \
    -d "{\"name\":\"load_test\",\"value\":$i,\"labels\":{}}" &
done
wait

# Check results
curl http://localhost:8000/api/v1/metrics?limit=100 | jq 'length'
```

**Expected:** All 1000 messages processed within 10-30 seconds

---

## Real-World Comparison

### Companies Using Similar Architecture

| Company | Use Case | Scale |
|---------|----------|-------|
| **Uber** | Ride events, location updates | 1 trillion+ messages/day |
| **Netflix** | Viewing events, recommendations | Billions/day |
| **LinkedIn** | Activity streams, notifications | 7 trillion+ messages/day |
| **Airbnb** | Booking events, pricing updates | Millions/day |

**Our system:** Ready to scale to millions/day!

---

## Key Takeaways

### What Makes This "Senior-Level"

**Junior approach:**
- Direct DB writes
- Blocking operations
- Single point of failure
- Hard to scale

**Senior approach (what we built):**
- Event-driven architecture
- Non-blocking async operations
- Decoupled services
- Horizontal scalability
- Fault tolerance (DLQ)
- Monitoring and observability
- Graceful degradation

### Interview-Ready Knowledge

You can now answer:
- "Design a high-throughput ingestion system"
- "How do you handle message failures?"
- "Explain at-least-once delivery"
- "How do you scale a consumer?"
- "What's the difference between a queue and a log?"

---

## Next Steps: Phase 3 Preview

### Stream Processing (Real-Time Aggregations)
```python
# Current: Individual metrics
{"name": "cpu_usage", "value": 85.5}

# Phase 3: Real-time aggregations
{"name": "cpu_usage_avg_5min", "value": 82.3, "window": "10:00-10:05"}
{"name": "cpu_usage_p95_1hour", "value": 91.2, "window": "09:00-10:00"}
```

**Technologies:**
- Kafka Streams or Flink
- Windowing functions (tumbling, sliding, session)
- State stores for aggregations

### TimescaleDB Integration
```sql
-- Hypertables: Automatic partitioning by time
CREATE TABLE metrics (
  timestamp TIMESTAMPTZ NOT NULL,
  ...
);

SELECT create_hypertable('metrics', 'timestamp');

-- Continuous aggregations
CREATE MATERIALIZED VIEW metrics_hourly
WITH (timescaledb.continuous) AS
SELECT
  time_bucket('1 hour', timestamp) as bucket,
  name,
  AVG(value) as avg_value
FROM metrics
GROUP BY bucket, name;
```

### Data Retention & Archival
```python
# Hot storage: Last 7 days (fast queries)
# Warm storage: 7-90 days (compressed)
# Cold storage: 90+ days (S3/archive)

# Automatic compression
ALTER TABLE metrics SET (
  timescaledb.compress,
  timescaledb.compress_segmentby = 'name'
);

# Retention policy
SELECT add_retention_policy('metrics', INTERVAL '90 days');
```

---

## Resources & References

### Documentation
- [Kafka Documentation](https://kafka.apache.org/documentation/)
- [Confluent Kafka Guide](https://docs.confluent.io/platform/current/kafka/introduction.html)

### Learning
- [Designing Data-Intensive Applications](https://dataintensive.net/) - Chapter 11
- [Kafka: The Definitive Guide](https://www.confluent.io/resources/kafka-the-definitive-guide-v2/)

### Tools Used
- Kafka UI: http://localhost:8080
- Kafka CLI tools in container

---

## Commands Reference
```bash
# Start all services
docker-compose up -d

# Start API server
cd services/ingestion
uv run uvicorn app.main:app --reload

# Start consumer worker
uv run python app/worker.py

# Send test metric
curl -X POST http://localhost:8000/api/v1/metrics \
  -H "Content-Type: application/json" \
  -d '{"name":"test","value":42.0,"labels":{}}'

# Check Kafka topics
docker exec -it <kafka-container> \
  /opt/kafka/bin/kafka-topics.sh --list --bootstrap-server localhost:9092

# View messages in topic
docker exec -it <kafka-container> \
  /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic metrics --from-beginning

# Check consumer group lag
docker exec -it <kafka-container> \
  /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe --group metrics_worker_group
```

---

**Previous:** [Phase 1 - Foundation](./phase1_technical_summary.md)  
**Next:** Phase 3 - Stream Processing & Time-Series Optimization  
**Project:** [Main README](../../README.md)

---

*Built with ❤️ on the journey from Junior to Senior Backend Engineer*
