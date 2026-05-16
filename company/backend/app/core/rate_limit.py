"""Simple in-memory sliding-window rate limiter utilities.

This module provides a tiny, low-dependency rate limiter intended for
short-lived processes (e.g. API servers running in a single process).
It implements a sliding-window algorithm using timestamped events stored
in deques. The implementation is intentionally simple and not meant for
distributed deployments.
"""

from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock
from time import time


@dataclass(frozen=True)
class RateLimitRule:
    """Configuration for a rate limit.

    Attributes:
        limit: maximum number of allowed events in the window
        window_seconds: window size in seconds
    """
    limit: int
    window_seconds: int


class RateLimitExceeded(Exception):
    """Raised when a rate limit has been exceeded.

    The exception exposes `retry_after_seconds` to indicate how long the
    caller should wait before retrying.
    """

    def __init__(self, *, retry_after_seconds: int) -> None:
        super().__init__("Rate limit exceeded.")
        self.retry_after_seconds = retry_after_seconds


class InMemorySlidingWindowLimiter:
    """Thread-safe in-memory sliding-window limiter.

    This keeps a mapping of `bucket` -> deque[timestamp]. On each `hit`
    call we prune timestamps older than the window, check the count, and
    append the new event. A `Lock` protects the in-memory structures so
    concurrent hits from multiple threads are safe.
    """

    def __init__(self) -> None:
        # Map bucket key -> deque of event timestamps (floats from time()).
        self._events: dict[str, deque[float]] = defaultdict(deque)
        # Simple mutex to protect the deque operations.
        self._lock = Lock()

    def hit(self, *, bucket: str, rule: RateLimitRule) -> None:
        """Record a hit for `bucket` and enforce the provided `rule`.

        If the number of recorded events in the last `rule.window_seconds`
        is already >= `rule.limit`, this raises `RateLimitExceeded` with
        a conservative `retry_after_seconds` value (at least 1).

        Args:
            bucket: Unique key to group related events (e.g. client+action)
            rule: Rate limit configuration to apply

        Raises:
            RateLimitExceeded: when the limit would be exceeded by this hit
        """
        now = time()
        cutoff = now - rule.window_seconds

        # Lock to ensure deque mutations and reads are atomic across threads.
        with self._lock:
            hits = self._events[bucket]

            # Remove timestamps that are outside the sliding window (oldest
            # first). This keeps the deque size bounded to roughly the limit.
            while hits and hits[0] <= cutoff:
                hits.popleft()

            # If we've already reached the allowed limit, compute a
            # retry-after value based on when the oldest remaining hit
            # will fall out of the window. Use `max(1, ...)` to avoid
            # returning 0 which could create tight retry loops.
            if len(hits) >= rule.limit:
                retry_after = max(1, int(rule.window_seconds - (now - hits[0])))
                raise RateLimitExceeded(retry_after_seconds=retry_after)

            # Record this hit.
            hits.append(now)


# Common rules used by the application. Comments explain intended usage.
# Allow 5 OTP request attempts per 10 minutes per bucket.
otp_request_rule = RateLimitRule(limit=5, window_seconds=600)
# Allow 10 OTP verification attempts per 10 minutes per bucket.
otp_verify_rule = RateLimitRule(limit=10, window_seconds=600)

# A single in-memory limiter instance used by the app when running in a
# single process. For a multi-process deployment this should be replaced
# with a distributed store (Redis, etc.).
otp_limiter = InMemorySlidingWindowLimiter()


def build_rate_bucket(*, action: str, client_ip: str, patient_key_hash: str) -> str:
    """Create a deterministic bucket key for rate limiting.

    The key concatenates `action`, `client_ip`, and `patient_key_hash`.
    Keep this stable because changing the format will invalidate existing
    counters.
    """
    return f"{action}:{client_ip}:{patient_key_hash}"