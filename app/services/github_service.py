"""
GitHub Service
Handles all GitHub Actions API interactions:
  - Trigger workflow_dispatch
  - Fetch workflow runs
  - Poll run status
  - Validate repos and branches
"""

import logging
import time
from typing import Optional

import httpx

from app.config.settings import settings

logger = logging.getLogger(__name__)

HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


def _auth_headers() -> dict:
    """Build authorization headers using the PAT token from settings."""
    if not settings.GITHUB_TOKEN:
        raise ValueError(
            "GITHUB_TOKEN is not set. Add it to your .env file."
        )
    return {**HEADERS, "Authorization": f"Bearer {settings.GITHUB_TOKEN}"}


# ── Validation ────────────────────────────────────────────────────────────────

async def validate_repo_exists(repo: str) -> tuple[bool, str]:
    """Check that the repo actually exists on GitHub."""
    url = f"{settings.GITHUB_API_BASE}/repos/{settings.GITHUB_OWNER}/{repo}"
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.get(url, headers=_auth_headers())
            if resp.status_code == 200:
                return True, ""
            elif resp.status_code == 404:
                return False, f"Repository '{repo}' not found under '{settings.GITHUB_OWNER}'."
            else:
                return False, f"GitHub API error {resp.status_code}: {resp.text}"
        except httpx.RequestError as e:
            return False, f"Network error checking repo: {str(e)}"


async def validate_branch_exists(repo: str, branch: str) -> tuple[bool, str]:
    """Check that the branch exists in the repo."""
    url = (
        f"{settings.GITHUB_API_BASE}/repos/{settings.GITHUB_OWNER}/{repo}"
        f"/branches/{branch}"
    )
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.get(url, headers=_auth_headers())
            if resp.status_code == 200:
                return True, ""
            elif resp.status_code == 404:
                return False, f"Branch '{branch}' not found in repo '{repo}'."
            else:
                return False, f"GitHub API error {resp.status_code}: {resp.text}"
        except httpx.RequestError as e:
            return False, f"Network error checking branch: {str(e)}"


async def list_workflow_files(repo: str) -> list[str]:
    """List all workflow files in .github/workflows/ for discovery."""
    url = (
        f"{settings.GITHUB_API_BASE}/repos/{settings.GITHUB_OWNER}/{repo}"
        f"/contents/.github/workflows"
    )
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.get(url, headers=_auth_headers())
            if resp.status_code == 200:
                files = resp.json()
                return [f["name"] for f in files if f["name"].endswith(".yml")]
            return []
        except Exception:
            return []


# ── Trigger ───────────────────────────────────────────────────────────────────

async def trigger_workflow(
    repo: str,
    branch: str,
    environment: str,
    image_id: str,
) -> tuple[bool, str, Optional[int]]:
    """
    Trigger the AKS-CD.yml workflow via workflow_dispatch.

    Returns:
        (success: bool, error_message: str, run_id: int | None)
    """
    url = (
        f"{settings.GITHUB_API_BASE}/repos/{settings.GITHUB_OWNER}/{repo}"
        f"/actions/workflows/{settings.WORKFLOW_FILE}/dispatches"
    )

    payload = {
        "ref": branch,
        "inputs": {
            "environment": environment,
            "branch": branch,
            "image_id": image_id,
        },
    }

    logger.info(f"Triggering workflow | repo={repo} branch={branch} env={environment} image={image_id}")
    logger.debug(f"POST {url} | payload={payload}")

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.post(url, headers=_auth_headers(), json=payload)

            if resp.status_code == 204:
                # 204 No Content = success; fetch the run ID
                logger.info("Workflow triggered successfully (HTTP 204)")
                run_id = await _get_latest_run_id(repo, branch)
                return True, "", run_id

            elif resp.status_code == 404:
                msg = (
                    f"Workflow '{settings.WORKFLOW_FILE}' not found in repo '{repo}'. "
                    f"Check that the file exists and has workflow_dispatch configured."
                )
                logger.error(msg)
                return False, msg, None

            elif resp.status_code == 422:
                detail = resp.json().get("message", resp.text)
                msg = f"Unprocessable request (422): {detail}"
                logger.error(msg)
                return False, msg, None

            elif resp.status_code == 401:
                msg = "GitHub token is invalid or expired. Regenerate your PAT."
                logger.error(msg)
                return False, msg, None

            elif resp.status_code == 403:
                msg = (
                    "Permission denied (403). Ensure your PAT has 'repo' and 'workflow' scopes."
                )
                logger.error(msg)
                return False, msg, None

            else:
                msg = f"Unexpected GitHub API response {resp.status_code}: {resp.text}"
                logger.error(msg)
                return False, msg, None

        except httpx.TimeoutException:
            msg = "Request to GitHub API timed out."
            logger.error(msg)
            return False, msg, None

        except httpx.RequestError as e:
            msg = f"Network error triggering workflow: {str(e)}"
            logger.error(msg)
            return False, msg, None


async def _get_latest_run_id(repo: str, branch: str) -> Optional[int]:
    """
    After triggering a dispatch, GitHub takes ~1-2s to create the run.
    Poll up to 5 times with 2s delay to get the latest run ID.
    """
    url = (
        f"{settings.GITHUB_API_BASE}/repos/{settings.GITHUB_OWNER}/{repo}"
        f"/actions/runs"
    )
    params = {"branch": branch, "per_page": 1}

    async with httpx.AsyncClient(timeout=15) as client:
        for attempt in range(5):
            await _async_sleep(2)
            try:
                resp = await client.get(url, headers=_auth_headers(), params=params)
                if resp.status_code == 200:
                    runs = resp.json().get("workflow_runs", [])
                    if runs:
                        run_id = runs[0]["id"]
                        logger.info(f"Got run ID: {run_id} (attempt {attempt + 1})")
                        return run_id
            except Exception as e:
                logger.warning(f"Error fetching run ID (attempt {attempt + 1}): {e}")

    logger.warning("Could not retrieve run ID after 5 attempts")
    return None


# ── Status ────────────────────────────────────────────────────────────────────

async def get_workflow_run_status(repo: str, run_id: int) -> dict:
    """Fetch the current status of a specific workflow run."""
    url = (
        f"{settings.GITHUB_API_BASE}/repos/{settings.GITHUB_OWNER}/{repo}"
        f"/actions/runs/{run_id}"
    )
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.get(url, headers=_auth_headers())
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "status": data.get("status", "unknown"),
                    "conclusion": data.get("conclusion"),
                    "workflow_name": data.get("name"),
                    "head_branch": data.get("head_branch"),
                    "created_at": data.get("created_at"),
                    "updated_at": data.get("updated_at"),
                    "workflow_url": data.get("html_url"),
                    "run_id": run_id,
                    "repo": repo,
                }
            elif resp.status_code == 404:
                return {"error": f"Run {run_id} not found in repo '{repo}'."}
            else:
                return {"error": f"GitHub API error {resp.status_code}: {resp.text}"}
        except httpx.RequestError as e:
            return {"error": f"Network error: {str(e)}"}


async def poll_workflow_until_complete(repo: str, run_id: int) -> dict:
    """
    Poll the run status until it completes or max attempts reached.
    Returns the final status dict.
    """
    logger.info(f"Polling run {run_id} in {repo} every {settings.POLL_INTERVAL_SECONDS}s...")

    for attempt in range(settings.POLL_MAX_ATTEMPTS):
        await _async_sleep(settings.POLL_INTERVAL_SECONDS)
        result = await get_workflow_run_status(repo, run_id)

        if "error" in result:
            logger.error(f"Poll error: {result['error']}")
            return result

        run_status = result.get("status")
        conclusion = result.get("conclusion")

        logger.info(
            f"  [{attempt + 1}/{settings.POLL_MAX_ATTEMPTS}] "
            f"status={run_status} conclusion={conclusion}"
        )

        if run_status == "completed":
            logger.info(f"Run {run_id} completed with conclusion: {conclusion}")
            return result

    logger.warning(f"Run {run_id} did not complete within polling window.")
    return {**result, "warning": "Polling timed out. Check GitHub Actions for final status."}


# ── Helper ────────────────────────────────────────────────────────────────────

async def _async_sleep(seconds: float):
    """Non-blocking sleep using asyncio."""
    import asyncio
    await asyncio.sleep(seconds)
