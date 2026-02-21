from datetime import datetime as dt
from datetime import timezone as tz

import structlog
from prometheus_client import Counter, Histogram, start_http_server

logger = structlog.get_logger()

# Prometheus Metrics are defined at module level
# so they are registered once on import
# Process global Singletons are used

# Singletons
MESSAGES_PROCESSED = Counter(
    "kafka_messages_processed_total",
    "Total Kafka messages processed, by outcome.",
    # 'status' label lets you compute error ratio in a single PromQL query:
    # rate(kafka_messages_processed_total{status="failure"}[5m])
    # / rate(kafka_messages_processed_total[5m])
    ["status"],  # values: "success" | "failure"
)

PROCESSING_LATENCY = Histogram(
    "kafka_message_processing_duration_seconds",
    "End-to-end processing time per message (seconds).",
    # Buckets tuned for a real-time system: we care about sub-100ms.
    # Anything approaching 1s is worth investigating.
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)

DLQ_MESSAGES = Counter(
    "kafka_dlq_messages_total",
    "Total messages routed to the Dead Letter Queue, by reason.",
    ["reason"],  # e.g. "ValueError", "deserialization_error", "db_error"
)


def start_metrics_server(port: int = 8001) -> None:
    """
    Start the Prometheus HTTP server.
    Call this ONCE at worker startup, before the consume loop begins.
    Prometheus will scrape GET /metrics on this port every 15s.
    """
    start_http_server(port)
    logger.info("prometheus_metrics_server_started", port=port)


class MetricsTracker:
    """
    Track processing metrics for monitoring.
    Dual-track: in-memory stats for structured log summaries (your existing
    logic) + Prometheus counters/histograms for real-time dashboards.
    """

    def __init__(self):
        self.processed_count = 0
        self.failed_count = 0
        self.dlq_count = 0
        self.processing_times: list[float] = []
        self.start_time = dt.now(tz.utc)

    def record_success(self, processing_time_ms: float):
        """Record successful processing."""
        self.processed_count += 1
        self.processing_times.append(processing_time_ms)

        # Prometheus: increment success counter + observe latency
        MESSAGES_PROCESSED.labels(status="success").inc()
        # Histogram expects seconds; your existing code tracks ms
        PROCESSING_LATENCY.observe(processing_time_ms / 1000)

        # Log stats every 100 messages
        if self.processed_count % 100 == 0:
            self.log_stats()

    def record_failure(self):
        """Record processing failure (transient error, will not DLQ).."""
        self.failed_count += 1
        # Prometheus: increment failure counter
        MESSAGES_PROCESSED.labels(status="failure").inc()

    def record_dlq(self, reason: str = "unknown"):
        """
        Record message sent to DLQ.
        Args:
            reason: Short machine-readable reason code. Used as a Prometheus
                    label so you can alert on specific error classes.
                    e.g. "ValueError", "deserialization_error"
        """
        self.dlq_count += 1
        # Prometheus: labeled so you can distinguish schema errors vs logic errors
        DLQ_MESSAGES.labels(reason=reason).inc()

    def log_stats(self):
        """Log current statistics."""
        uptime = (dt.now(tz.utc) - self.start_time).total_seconds()
        rate = self.processed_count / uptime if uptime > 0 else 0

        avg_time = (
            sum(self.processing_times) / len(self.processing_times)
            if self.processing_times
            else 0
        )

        logger.info(
            "consumer_stats",
            processed=self.processed_count,
            failed=self.failed_count,
            dlq=self.dlq_count,
            rate_per_sec=round(rate, 2),
            avg_processing_ms=round(avg_time, 2),
            uptime_sec=round(uptime, 2),
        )


# Global tracker instance
tracker = MetricsTracker()
