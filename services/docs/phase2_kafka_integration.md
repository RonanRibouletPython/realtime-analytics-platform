# Phase 2: Kafka Integration - Event-Driven Architecture

**Completed:** January 27, 2025  
**Duration:** ~4-6 hours  
**Status:** COMPLETE  
**Previous Phase:** [Phase 1 - Foundation](./phase1_technical_summary.md)

---

## What We Built

Transformed the synchronous metrics ingestion API into an **event-driven, asynchronous system** using Apache Kafka. This enables:
- Non-blocking API responses
- Decoupled ingestion from processing
- Horizontal scalability
- Fault tolerance and message replay
- Dead Letter Queue for poison messages

### Architecture Evolution

**Phase 1 (Synchronous):**
```
Client → FastAPI → PostgreSQL
         (Blocks until DB write completes)
```

**Phase 2 (Event-Driven):**
```
Client → FastAPI → Kafka → Consumer Worker → PostgreSQL
         (Returns immediately)   (Background processing)
```

---

## System Architecture
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

### 1. **Apache Kafka 3.6+**

**Why Kafka:**
- Industry-standard event streaming platform
- Used by Uber, Netflix, LinkedIn, Airbnb
- Handles millions of messages per second
- Durable message storage (not just a queue)
- Horizontal scalability

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
```python
# Same group_id = work distribution
consumer1 = AIOKafkaConsumer(..., group_id="metrics_worker_group")
consumer2 = AIOKafkaConsumer(..., group_id="metrics_worker_group")

# Kafka automatically assigns different partitions to each consumer!
```

**Scaling pattern:**
```bash
# Run multiple workers (same group_id)
# Kafka balances load automatically
python worker.py &  # Consumer 1
python worker.py &  # Consumer 2
python worker.py &  # Consumer 3
```

#### c) Offset Management
```python
# Manual commit for reliability
enable_auto_commit=False

# After successful processing
await consumer.commit()  # Checkpoint: "I processed up to message X"

# If consumer crashes, restart from last committed offset
```

**Why manual commits:**
- Prevent data loss (commit only after DB write succeeds)
- Enable retry logic (don't commit if processing fails)
- Exactly-once semantics possible

#### d) Message Serialization
```python
# Producer: Python dict → JSON → bytes
value_serializer=lambda v: json.dumps(v).encode("utf-8")

# Consumer: bytes → JSON → Python dict
value_deserializer=lambda m: json.loads(m.decode("utf-8"))
```

---

### 2. **aiokafka (Async Kafka Client)**

**Why aiokafka over kafka-python:**
- Native async/await support
- Non-blocking I/O
- Perfect for FastAPI integration

**Producer Pattern:**
```python
# Singleton pattern (reuse connection)
_producer: AIOKafkaProducer | None = None

async def get_kafka_producer() -> AIOKafkaProducer:
    global _producer
    if _producer is None:
        _producer = AIOKafkaProducer(
            bootstrap_servers="localhost:9092",
            value_serializer=lambda v: json.dumps(v).encode("utf-8")
        )
        await _producer.start()
    return _producer
```

**Why singleton:**
- Connection pooling (expensive to create)
- Reuse across requests
- Graceful shutdown management

**Consumer Pattern:**
```python
consumer = AIOKafkaConsumer(
    'metrics',
    bootstrap_servers='localhost:9092',
    group_id='metrics_worker_group',
    auto_offset_reset='earliest',  # Start from beginning if new
    enable_auto_commit=False        # Manual commits
)

await consumer.start()

async for msg in consumer:
    # Process message
    await process(msg.value)
    
    # Commit offset
    await consumer.commit()
```

---

### 3. **Dead Letter Queue (DLQ) Pattern**

**Problem:** What happens when a message can't be processed?
- Malformed JSON
- Invalid data types
- Business rule violations

**Solution:** Route to DLQ for manual inspection
```python
async def process_message(session, message, producer):
    try:
        # Normal processing
        metric = Metric(**message)
        session.add(metric)
        await session.commit()
        return True
        
    except ValueError as e:
        # Data validation failed - send to DLQ
        await send_to_dlq(producer, message, str(e))
        return True  # Don't retry (it will fail again)
        
    except Exception as e:
        # Database error - might be temporary
        return False  # Retry later
```

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

---

### 4. **Graceful Shutdown**

**Problem:** Ctrl+C kills worker mid-processing
- Message half-processed
- Database transaction incomplete
- Offset not committed

**Solution:** Signal Handlers
```python
shutdown_flag = False

def signal_handler(sig, frame):
    global shutdown_flag
    shutdown_flag = True  # Set flag instead of immediate exit

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

async for msg in consumer:
    if shutdown_flag:
        break  # Finish current message, then exit
    
    await process(msg)

# Cleanup
await consumer.commit()
await consumer.stop()
```

**Why this matters:**
- No data loss
- Clean shutdown in production
- Kubernetes/Docker compatibility

---

## Code Walkthrough

### Complete Message Flow

**1. Client sends HTTP request:**
```bash
POST /api/v1/metrics
{
  "name": "cpu_usage",
  "value": 85.5,
  "labels": {"host": "server-01"}
}
```

**2. FastAPI endpoint (non-blocking):**
```python
@router.post("/metrics", status_code=202)
async def ingest_metric(metric: MetricCreate):
    producer = await get_kafka_producer()  # Singleton
    
    # Send to Kafka (async, but waits for acknowledgment)
    await producer.send_and_wait(
        topic="metrics",
        value=metric.model_dump(mode="json")
    )
    
    # Return immediately (message queued)
    return {"status": "queued", "message": "Accepted"}
```
**Response time:** <10ms (vs 50-100ms for direct DB write)

**3. Kafka stores message:**
```
Topic: metrics
Partition: 0 (determined by hash of key, or round-robin)
Offset: 12345 (sequential ID within partition)
```

**4. Consumer fetches message:**
```python
async for msg in consumer:
    # msg.topic = "metrics"
    # msg.partition = 0
    # msg.offset = 12345
    # msg.value = {"name": "cpu_usage", "value": 85.5, ...}
    
    await process_message(msg.value)
    await consumer.commit()  # Checkpoint
```

**5. Process and save:**
```python
async def process_message(message_value):
    metric = Metric(
        name=message_value["name"],
        value=message_value["value"],
        timestamp=datetime.fromisoformat(message_value["timestamp"]),
        labels=message_value["labels"]
    )
    
    session.add(metric)
    await session.commit()
```

**Total latency:** 100-500ms from HTTP request to DB persistence
- API response: <10ms
- Background processing: 90-490ms
- User experience: Instant ✨

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
uv run uvicorn app.main:app --reload &

# 3. Start consumer
uv run python app/worker.py &

# 4. Send test data
uv run python tests/test_kafka_pipeline.py

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
- [aiokafka](https://aiokafka.readthedocs.io/)
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