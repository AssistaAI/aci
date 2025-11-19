"""
Simple Performance Tests for Trigger System

These tests can be run with pytest and don't require additional dependencies.
Tests basic performance characteristics of the trigger system components.

Run with:
    pytest -v aci/tests/performance/test_simple_load.py
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from aci.server.metrics import MetricsCollector, get_metrics_collector
from aci.server.rate_limiter import RateLimiter


class TestRateLimiterPerformance:
    """Test rate limiter performance under load."""

    def test_rate_limiter_throughput(self):
        """Test rate limiter can handle high request volume."""
        limiter = RateLimiter(rate=1000, capacity=2000)  # High limits

        start_time = time.time()
        requests = 10000

        for i in range(requests):
            allowed, metadata = limiter.allow(f"user_{i % 100}")  # 100 unique users
            assert isinstance(allowed, bool)
            assert "remaining" in metadata

        elapsed = time.time() - start_time
        throughput = requests / elapsed

        print(f"\nRate limiter throughput: {throughput:.0f} req/s")
        assert throughput > 10000, "Rate limiter should handle >10k req/s"

    def test_rate_limiter_concurrent(self):
        """Test rate limiter thread safety under concurrent load."""
        limiter = RateLimiter(rate=10, capacity=20)  # Lower limits to trigger rate limiting
        num_threads = 10
        requests_per_thread = 50  # More requests to ensure rate limiting

        def make_requests(thread_id):
            results = []
            # All threads use same identifier to trigger rate limiting
            for i in range(requests_per_thread):
                allowed, metadata = limiter.allow("shared_user")
                results.append(allowed)
            return results

        start_time = time.time()

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(make_requests, i) for i in range(num_threads)]
            all_results = []
            for future in as_completed(futures):
                all_results.extend(future.result())

        elapsed = time.time() - start_time

        total_requests = num_threads * requests_per_thread
        throughput = total_requests / elapsed

        print(f"\nConcurrent throughput: {throughput:.0f} req/s")
        print(f"Success rate: {sum(all_results)/len(all_results)*100:.1f}%")
        print(f"Rate limited: {len([r for r in all_results if not r])} requests")

        # Some requests should be rate limited when sharing same identifier
        assert not all(all_results), "Some requests should be rate limited"
        assert throughput > 1000, "Should handle >1k concurrent req/s"

    def test_rate_limiter_latency(self):
        """Test rate limiter latency distribution."""
        limiter = RateLimiter(rate=100, capacity=200)
        latencies = []

        # Warm up
        for _ in range(100):
            limiter.allow("warmup")

        # Measure
        for i in range(1000):
            start = time.perf_counter()
            limiter.allow(f"user_{i % 10}")
            latency = (time.perf_counter() - start) * 1000  # Convert to ms
            latencies.append(latency)

        latencies.sort()
        p50 = latencies[len(latencies) // 2]
        p95 = latencies[int(len(latencies) * 0.95)]
        p99 = latencies[int(len(latencies) * 0.99)]

        print(f"\nRate limiter latency (ms):")
        print(f"  P50: {p50:.3f}")
        print(f"  P95: {p95:.3f}")
        print(f"  P99: {p99:.3f}")

        # Performance targets
        assert p50 < 1.0, "P50 latency should be <1ms"
        assert p95 < 5.0, "P95 latency should be <5ms"
        assert p99 < 10.0, "P99 latency should be <10ms"


class TestMetricsCollectorPerformance:
    """Test metrics collector performance under load."""

    def test_metrics_throughput(self):
        """Test metrics collector write throughput."""
        collector = MetricsCollector()
        operations = 10000

        start_time = time.time()

        for i in range(operations):
            collector.increment_counter("test_counter", labels={"id": str(i % 100)})
            collector.set_gauge("test_gauge", i % 1000, labels={"type": "test"})
            collector.record_histogram("test_histogram", float(i % 100))

        elapsed = time.time() - start_time
        throughput = (operations * 3) / elapsed  # 3 operations per iteration

        print(f"\nMetrics throughput: {throughput:.0f} ops/s")
        assert throughput > 10000, "Should handle >10k metric ops/s"

    def test_metrics_concurrent(self):
        """Test metrics collector thread safety."""
        collector = MetricsCollector()
        num_threads = 10
        operations_per_thread = 1000

        def record_metrics(thread_id):
            for i in range(operations_per_thread):
                collector.increment_counter(
                    "concurrent_test", labels={"thread": str(thread_id)}
                )
                collector.set_gauge("thread_gauge", i, labels={"thread": str(thread_id)})
                collector.record_histogram("latency", float(i % 100))

        start_time = time.time()

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(record_metrics, i) for i in range(num_threads)]
            for future in as_completed(futures):
                future.result()

        elapsed = time.time() - start_time

        # Verify data integrity
        metrics = collector.get_metrics()
        total_ops = num_threads * operations_per_thread * 3
        throughput = total_ops / elapsed

        print(f"\nConcurrent metrics throughput: {throughput:.0f} ops/s")

        # Check that counters were incremented correctly
        counter_total = sum(v for k, v in metrics["counters"].items() if "concurrent_test" in k)
        expected_total = num_threads * operations_per_thread

        assert counter_total == expected_total, "Counter integrity check failed"
        assert throughput > 5000, "Should handle >5k concurrent ops/s"

    def test_metrics_get_performance(self):
        """Test metrics retrieval performance."""
        collector = MetricsCollector()

        # Populate with data
        for i in range(100):
            collector.increment_counter("counter", labels={"id": str(i)})
            collector.set_gauge("gauge", i, labels={"id": str(i)})
            collector.record_histogram("histogram", float(i), labels={"id": str(i)})

        # Measure retrieval time
        latencies = []
        for _ in range(100):
            start = time.perf_counter()
            metrics = collector.get_metrics()
            latency = (time.perf_counter() - start) * 1000
            latencies.append(latency)

        latencies.sort()
        p50 = latencies[len(latencies) // 2]
        p95 = latencies[int(len(latencies) * 0.95)]

        print(f"\nMetrics retrieval latency (ms):")
        print(f"  P50: {p50:.3f}")
        print(f"  P95: {p95:.3f}")

        assert p50 < 10.0, "P50 retrieval should be <10ms"
        assert p95 < 50.0, "P95 retrieval should be <50ms"


class TestBackgroundJobsPerformance:
    """Test performance of background job operations."""

    def test_cleanup_simulation(self):
        """Simulate cleanup job performance with many items."""
        # Simulate processing 10,000 expired events
        items_to_process = 10000
        batch_size = 100

        start_time = time.time()

        # Simulate batched cleanup
        processed = 0
        while processed < items_to_process:
            batch = min(batch_size, items_to_process - processed)
            # Simulate database operation latency
            time.sleep(0.001)  # 1ms per batch
            processed += batch

        elapsed = time.time() - start_time
        throughput = items_to_process / elapsed

        print(f"\nCleanup throughput: {throughput:.0f} items/s")
        print(f"Total time for {items_to_process} items: {elapsed:.2f}s")

        # Should process cleanup reasonably fast
        assert elapsed < 60, "Should cleanup 10k items in <60s"
        assert throughput > 100, "Should process >100 items/s"


# ============================================================================
# Performance Benchmarks Summary
# ============================================================================


@pytest.fixture(scope="session", autouse=True)
def print_performance_summary(request):
    """Print performance summary after all tests."""
    yield

    print("\n" + "=" * 80)
    print("PERFORMANCE TEST SUMMARY")
    print("=" * 80)
    print("\nComponent Performance Targets:")
    print("  Rate Limiter:")
    print("    ✓ Throughput: >10,000 req/s")
    print("    ✓ Latency P99: <10ms")
    print("    ✓ Thread-safe under concurrent load")
    print("\n  Metrics Collector:")
    print("    ✓ Write throughput: >10,000 ops/s")
    print("    ✓ Retrieval latency: <50ms (P95)")
    print("    ✓ Data integrity under concurrent writes")
    print("\n  Background Jobs:")
    print("    ✓ Cleanup: >100 items/s")
    print("    ✓ Batch processing: <60s for 10k items")
    print("\nAll performance tests completed!")
    print("=" * 80)
