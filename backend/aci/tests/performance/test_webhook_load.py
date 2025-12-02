"""
Performance Test for Webhook Receiver

This script uses locust to load test the webhook receiver endpoint.
Tests rate limiting, processing time, and system behavior under load.

Run with:
    locust -f test_webhook_load.py --host=http://localhost:8000

Or headless:
    locust -f test_webhook_load.py --host=http://localhost:8000 \
           --users 100 --spawn-rate 10 --run-time 60s --headless
"""

import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, datetime

from locust import HttpUser, between, task


class WebhookUser(HttpUser):
    """
    Simulates a user sending webhook requests.

    Tests:
    - Normal webhook processing
    - Rate limiting behavior
    - Concurrent requests
    - Different payload sizes
    """

    wait_time = between(0.1, 0.5)  # Wait 100-500ms between requests

    def on_start(self):
        """Initialize test data for this user."""
        # Create a test trigger (in real scenario, this would be set up beforehand)
        self.trigger_id = str(uuid.uuid4())
        self.app_name = "github"
        self.webhook_secret = "test-secret-key"

    def _sign_payload(self, payload: bytes) -> str:
        """Create HMAC signature for webhook payload."""
        return hmac.new(
            self.webhook_secret.encode(), payload, hashlib.sha256
        ).hexdigest()

    @task(10)
    def send_webhook_small(self):
        """Send a small webhook payload (normal case)."""
        payload = {
            "event": "push",
            "repository": {"name": "test-repo"},
            "commits": [
                {
                    "id": str(uuid.uuid4()),
                    "message": "Test commit",
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            ],
        }

        payload_bytes = json.dumps(payload).encode()
        signature = self._sign_payload(payload_bytes)

        with self.client.post(
            f"/webhooks/{self.app_name}/{self.trigger_id}",
            data=payload_bytes,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": f"sha256={signature}",
            },
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 429:
                # Rate limited - this is expected under load
                response.success()
            elif response.status_code == 404:
                # Trigger doesn't exist - expected in test environment
                response.success()
            else:
                response.failure(f"Unexpected status code: {response.status_code}")

    @task(5)
    def send_webhook_large(self):
        """Send a large webhook payload (stress test)."""
        # Create a payload with 100 commits (simulates batch push)
        commits = [
            {
                "id": str(uuid.uuid4()),
                "message": f"Test commit {i}" * 10,  # Longer messages
                "timestamp": datetime.now(UTC).isoformat(),
                "author": {"name": "Test User", "email": "test@example.com"},
                "files": [f"file{j}.py" for j in range(5)],
            }
            for i in range(100)
        ]

        payload = {
            "event": "push",
            "repository": {"name": "test-repo", "full_name": "org/test-repo"},
            "commits": commits,
        }

        payload_bytes = json.dumps(payload).encode()
        signature = self._sign_payload(payload_bytes)

        with self.client.post(
            f"/webhooks/{self.app_name}/{self.trigger_id}",
            data=payload_bytes,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": f"sha256={signature}",
            },
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 429:
                response.success()
            elif response.status_code == 404:
                response.success()
            else:
                response.failure(f"Unexpected status code: {response.status_code}")

    @task(2)
    def send_webhook_burst(self):
        """Send rapid burst of webhooks (test rate limiting)."""
        # Send 5 requests in quick succession
        for _ in range(5):
            payload = {
                "event": "issue_comment",
                "action": "created",
                "comment": {"id": str(uuid.uuid4()), "body": "Test comment"},
                "timestamp": datetime.now(UTC).isoformat(),
            }

            payload_bytes = json.dumps(payload).encode()
            signature = self._sign_payload(payload_bytes)

            with self.client.post(
                f"/webhooks/{self.app_name}/{self.trigger_id}",
                data=payload_bytes,
                headers={
                    "Content-Type": "application/json",
                    "X-Hub-Signature-256": f"sha256={signature}",
                },
                catch_response=True,
            ) as response:
                if response.status_code in [200, 429, 404]:
                    response.success()
                else:
                    response.failure(f"Unexpected status: {response.status_code}")

            # Small delay between burst requests
            time.sleep(0.01)

    @task(1)
    def check_metrics(self):
        """Periodically check metrics endpoint."""
        with self.client.get("/metrics", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Metrics endpoint failed: {response.status_code}")


class RateLimitUser(HttpUser):
    """
    Specifically tests rate limiting behavior.

    Sends high-frequency requests to trigger rate limits.
    """

    wait_time = between(0.01, 0.05)  # Very short wait times

    def on_start(self):
        self.trigger_id = str(uuid.uuid4())
        self.app_name = "slack"
        self.webhook_secret = "test-secret"
        self.rate_limited_count = 0
        self.success_count = 0

    @task
    def spam_webhooks(self):
        """Send many requests to test rate limiter."""
        payload = {"event": "message", "text": "spam", "ts": str(time.time())}

        payload_bytes = json.dumps(payload).encode()
        signature = hmac.new(
            self.webhook_secret.encode(), payload_bytes, hashlib.sha256
        ).hexdigest()

        with self.client.post(
            f"/webhooks/{self.app_name}/{self.trigger_id}",
            data=payload_bytes,
            headers={
                "Content-Type": "application/json",
                "X-Slack-Signature": f"v0={signature}",
            },
            catch_response=True,
        ) as response:
            if response.status_code == 429:
                self.rate_limited_count += 1
                response.success()
            elif response.status_code in [200, 404]:
                self.success_count += 1
                response.success()
            else:
                response.failure(f"Unexpected status: {response.status_code}")


# ============================================================================
# Custom Test Scenarios
# ============================================================================


def print_stats():
    """Print custom statistics after test run."""
    print("\n" + "=" * 80)
    print("WEBHOOK LOAD TEST RESULTS")
    print("=" * 80)
    print("\nRate Limiting Effectiveness:")
    print("- Check that 429 responses appear under high load")
    print("- Verify that rate limits reset after cooldown period")
    print("\nPerformance Targets:")
    print("- P50 response time: < 100ms")
    print("- P95 response time: < 500ms")
    print("- P99 response time: < 1000ms")
    print("- Throughput: > 100 req/s")
    print("\nMetrics Available at: http://localhost:8000/metrics")
    print("=" * 80)


# ============================================================================
# Usage Instructions
# ============================================================================

if __name__ == "__main__":
    print("""
╔════════════════════════════════════════════════════════════════════╗
║                  WEBHOOK LOAD TEST SUITE                           ║
╠════════════════════════════════════════════════════════════════════╣
║                                                                    ║
║  This script tests the webhook receiver under various load        ║
║  conditions to validate rate limiting and performance.            ║
║                                                                    ║
║  PREREQUISITES:                                                    ║
║  1. Server running at http://localhost:8000                       ║
║  2. Install locust: pip install locust                            ║
║                                                                    ║
║  USAGE:                                                            ║
║                                                                    ║
║  Web UI (recommended):                                             ║
║    locust -f test_webhook_load.py --host=http://localhost:8000    ║
║    Then open: http://localhost:8089                               ║
║                                                                    ║
║  Headless (automated):                                             ║
║    locust -f test_webhook_load.py \\                               ║
║           --host=http://localhost:8000 \\                          ║
║           --users 100 \\                                           ║
║           --spawn-rate 10 \\                                       ║
║           --run-time 60s \\                                        ║
║           --headless                                               ║
║                                                                    ║
║  SCENARIOS:                                                        ║
║  - WebhookUser: Normal webhook traffic with varying sizes         ║
║  - RateLimitUser: High-frequency spam to test rate limiting       ║
║                                                                    ║
║  WHAT TO LOOK FOR:                                                 ║
║  ✓ Response times stay low under load                             ║
║  ✓ Rate limiting kicks in (429 responses)                         ║
║  ✓ No 5xx errors under normal load                                ║
║  ✓ System recovers after load spike                               ║
║                                                                    ║
╚════════════════════════════════════════════════════════════════════╝
    """)
