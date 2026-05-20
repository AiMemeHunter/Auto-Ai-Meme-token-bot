"""
FastAPI REST API server with WebSocket support.
"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from hunter.config import settings
from hunter.engine import HunterEngine
from hunter.logger import setup_logging, get_logger
from api.routes.tokens import router as tokens_router
from api.routes.alerts import router as alerts_router
from api.routes.stats import router as stats_router
from api.middleware import setup_middleware

logger = get_logger(__name__)

engine = HunterEngine()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management."""
    setup_logging()
    logger.info("api_server_starting")
    asyncio.create_task(engine.start())
    yield
    await engine.stop()
    logger.info("api_server_stopped")


app = FastAPI(
    title="Meme Token Hunter API",
    description="Multi-chain meme token scanner with AI-powered rug pull detection",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Setup middleware
setup_middleware(app)

# Mount API routes
app.include_router(tokens_router, prefix="/api/v1/tokens", tags=["Tokens"])
app.include_router(alerts_router, prefix="/api/v1/alerts", tags=["Alerts"])
app.include_router(stats_router, prefix="/api/v1/stats", tags=["Stats"])

# Serve static web dashboard
web_dir = Path(__file__).parent.parent / "web"
if web_dir.exists():
    app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")


@app.get("/", include_in_schema=False)
async def serve_dashboard():
    """Serve the web dashboard."""
    index = web_dir / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"message": "Meme Token Hunter API v1.0.0", "docs": "/docs"}


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "model_loaded": engine.model_manager.is_model_loaded,
        "model_version": engine.model_manager.get_model_version(),
        "active_scanners": len([s for s in engine.scanners.values() if s.is_running]),
    }


@app.websocket("/ws/feed")
async def websocket_feed(websocket: WebSocket):
    """WebSocket endpoint for live token feed."""
    await websocket.accept()
    engine.register_ws_client(websocket)
    logger.info("ws_client_connected")
    try:
        while True:
            data = await websocket.receive_text()
            # Client can send filter preferences
    except WebSocketDisconnect:
        engine.unregister_ws_client(websocket)
        logger.info("ws_client_disconnected")


def run_server():
    """Run the API server."""
    import uvicorn
    uvicorn.run(
        "api.server:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    run_server()
