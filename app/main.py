"""
AI Deployment Agent - Main Application Entry Point
FastAPI + OpenAI + GitHub Actions API
"""

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from app.api import deploy, status, chat
from app.config.settings import settings

# ─── Logging Setup ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


# ─── Lifespan ─────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 AI Deployment Agent starting up...")
    logger.info(f"   GitHub Owner : {settings.GITHUB_OWNER}")
    logger.info(f"   Repos        : {settings.SUPPORTED_REPOS}")
    logger.info(f"   Environments : {settings.SUPPORTED_ENVIRONMENTS}")
    logger.info(f"   Workflow     : {settings.WORKFLOW_FILE}")
    yield
    logger.info("🛑 AI Deployment Agent shutting down...")


# ─── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="AI Deployment Agent",
    description=(
        "Trigger GitHub Actions deployment workflows via natural language "
        "or structured JSON. Powered by FastAPI + OpenAI + GitHub API."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routers ──────────────────────────────────────────────────────────────────
app.include_router(deploy.router, prefix="/api/v1", tags=["Deploy"])
app.include_router(status.router, prefix="/api/v1", tags=["Status"])
app.include_router(chat.router,   prefix="/api/v1", tags=["Chat Agent"])


# ─── Global Exception Handler ─────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled exception on {request.url}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"status": "FAILED", "error": f"Internal server error: {str(exc)}"},
    )


# ─── Health ───────────────────────────────────────────────────────────────────
@app.get("/health", tags=["Health"])
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "AI Deployment Agent",
        "version": "1.0.0",
        "github_owner": settings.GITHUB_OWNER,
        "workflow_file": settings.WORKFLOW_FILE,
    }


@app.get("/", tags=["Health"])
async def root():
    """Serve the Chat UI."""
    ui_path = Path(__file__).parent / "static" / "index.html"
    if ui_path.exists():
        return HTMLResponse(ui_path.read_text())
    return {"message": "AI Deployment Agent is running.", "docs": "/docs"}