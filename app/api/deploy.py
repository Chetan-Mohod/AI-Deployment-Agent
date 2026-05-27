"""
Deploy API Router
POST /api/v1/deploy
"""

import logging

from fastapi import APIRouter, HTTPException

from app.models.deployment_models import DeploymentResponse, UnifiedDeployRequest
from app.services import deployment_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/deploy",
    response_model=DeploymentResponse,
    summary="Trigger a GitHub Actions deployment",
    description="""
Accepts **either** a natural language message **or** structured JSON fields.

**Natural language examples:**
- `{"message": "Deploy AI-Deployment-Agent 5.0.123 to qa"}`
- `{"message": "Deploy image 5.0.45 to uat from V5.0"}`

**Structured input:**
```json
{
  "repo": "AI-Deployment-Agent",
  "branch": "V5.0",
  "environment": "qa",
  "image_id": "5.0.123"
}
```

**PROD deployments** require an extra field:
```json
{ ..., "prod_confirmation": "CONFIRM-PROD" }
```
""",
)
async def deploy(request: UnifiedDeployRequest) -> DeploymentResponse:
    """Trigger a deployment workflow."""
    logger.info(f"Received deploy request: {request.model_dump(exclude_none=True)}")

    if not request.message and not (request.repo and request.environment and request.image_id):
        raise HTTPException(
            status_code=422,
            detail=(
                "Provide either 'message' (natural language) "
                "or structured fields: 'repo', 'environment', 'image_id'."
            ),
        )

    return await deployment_service.handle_deploy_request(request)
