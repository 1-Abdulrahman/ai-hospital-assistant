from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock
from time import time


@dataclass(frozen=True)
class RateLimitRule:
    limit: int
    window_seconds: int


class RateLimitExceeded(Exception):
    def __init__(self, *, retry_after_seconds: int) -> None:
        super().__init__("Rate limit exceeded.")
        self.retry_after_seconds = retry_after_seconds


class InMemorySlidingWindowLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def hit(self, *, bucket: str, rule: RateLimitRule) -> None:
        now = time()
        cutoff = now - rule.window_seconds

        with self._lock:
            hits = self._events[bucket]

            while hits and hits[0] <= cutoff:
                hits.popleft()

            if len(hits) >= rule.limit:
                retry_after = max(1, int(rule.window_seconds - (now - hits[0])))
                raise RateLimitExceeded(retry_after_seconds=retry_after)

            hits.append(now)


otp_request_rule = RateLimitRule(limit=5, window_seconds=600)
otp_verify_rule = RateLimitRule(limit=10, window_seconds=600)

otp_limiter = InMemorySlidingWindowLimiter()


def build_rate_bucket(*, action: str, client_ip: str, patient_key_hash: str) -> str:
    return f"{action}:{client_ip}:{patient_key_hash}"