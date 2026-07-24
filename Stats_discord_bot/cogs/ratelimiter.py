# rate_limiter.py - Complete Rate Limiting System (No Commands)

import asyncio
import time
import random
from typing import Dict, Optional, Callable, Any, List
from enum import Enum
from collections import defaultdict, deque
from dataclasses import dataclass, field
import functools


class RateLimitType(Enum):
    """Types of rate limiters with their priorities and hard caps."""

    # Hard-capped types (never exceed their limits, regardless of others)
    AUTOROLES = "autoroles"              # Max: 7 req/s, Hard cap: YES
    COUNTERS = "counters"                # Max: 7 req/s, Hard cap: YES
    SYNCING = "syncing"                  # Max: 5 req/s, Hard cap: YES
    API = "api"                          # Max: 5 req/s, Hard cap: YES

    # Soft-capped types (can borrow unused quota from hard-capped types,
    # but still must respect global 50 req/s ceiling)
    HISTORYSYNC = "historysync"          # Target: 1 req/s
    MESSAGE = "message"                  # Target: 10 req/s
    MESSAGE_WITH_HASH = "message_with_hash"  # Target: 10 req/s


@dataclass
class RateLimitConfig:
    """Configuration for a rate limiter."""
    name: str
    max_rate: float        # Baseline requests/second
    is_hard_cap: bool      # True = never exceed max_rate
    priority: int          # Lower = higher priority
    burst_multiplier: float = 1.5
    queue_timeout: float = 30.0


# Predefined configurations for each type
RATE_LIMIT_CONFIGS: Dict[RateLimitType, RateLimitConfig] = {
    RateLimitType.AUTOROLES: RateLimitConfig(
        name="autoroles", max_rate=7.0, is_hard_cap=True, priority=0, burst_multiplier=1.2
    ),
    RateLimitType.COUNTERS: RateLimitConfig(
        name="counters", max_rate=7.0, is_hard_cap=True, priority=0, burst_multiplier=1.2
    ),
    RateLimitType.SYNCING: RateLimitConfig(
        name="syncing", max_rate=5.0, is_hard_cap=True, priority=0, burst_multiplier=1.0
    ),
    RateLimitType.API: RateLimitConfig(
        name="api", max_rate=5.0, is_hard_cap=True, priority=0, burst_multiplier=1.0
    ),
    RateLimitType.HISTORYSYNC: RateLimitConfig(
        name="historysync", max_rate=1.0, is_hard_cap=False, priority=1, burst_multiplier=1.0
    ),
    RateLimitType.MESSAGE: RateLimitConfig(
        name="message", max_rate=10.0, is_hard_cap=False, priority=2, burst_multiplier=1.5
    ),
    RateLimitType.MESSAGE_WITH_HASH: RateLimitConfig(
        name="message_with_hash", max_rate=10.0, is_hard_cap=False, priority=2, burst_multiplier=1.5
    ),
}

# Combined hard cap rate of all hard-capped types at maximum usage
# 7 (autoroles) + 7 (counters) + 5 (syncing) + 5 (api) = 24 req/s reserved
_HARD_CAP_TOTAL = sum(
    cfg.max_rate
    for cfg in RATE_LIMIT_CONFIGS.values()
    if cfg.is_hard_cap
)  # = 24 req/s


# Global ceiling that ALL traffic must respect
_GLOBAL_MAX_RATE = 50.0  # requests/second


# ---------------------------------------------------------------------------
# Stats window: rolling 1-second window, bounded deque (no memory leak)
# ---------------------------------------------------------------------------

_STATS_WINDOW = 1.0          # seconds
_STATS_MAX_ENTRIES = 500     # safety cap per type


@dataclass
class TypeStats:
    total: int = 0
    limited: int = 0
    timeout: int = 0
    recent: deque = field(
        default_factory=lambda: deque(maxlen=_STATS_MAX_ENTRIES))

    def record(self):
        self.total += 1
        self.recent.append(time.monotonic())

    def current_rate(self) -> float:
        cutoff = time.monotonic() - _STATS_WINDOW
        while self.recent and self.recent[0] < cutoff:
            self.recent.popleft()
        return len(self.recent) / _STATS_WINDOW


class TokenBucket:
    """Token bucket with thread-safe async refill."""

    def __init__(self, rate: float, burst_multiplier: float = 1.5):
        self.rate = rate
        self.capacity = rate * burst_multiplier
        self.tokens = self.capacity
        self.last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def try_consume(self, tokens: float = 1.0) -> bool:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.last_refill = now
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False

    def available_tokens(self) -> float:
        now = time.monotonic()
        elapsed = now - self.last_refill
        return min(self.capacity, self.tokens + elapsed * self.rate)


class RateLimiter:
    """
    Rate limiter for Discord bots and API.

    All traffic respects the global 50 req/s ceiling.
    Hard-capped types (autoroles, counters, syncing, api) never exceed their individual limits.
    Soft-capped types (historysync, message, message_with_hash) can borrow unused quota from hard-capped types,
    but still cannot exceed the global 50 req/s ceiling.
    """

    def __init__(self, global_rate: float = _GLOBAL_MAX_RATE):
        self.global_rate = global_rate
        self.global_bucket = TokenBucket(global_rate, burst_multiplier=1.2)

        self.buckets: Dict[RateLimitType, TokenBucket] = {}
        self.hard_capped_types: List[RateLimitType] = []
        self.soft_capped_types: List[RateLimitType] = []

        self._retry_after: Dict[RateLimitType, float] = {}
        self._global_retry_after: float = 0.0

        self.stats: Dict[RateLimitType, TypeStats] = defaultdict(TypeStats)

        self._initialize_buckets()

    def _initialize_buckets(self):
        for limit_type, config in RATE_LIMIT_CONFIGS.items():
            self.buckets[limit_type] = TokenBucket(
                config.max_rate,
                burst_multiplier=config.burst_multiplier
            )
            if config.is_hard_cap:
                self.hard_capped_types.append(limit_type)
            else:
                self.soft_capped_types.append(limit_type)

        self.hard_capped_types.sort(
            key=lambda t: RATE_LIMIT_CONFIGS[t].priority)
        self.soft_capped_types.sort(
            key=lambda t: RATE_LIMIT_CONFIGS[t].priority)

    def notify_retry_after(
        self,
        limit_type: RateLimitType,
        retry_after_seconds: float,
        is_global: bool = False,
    ):
        unblock_at = time.monotonic() + retry_after_seconds
        if is_global:
            self._global_retry_after = unblock_at
        else:
            self._retry_after[limit_type] = unblock_at

    def _available_soft_quota(self) -> float:
        """
        Calculate how much of the global quota is available for soft-capped types.

        Soft-capped types can use:
        - Unused quota from hard-capped types (their reserved capacity that isn't being used)
        - But cannot exceed the global ceiling of 50 req/s total across all traffic

        Returns: Available requests per second for soft-capped types
        """
        # Calculate current usage of hard-capped types
        hard_cap_tokens_used = sum(
            self.buckets[t].capacity - self.buckets[t].available_tokens()
            for t in self.hard_capped_types
        )
        hard_cap_total_capacity = sum(
            self.buckets[t].capacity for t in self.hard_capped_types
        )

        if hard_cap_total_capacity == 0:
            return self.global_rate

        # What percentage of hard-cap capacity is currently being used?
        hard_utilisation = hard_cap_tokens_used / hard_cap_total_capacity

        # How many req/s of the reserved total are actually being used?
        hard_in_use_rate = hard_utilisation * _HARD_CAP_TOTAL

        # Unused hard-cap quota = reserved total - what's actually in use
        unused_hard_quota = max(0.0, _HARD_CAP_TOTAL - hard_in_use_rate)

        # Soft types can use up to (global ceiling - current hard usage)
        available_for_soft = self.global_rate - hard_in_use_rate

        # But they can also borrow from unused hard quota if needed
        # (This is already included in available_for_soft calculation above)

        return max(0.0, available_for_soft)

    async def acquire(self, limit_type: RateLimitType, timeout: float = 30.0) -> bool:
        config = RATE_LIMIT_CONFIGS[limit_type]
        start = time.monotonic()
        attempt = 0

        self.stats[limit_type].record()

        while True:
            now = time.monotonic()
            elapsed = now - start

            # Respect Discord Retry-After blocks
            global_block = self._global_retry_after - now
            if global_block > 0:
                if elapsed + global_block > timeout:
                    self.stats[limit_type].timeout += 1
                    return False
                await asyncio.sleep(global_block)
                continue

            type_block = self._retry_after.get(limit_type, 0) - now
            if type_block > 0:
                if elapsed + type_block > timeout:
                    self.stats[limit_type].timeout += 1
                    return False
                await asyncio.sleep(type_block)
                continue

            # GLOBAL CEILING CHECK - ALL traffic must respect this
            if not await self.global_bucket.try_consume(1.0):
                wait = self._backoff(attempt)
                if elapsed + wait > timeout:
                    self.stats[limit_type].timeout += 1
                    return False
                await asyncio.sleep(wait)
                attempt += 1
                continue

            # Hard-capped: must also pass per-type bucket (strict limit)
            if config.is_hard_cap:
                if await self.buckets[limit_type].try_consume(1.0):
                    return True
                wait = self._backoff(attempt)
                if elapsed + wait > timeout:
                    self.stats[limit_type].timeout += 1
                    return False
                await asyncio.sleep(wait)
                attempt += 1
                continue

            # Soft-capped: check if within available soft quota
            # (which already accounts for global ceiling)
            soft_quota = self._available_soft_quota()
            current_soft_rate = self.stats[limit_type].current_rate()

            if current_soft_rate < soft_quota:
                # Consume from per-type bucket for tracking, but the real limit is soft_quota
                await self.buckets[limit_type].try_consume(1.0)
                return True

            # Soft quota exhausted — back off
            self.stats[limit_type].limited += 1
            wait = self._backoff(attempt)
            if elapsed + wait > timeout:
                self.stats[limit_type].timeout += 1
                return False
            await asyncio.sleep(wait)
            attempt += 1

    @staticmethod
    def _backoff(attempt: int, base: float = 0.05, cap: float = 2.0) -> float:
        ceiling = min(cap, base * (2 ** attempt))
        return random.uniform(0, ceiling)

    async def execute(
        self,
        limit_type: RateLimitType,
        func: Callable,
        *args,
        timeout: float = 30.0,
        **kwargs,
    ) -> Any:
        if not await self.acquire(limit_type, timeout):
            raise TimeoutError(f"Rate limit timeout for {limit_type.value}")

        try:
            return await func(*args, **kwargs)
        except Exception as exc:
            self.stats[limit_type].limited += 1
            retry_after = getattr(exc, "retry_after", None)
            if retry_after is not None:
                is_global = getattr(exc, "is_global", False)
                self.notify_retry_after(
                    limit_type, float(retry_after), is_global)
            raise

    def get_stats(self) -> Dict[str, Any]:
        return {
            limit_type.value: {
                "total": s.total,
                "limited": s.limited,
                "timeout": s.timeout,
                "current_rate_per_sec": round(s.current_rate(), 2),
            }
            for limit_type, s in self.stats.items()
        }

    def available_soft_quota(self) -> float:
        """Get current available quota for soft-capped types."""
        return self._available_soft_quota()

    def global_available(self) -> float:
        """Get current available global quota (all traffic)."""
        return self.global_bucket.available_tokens()


# ============================================================================
# DECORATOR FOR EASY USE
# ============================================================================

def rate_limited(limit_type: RateLimitType, timeout: float = 30.0):
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            instance = args[0] if args else None
            rate_limiter: Optional[RateLimiter] = (
                getattr(instance, "rate_limiter", None)
                if instance is not None
                else None
            )
            if rate_limiter is None:
                raise RuntimeError(
                    "No rate_limiter found on self. "
                    "Add 'self.rate_limiter = RateLimiter()' to your cog's __init__."
                )
            return await rate_limiter.execute(limit_type, func, *args, timeout=timeout, **kwargs)
        return wrapper
    return decorator


def fastapi_rate_limited(limit_type: RateLimitType, timeout: float = 30.0):
    """Decorator for FastAPI endpoints - uses global rate limiter"""
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            rate_limiter = get_rate_limiter()
            if not await rate_limiter.acquire(limit_type, timeout=timeout):
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=429, detail="Rate limit exceeded")
            return await func(*args, **kwargs)
        return wrapper
    return decorator


# ============================================================================
# GLOBAL INSTANCE FOR SIMPLE IMPORT
# ============================================================================

_global_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    global _global_rate_limiter
    if _global_rate_limiter is None:
        _global_rate_limiter = RateLimiter()
    return _global_rate_limiter
