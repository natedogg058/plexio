import asyncio
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from plexio.settings import settings


class InMemoryRateLimiter:
    def __init__(
        self,
        requests: int,
        window_seconds: int = 60,
        max_clients: int = 10_000,
    ):
        self.requests = requests
        self.window_seconds = window_seconds
        self.max_clients = max_clients
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def allow(self, key: str, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        cutoff = current - self.window_seconds
        async with self._lock:
            if key not in self._events and len(self._events) >= self.max_clients:
                stale_keys = [
                    client
                    for client, entries in self._events.items()
                    if not entries or entries[-1] <= cutoff
                ]
                for client in stale_keys:
                    self._events.pop(client, None)
                if len(self._events) >= self.max_clients:
                    self._events.pop(next(iter(self._events)))
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.requests:
                return False
            events.append(current)
            return True


public_api_limiter = InMemoryRateLimiter(settings.public_api_rate_limit)


async def limit_public_api(request: Request) -> None:
    client_ip = request.client.host if request.client else 'unknown'
    if settings.trust_proxy_headers:
        forwarded_for = request.headers.get('x-forwarded-for')
        if forwarded_for:
            client_ip = forwarded_for.split(',', 1)[0].strip()
    if not await public_api_limiter.allow(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail='Too many requests; retry in one minute',
            headers={'Retry-After': '60'},
        )
