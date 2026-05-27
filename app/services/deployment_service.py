"""
Deployment Service
Orchestrates: AI parsing → validation → GitHub trigger → response
"""

import logging
from typing import Optional

from app.config.settings import settings
from app.models.deployment_models import (
    DeploymentResponse,
    DeploymentStatus,
    ParsedDeployment,
    UnifiedDeployRequest,
)
from app.services import ai_service, github_service

logger = logging.getLogger(__name__)


async def handle_deploy_request(request: UnifiedDeployRequest) -> DeploymentResponse:
    """
    Main orchestration entry point.

    Flow:
    1. Determine mode: AI parse (if message provided) vs direct structured input
    2. Validate all parameters
    3. PROD safety check
    4. Trigger GitHub workflow
    5. Return response with run URL
    """

    # ── Step 1: Parse / Extract parameters ──────────────────────────────────
    if request.message:
        logger.info(f"Natural language mode: '{request.message}'")
        parsed = await ai_service.parse_deployment_request(request.message)

        if parsed.missing_fields:
            return DeploymentResponse(
                status=DeploymentStatus.FAILED,
                error=f"Missing required fields: {', '.join(parsed.missing_fields)}",
                message=parsed.follow_up_question,
            )

        repo = parsed.repo
        branch = parsed.branch or settings.DEFAULT_BRANCH
        environment = parsed.environment
        image_id = parsed.image_id

    else:
        logger.info("Structured input mode")
        repo = request.repo
        branch = request.branch or settings.DEFAULT_BRANCH
        environment = request.environment
        image_id = request.image_id

    # ── Step 2: Validate required fields ────────────────────────────────────
    if not repo:
        return _error("'repo' is required.")
    if not environment:
        return _error("'environment' is required.")
    if not image_id:
        return _error("'image_id' is required.")

    environment = settings.normalize_environment(environment)

    # ── Step 3: Config-level validation ─────────────────────────────────────
    if not settings.is_valid_repo(repo):
        return _error(
            f"Repository '{repo}' is not in the supported list: {settings.SUPPORTED_REPOS}"
        )

    if not settings.is_valid_branch(branch):
        return _error(
            f"Branch '{branch}' is not in the supported list: {settings.SUPPORTED_BRANCHES}"
        )

    if not settings.is_valid_environment(environment):
        return _error(
            f"Environment '{environment}' is not supported. "
            f"Choose from: {settings.SUPPORTED_ENVIRONMENTS}"
        )

    # ── Step 4: Image ID format validation ──────────────────────────────────
    valid_img, img_error = settings.validate_image_id(branch, image_id)
    if not valid_img:
        return _error(img_error)

    # ── Step 5: PROD safety check ────────────────────────────────────────────
    if environment == "prod" and settings.PROD_CONFIRMATION_REQUIRED:
        confirmation = request.prod_confirmation
        if confirmation != settings.PROD_CONFIRMATION_TOKEN:
            return DeploymentResponse(
                status=DeploymentStatus.FAILED,
                repo=repo,
                branch=branch,
                environment=environment,
                image_id=image_id,
                error=(
                    "PROD deployment requires explicit confirmation. "
                    f"Add 'prod_confirmation': '{settings.PROD_CONFIRMATION_TOKEN}' to your request."
                ),
            )

    # ── Step 6: GitHub repo/branch existence check ──────────────────────────
    repo_ok, repo_err = await github_service.validate_repo_exists(repo)
    if not repo_ok:
        return _error(repo_err)

    branch_ok, branch_err = await github_service.validate_branch_exists(repo, branch)
    if not branch_ok:
        return _error(branch_err)

    # ── Step 7: Trigger workflow ─────────────────────────────────────────────
    logger.info(
        f"Triggering deployment | repo={repo} branch={branch} "
        f"env={environment} image={image_id}"
    )

    success, error_msg, run_id = await github_service.trigger_workflow(
        repo=repo,
        branch=branch,
        environment=environment,
        image_id=image_id,
    )

    if not success:
        return DeploymentResponse(
            status=DeploymentStatus.FAILED,
            repo=repo,
            branch=branch,
            environment=environment,
            image_id=image_id,
            workflow=settings.WORKFLOW_FILE,
            error=error_msg,
        )

    # ── Step 8: Build success response ──────────────────────────────────────
    workflow_url = None
    if run_id:
        workflow_url = settings.get_workflow_url(repo, run_id)

    summary = await ai_service.generate_deployment_summary(
        repo, branch, environment, image_id
    )

    logger.info(f"Deployment triggered successfully | run_id={run_id} url={workflow_url}")

    return DeploymentResponse(
        status=DeploymentStatus.TRIGGERED,
        repo=repo,
        branch=branch,
        environment=environment,
        image_id=image_id,
        workflow=f"AKS-CD ({settings.WORKFLOW_FILE})",
        workflow_url=workflow_url,
        run_id=run_id,
        message=summary,
    )


def _error(msg: str) -> DeploymentResponse:
    logger.warning(f"Deployment validation error: {msg}")
    return DeploymentResponse(status=DeploymentStatus.FAILED, error=msg)
