"""
Configuration & Settings
All configurable values live here. Edit this file to add repos, branches, environments.
"""

import os
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── GitHub ──────────────────────────────────────────────────────────────
    # REQUIRED: Set your GitHub org or personal account name
    GITHUB_OWNER: str = "Chetan-Mohod"

    # REQUIRED: Set in .env file — NEVER hardcode here
    GITHUB_TOKEN: str = ""

    # Workflow file name inside .github/workflows/ of each repo
    WORKFLOW_FILE: str = "AKS-CD.yml"

    # GitHub API base URL (change for GitHub Enterprise)
    GITHUB_API_BASE: str = "https://api.github.com"

    # ── Supported Repos ─────────────────────────────────────────────────────
    # Add or remove repository names here (just the repo name, not full URL)
    SUPPORTED_REPOS: List[str] = [
        "AI-Deployment-Agent",
        "billing-service",
        "payment-service",
        "auth-service",
    ]

    # ── Supported Branches ──────────────────────────────────────────────────
    # Branch names your team uses. The agent validates against this list.
    SUPPORTED_BRANCHES: List[str] = [
        "V5.0",
        "V6.0",
        "main",
        "develop",
        "release",
    ]

    # Default branch when none is specified
    DEFAULT_BRANCH: str = "V5.0"

    # ── Supported Environments ──────────────────────────────────────────────
    # Must match the 'options' values in your AKS-CD.yml workflow_dispatch
    SUPPORTED_ENVIRONMENTS: List[str] = ["dev", "qa", "uat", "prod"]

    # ── PROD Safety ─────────────────────────────────────────────────────────
    # When True, PROD deployments require an explicit confirmation token
    PROD_CONFIRMATION_REQUIRED: bool = True
    PROD_CONFIRMATION_TOKEN: str = "CONFIRM-PROD"

    # ── OpenAI ──────────────────────────────────────────────────────────────
    # REQUIRED: Set in .env — NEVER hardcode here
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_MAX_TOKENS: int = 1000

    # ── Polling ─────────────────────────────────────────────────────────────
    # How many seconds to wait between status polls, and max attempts
    POLL_INTERVAL_SECONDS: int = 10
    POLL_MAX_ATTEMPTS: int = 30

    # ── App ─────────────────────────────────────────────────────────────────
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True

    # ── Derived helpers ─────────────────────────────────────────────────────
    def get_workflow_url(self, repo: str, run_id: int) -> str:
        return (
            f"https://github.com/{self.GITHUB_OWNER}/{repo}"
            f"/actions/runs/{run_id}"
        )

    def normalize_environment(self, env: str) -> str:
        """Normalize environment string to lowercase."""
        return env.strip().lower()

    def is_valid_repo(self, repo: str) -> bool:
        return repo in self.SUPPORTED_REPOS

    def is_valid_branch(self, branch: str) -> bool:
        return branch in self.SUPPORTED_BRANCHES

    def is_valid_environment(self, env: str) -> bool:
        return self.normalize_environment(env) in self.SUPPORTED_ENVIRONMENTS

    def validate_image_id(self, branch: str, image_id: str) -> tuple[bool, str]:
        """
        Validate that image_id matches the branch version pattern.

        Branch V5.0  → image must start with 5.0.
        Branch V6.0  → image must start with 6.0.
        Branch main  → no version prefix check (free-form)
        """
        if not branch.startswith("V"):
            return True, ""

        version = branch.lstrip("V")          # "V5.0" → "5.0"
        expected_prefix = f"{version}."

        if not image_id.startswith(expected_prefix):
            return False, (
                f"Image ID '{image_id}' does not match branch '{branch}'. "
                f"Expected format: {expected_prefix}<PR_number>  "
                f"(e.g. {expected_prefix}123)"
            )
        return True, ""


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings: Settings = get_settings()
