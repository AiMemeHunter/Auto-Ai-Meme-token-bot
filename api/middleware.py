"""
API middleware: CORS, rate limiting, API key auth.
"""
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import time
from collections import defaultdict
from hunter.config import settings
from hunter.logger import get_logger

logger = get_logger(__name__)


class APIKeyMiddleware(BaseHTTPMiddleware):
    """API key authentication middleware."""
    EXEMPT_PATHS = {"/", "/health", "/docs", "/redoc", "/openapi.json", "/ws/feed"}

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in self.EXEMPT_PATHS or path.startswith("/static"):
            return await call_next(request)
        if settings.api_key:
            api_key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
            if api_key != settings.api_key:
                raise HTTPException(status_code=401, detail="Invalid API key")
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple rate limiting per IP."""
    def __init__(self, app, requests_per_minute: int = 60):
        super().__init__(app)
        self.rpm = requests_per_minute
        self._requests: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        self._requests[client_ip] = [t for t in self._requests[client_ip] if now - t < 60]
        if len(self._requests[client_ip]) >= self.rpm:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        self._requests[client_ip].append(now)
        return await call_next(request)


def setup_middleware(app: FastAPI) -> None:
    """Configure all middleware for the app."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(APIKeyMiddleware)
    app.add_middleware(RateLimitMiddleware, requests_per_minute=60)
