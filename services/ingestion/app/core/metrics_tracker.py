from datetime import datetime, timezone
from datetime import datetime as dt
from datetime import timezone as tz

import structlog

logger = structlog.get_logger()


class MetricsTracker:
    """Track processing metrics for monitoring."""

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

        # Log stats every 100 messages
        if self.processed_count % 100 == 0:
            self.log_stats()

    def record_failure(self):
        """Record processing failure."""
        self.failed_count += 1

    def record_dlq(self):
        """Record message sent to DLQ."""
        self.dlq_count += 1

    def log_stats(self):
        """Log current statistics."""
        uptime = (datetime.now(timezone.utc) - self.start_time).total_seconds()
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
