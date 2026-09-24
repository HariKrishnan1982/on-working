"""
Minimal in-memory per-source rate limiter for telephony ingress endpoints.

Fixed-window counters keyed by (scope, source IP). No persistence, no
distributed state — this gateway is a single process; the limiter exists to
blunt webhook/call floods, not to provide billing-grade quotas. Limits come
from settings (VFD_TELEPHONY_RATE_LIMIT_PER_MIN). Exceeding the limit yields
HTTP 429 with a Retry-After hint. Legitimate low-rate signaling (a PBX, a
provider webhook, an operator) never approaches the default.
"""

from __future__ import annotations

import time
from typing import Dict, Tuple

from fastapi import HTTPException, Request

from configs.settings import settings

_window_start: Dict[Tuple[str, str], float] = {}
_window_count: Dict[Tuple[str, str], int] = {}

WINDOW_S = 60.0


def reset() -> None:
    """Clear all counters. Test hook only."""
    _window_start.clear()
    _window_count.clear()


def _client_key(request: Request) -> str:
    try:
        return request.client.host if request.client else "unknown"
    except Exception:
        return "unknown"


def check(scope: str, key: str, limit_per_min: int | None = None) -> None:
    """Raise HTTP 429 if (scope, key) exceeded its per-minute budget."""
    limit = settings.telephony_rate_limit_per_min if limit_per_min is None else limit_per_min
    now = time.time()
    slot = (scope, key)
    started = _window_start.get(slot, now)
    if now - started >= WINDOW_S:
        started = now
        _window_count[slot] = 0
        _window_start[slot] = started
    else:
        _window_start.setdefault(slot, started)
    count = _window_count.get(slot, 0) + 1
    _window_count[slot] = count
    if count > limit:
        retry_after = max(1, int(WINDOW_S - (now - started)))
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded for {scope} ({limit}/min). Retry in {retry_after}s.",
            headers={"Retry-After": str(retry_after)},
        )


async def limit_telephony_signaling(request: Request) -> None:
    """FastAPI dependency: rate-limit telephony call-control endpoints."""
    check("telephony-signaling", _client_key(request))


async def limit_telephony_webhook(request: Request) -> None:
    """FastAPI dependency: rate-limit provider webhook endpoints."""
    check("telephony-webhook", _client_key(request))
