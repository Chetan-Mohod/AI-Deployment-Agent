"""
Pydantic Models — Request & Response schemas
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class DeploymentStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    TRIGGERED = "TRIGGERED"
    CANCELLED = "CANCELLED"


# ── Request Models ────────────────────────────────────────────────────────────

class NaturalLanguageRequest(BaseModel):
    """Accept a plain-English deployment request."""
    message: str = Field(
        ...,
        min_length=5,
        examples=["Deploy AI-Deployment-Agent 5.0.123 to qa from V5.0"],
    )


class StructuredDeployRequest(BaseModel):
    """Fully structured deployment request."""
    repo: str = Field(..., examples=["AI-Deployment-Agent"])
    branch: str = Field(default="V5.0", examples=["V5.0", "V6.0"])
    environment: str = Field(..., examples=["qa", "uat", "prod"])
    image_id: str = Field(..., examples=["5.0.123"])
    # Only required when deploying to prod
    prod_confirmation: Optional[str] = Field(
        default=None,
        description="Required for PROD: pass 'CONFIRM-PROD'",
    )

    @field_validator("environment")
    @classmethod
    def normalize_env(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("branch")
    @classmethod
    def normalize_branch(cls, v: str) -> str:
        return v.strip()


class UnifiedDeployRequest(BaseModel):
    """
    Accepts EITHER natural language OR structured fields.
    If 'message' is provided, AI parsing is used.
    If 'repo' + 'environment' + 'image_id' are provided, direct mode is used.
    """
    # Natural language
    message: Optional[str] = Field(default=None, examples=["Deploy 5.0.123 to qa"])

    # Structured fields
    repo: Optional[str] = Field(default=None, examples=["AI-Deployment-Agent"])
    branch: Optional[str] = Field(default=None, examples=["V5.0"])
    environment: Optional[str] = Field(default=None, examples=["qa"])
    image_id: Optional[str] = Field(default=None, examples=["5.0.123"])
    prod_confirmation: Optional[str] = Field(default=None)


# ── Response Models ───────────────────────────────────────────────────────────

class DeploymentResponse(BaseModel):
    status: DeploymentStatus
    repo: Optional[str] = None
    branch: Optional[str] = None
    environment: Optional[str] = None
    image_id: Optional[str] = None
    workflow: Optional[str] = None
    workflow_url: Optional[str] = None
    run_id: Optional[int] = None
    message: Optional[str] = None
    error: Optional[str] = None


class WorkflowStatusResponse(BaseModel):
    status: str
    repo: str
    run_id: int
    workflow_name: Optional[str] = None
    conclusion: Optional[str] = None
    workflow_url: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    head_branch: Optional[str] = None


class ParsedDeployment(BaseModel):
    """Structured output from the AI parsing layer."""
    repo: Optional[str] = None
    branch: Optional[str] = None
    environment: Optional[str] = None
    image_id: Optional[str] = None
    confidence: float = 0.0
    missing_fields: list[str] = []
    follow_up_question: Optional[str] = None
    is_prod: bool = False
    summary: Optional[str] = None
