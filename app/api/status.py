"""
Status API Router
GET /api/v1/status/{repo}/{run_id}
GET /api/v1/status/{repo}/{run_id}/poll  ← polls until completion
"""

import logging

from fastapi import APIRouter, HTTPException

from app.models.deployment_models import WorkflowStatusResponse
from app.services import github_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/status/{repo}/{run_id}",
    summary="Get current workflow run status",
    description="Fetches the current status of a GitHub Actions run by repo and run ID.",
)
async def get_status(repo: str, run_id: int):
    """Get the current status of a workflow run (single fetch)."""
    logger.info(f"Status check: repo={repo} run_id={run_id}")
    result = await github_service.get_workflow_run_status(repo, run_id)

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return result


@router.get(
    "/status/{repo}/{run_id}/poll",
    summary="Poll workflow until completion",
    description=(
        "Polls the workflow run every N seconds until it completes or times out. "
        "This is a long-running request — use for synchronous monitoring."
    ),
)
async def poll_status(repo: str, run_id: int):
    """Poll a workflow run until it completes."""
    logger.info(f"Polling run: repo={repo} run_id={run_id}")
    result = await github_service.poll_workflow_until_complete(repo, run_id)

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return result
