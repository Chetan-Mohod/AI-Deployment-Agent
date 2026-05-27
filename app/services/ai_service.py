"""
AI Service
Uses OpenAI to parse natural language deployment requests into structured parameters.
Falls back gracefully if OpenAI key is not configured.
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

from app.config.settings import settings
from app.models.deployment_models import ParsedDeployment

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "deployment_prompt.txt"


def _load_prompt_template() -> str:
    try:
        return _PROMPT_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning("deployment_prompt.txt not found, using inline prompt.")
        return _DEFAULT_PROMPT


_DEFAULT_PROMPT = """
You are a deployment assistant. Extract repo, branch, environment, image_id from the user message.
Respond ONLY with JSON: {"repo":null,"branch":null,"environment":null,"image_id":null,
"confidence":0.0,"missing_fields":[],"follow_up_question":null,"is_prod":false,"summary":null}
"""


def _build_system_prompt() -> str:
    template = _load_prompt_template()
    return template.format(
        supported_repos=settings.SUPPORTED_REPOS,
        supported_branches=settings.SUPPORTED_BRANCHES,
        supported_environments=settings.SUPPORTED_ENVIRONMENTS,
        default_branch=settings.DEFAULT_BRANCH,
    )


async def parse_deployment_request(message: str) -> ParsedDeployment:
    """
    Parse a natural language deployment message using OpenAI.
    Returns a ParsedDeployment with extracted fields.

    If OPENAI_API_KEY is not set, falls back to basic regex parsing.
    """
    if not settings.OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY not set — using basic fallback parser.")
        return _fallback_parse(message)

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url="https://api.groq.com/openai/v1"
        )

        system_prompt = _build_system_prompt()

        response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            max_tokens=settings.OPENAI_MAX_TOKENS,
            temperature=0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ],
        )

        raw = response.choices[0].message.content.strip()
        logger.debug(f"OpenAI raw response: {raw}")

        # Strip markdown code fences if present
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1]) if len(lines) > 2 else raw

        parsed_dict = json.loads(raw)
        result = ParsedDeployment(**parsed_dict)
        logger.info(
            f"AI parsed: repo={result.repo} branch={result.branch} "
            f"env={result.environment} image={result.image_id} "
            f"confidence={result.confidence}"
        )
        return result

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse OpenAI JSON response: {e}")
        return _fallback_parse(message)

    except Exception as e:
        logger.error(f"OpenAI call failed: {e}")
        return _fallback_parse(message)


def _fallback_parse(message: str) -> ParsedDeployment:
    """
    Basic rule-based fallback parser when OpenAI is unavailable.
    Extracts version-like patterns and environment keywords.
    """
    import re

    msg_lower = message.lower()
    result = ParsedDeployment()
    result.confidence = 0.5
    missing = []

    # ── Environment ────────────────────────────────────────────────────────
    for env in settings.SUPPORTED_ENVIRONMENTS:
        if env.lower() in msg_lower:
            result.environment = env.lower()
            result.is_prod = env.lower() == "prod"
            break
    if not result.environment:
        missing.append("environment")

    # ── Branch ────────────────────────────────────────────────────────────
    branch_match = re.search(r"\bV(\d+\.\d+)\b", message, re.IGNORECASE)
    if branch_match:
        result.branch = f"V{branch_match.group(1)}"
    else:
        result.branch = settings.DEFAULT_BRANCH

    # ── Image ID ──────────────────────────────────────────────────────────
    # Match patterns like: 5.0.123, 5.0.45, 6.0.89, or bare numbers
    image_match = re.search(r"\b(\d+\.\d+\.\d+)\b", message)
    if image_match:
        result.image_id = image_match.group(1)
    else:
        bare_num = re.search(r"\b(\d{2,4})\b", message)
        if bare_num and result.branch and result.branch.startswith("V"):
            version = result.branch.lstrip("V")
            result.image_id = f"{version}.{bare_num.group(1)}"
        else:
            missing.append("image_id")

    # ── Repo ──────────────────────────────────────────────────────────────
    for repo in settings.SUPPORTED_REPOS:
        if repo.lower() in msg_lower:
            result.repo = repo
            break
    if not result.repo:
        missing.append("repo")

    result.missing_fields = missing

    if missing:
        result.follow_up_question = (
            f"I couldn't determine: {', '.join(missing)}. "
            f"Could you please provide them?"
        )
        result.confidence = max(0.3, result.confidence - 0.1 * len(missing))

    if not missing:
        result.summary = (
            f"Deploy {result.repo} image {result.image_id} "
            f"to {result.environment} from branch {result.branch}"
        )

    return result


async def generate_deployment_summary(
    repo: str,
    branch: str,
    environment: str,
    image_id: str,
) -> str:
    """Generate a human-friendly deployment summary."""
    env_upper = environment.upper()
    prod_warning = " ⚠️  PRODUCTION DEPLOYMENT" if environment.lower() == "prod" else ""
    return (
        f"Deploying {repo} | Branch: {branch} | "
        f"Image: {image_id} | Environment: {env_upper}{prod_warning}"
    )
