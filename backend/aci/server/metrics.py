"""
Metrics and Observability for Trigger System

Provides metrics collection for monitoring trigger health and performance.
Can be integrated with Prometheus, DataDog, or other monitoring systems.
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock

from aci.common.logging_setup import get_logger

logger = get_logger(__name__)


@dataclass
class MetricValue:
    """Single metric value with timestamp"""

    value: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    labels: dict[str, str] = field(default_factory=dict)


class MetricsCollector:
    """
    Thread-safe metrics collector.

    Collects:
    - Counters (monotonically increasing)
    - Gauges (point-in-time values)
    - Histograms (distribution of values)
    """

    def __init__(self):
        self.counters: dict[str, float] = defaultdict(float)
        self.gauges: dict[str, float] = defaultdict(float)
        self.histograms: dict[str, list[float]] = defaultdict(list)
        self.lock = Lock()

    def increment_counter(
        self, name: str, value: float = 1.0, labels: dict[str, str] | None = None
    ):
        """
        Increment a counter metric.

        Args:
            name: Metric name
            value: Amount to increment (default 1.0)
            labels: Optional labels for metric
        """
        with self.lock:
            key = self._make_key(name, labels)
            self.counters[key] += value

    def set_gauge(self, name: str, value: float, labels: dict[str, str] | None = None):
        """
        Set a gauge metric to a specific value.

        Args:
            name: Metric name
            value: Gauge value
            labels: Optional labels for metric
        """
        with self.lock:
            key = self._make_key(name, labels)
            self.gauges[key] = value

    def record_histogram(self, name: str, value: float, labels: dict[str, str] | None = None):
        """
        Record a value in a histogram.

        Args:
            name: Metric name
            value: Value to record
            labels: Optional labels for metric
        """
        with self.lock:
            key = self._make_key(name, labels)
            self.histograms[key].append(value)

            # Keep only last 1000 values to prevent memory bloat
            if len(self.histograms[key]) > 1000:
                self.histograms[key] = self.histograms[key][-1000:]

    def get_metrics(self) -> dict[str, any]:
        """
        Get all collected metrics.

        Returns:
            Dict with all metrics
        """
        with self.lock:
            return {
                "counters": dict(self.counters),
                "gauges": dict(self.gauges),
                "histograms": {
                    k: {
                        "count": len(v),
                        "sum": sum(v),
                        "min": min(v) if v else 0,
                        "max": max(v) if v else 0,
                        "avg": sum(v) / len(v) if v else 0,
                    }
                    for k, v in self.histograms.items()
                },
            }

    def reset(self):
        """Reset all metrics (useful for testing)"""
        with self.lock:
            self.counters.clear()
            self.gauges.clear()
            self.histograms.clear()

    @staticmethod
    def _make_key(name: str, labels: dict[str, str] | None) -> str:
        """Create metric key with labels"""
        if not labels:
            return name

        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"


# Global metrics collector
_metrics_collector: MetricsCollector | None = None


def get_metrics_collector() -> MetricsCollector:
    """
    Get singleton metrics collector.

    Returns:
        MetricsCollector instance
    """
    global _metrics_collector

    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
        logger.info("Initialized metrics collector")

    return _metrics_collector


# ============================================================================
# Trigger-Specific Metrics
# ============================================================================


def record_webhook_received(app_name: str, trigger_id: str, event_type: str):
    """Record a webhook received event"""
    metrics = get_metrics_collector()
    metrics.increment_counter(
        "webhook_received_total",
        labels={
            "app": app_name,
            "trigger_id": trigger_id,
            "event_type": event_type,
        },
    )


def record_webhook_processing_time(app_name: str, duration_seconds: float):
    """Record webhook processing duration"""
    metrics = get_metrics_collector()
    metrics.record_histogram(
        "webhook_processing_duration_seconds",
        duration_seconds,
        labels={"app": app_name},
    )


def record_webhook_verification_failure(app_name: str, reason: str):
    """Record webhook verification failure"""
    metrics = get_metrics_collector()
    metrics.increment_counter(
        "webhook_verification_failed_total",
        labels={"app": app_name, "reason": reason},
    )


def record_trigger_registration(app_name: str, success: bool):
    """Record trigger registration attempt"""
    metrics = get_metrics_collector()
    status = "success" if success else "failed"
    metrics.increment_counter(
        "trigger_registration_total",
        labels={"app": app_name, "status": status},
    )


def record_trigger_renewal(app_name: str, success: bool):
    """Record trigger renewal attempt"""
    metrics = get_metrics_collector()
    status = "success" if success else "failed"
    metrics.increment_counter(
        "trigger_renewal_total",
        labels={"app": app_name, "status": status},
    )


def record_trigger_deletion(app_name: str, success: bool):
    """Record trigger deletion attempt"""
    metrics = get_metrics_collector()
    status = "success" if success else "failed"
    metrics.increment_counter(
        "trigger_deletion_total",
        labels={"app": app_name, "status": status},
    )


def record_event_stored(trigger_id: str, event_type: str):
    """Record event stored in database"""
    metrics = get_metrics_collector()
    metrics.increment_counter(
        "trigger_event_stored_total",
        labels={"trigger_id": trigger_id, "event_type": event_type},
    )


def record_duplicate_event(trigger_id: str):
    """Record duplicate event detected"""
    metrics = get_metrics_collector()
    metrics.increment_counter(
        "trigger_event_duplicate_total",
        labels={"trigger_id": trigger_id},
    )


def record_rate_limit_hit(identifier_type: str):
    """Record rate limit hit"""
    metrics = get_metrics_collector()
    metrics.increment_counter(
        "rate_limit_hit_total",
        labels={"type": identifier_type},
    )


def set_active_triggers_gauge(app_name: str, count: int):
    """Set number of active triggers for an app"""
    metrics = get_metrics_collector()
    metrics.set_gauge(
        "active_triggers_count",
        count,
        labels={"app": app_name},
    )


def set_pending_events_gauge(trigger_id: str, count: int):
    """Set number of pending events for a trigger"""
    metrics = get_metrics_collector()
    metrics.set_gauge(
        "pending_events_count",
        count,
        labels={"trigger_id": trigger_id},
    )


# ============================================================================
# Metric Decorators
# ============================================================================


def track_webhook_processing(app_name: str):
    """
    Decorator to track webhook processing time.

    Usage:
        @track_webhook_processing("GITHUB")
        async def process_github_webhook(payload):
            ...
    """

    def decorator(func):
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                record_webhook_processing_time(app_name, duration)

        return wrapper

    return decorator


# ============================================================================
# Prometheus Export (Optional)
# ============================================================================


def export_prometheus_metrics() -> str:
    """
    Export metrics in Prometheus format.

    Returns:
        Metrics in Prometheus text format
    """
    metrics = get_metrics_collector().get_metrics()
    lines = []

    # Export counters
    for name, value in metrics["counters"].items():
        lines.append(f"# TYPE {name.split('{')[0]} counter")
        lines.append(f"{name} {value}")

    # Export gauges
    for name, value in metrics["gauges"].items():
        lines.append(f"# TYPE {name.split('{')[0]} gauge")
        lines.append(f"{name} {value}")

    # Export histograms
    for name, stats in metrics["histograms"].items():
        base_name = name.split("{")[0]
        labels = name[len(base_name) :] if "{" in name else ""

        lines.append(f"# TYPE {base_name} histogram")
        lines.append(f"{base_name}_count{labels} {stats['count']}")
        lines.append(f"{base_name}_sum{labels} {stats['sum']}")

    return "\n".join(lines) + "\n"
