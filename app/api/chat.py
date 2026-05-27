"""
Chat API Router
POST /api/v1/chat  — conversational deployment agent
GET  /api/v1/chat/session/{session_id} — get session state
"""

import logging
import uuid
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.config.settings import settings
from app.models.deployment_models import DeploymentStatus
from app.services import ai_service, deployment_service, github_service
from app.models.deployment_models import UnifiedDeployRequest

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory session store (for POC; replace with Redis for production)
_sessions: dict = {}


class ChatMessage(BaseModel):
    session_id: Optional[str] = None
    message: str


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    state: str  # "collecting" | "confirming" | "deploying" | "done" | "error"
    deployment: Optional[dict] = None


def _new_session(session_id: str):
    _sessions[session_id] = {
        "repo": None,
        "branch": None,
        "environment": None,
        "image_id": None,
        "prod_confirmation": None,
        "state": "collecting",
        "history": [],
    }
    return _sessions[session_id]


def _get_or_create(session_id: str) -> dict:
    if session_id not in _sessions:
        return _new_session(session_id)
    return _sessions[session_id]


def _missing(session: dict) -> list[str]:
    required = ["repo", "branch", "environment", "image_id"]
    return [f for f in required if not session.get(f)]


def _extract_from_message(message: str, session: dict) -> dict:
    """
    Rule-based extractor to pull values from user message
    and fill in any missing session fields.
    """
    import re
    msg = message.strip()
    msg_lower = msg.lower()
    updates = {}

    # Environment
    if not session.get("environment"):
        for env in settings.SUPPORTED_ENVIRONMENTS:
            if env in msg_lower:
                updates["environment"] = env
                break

    # Branch — look for V5.0, V6.0 style
    if not session.get("branch"):
        m = re.search(r"\bV(\d+\.\d+)\b", msg, re.IGNORECASE)
        if m:
            updates["branch"] = f"V{m.group(1)}"

    # Image ID — full format like 5.0.123 or 6.0.89
    if not session.get("image_id"):
        m = re.search(r"\b(\d+\.\d+\.\d+)\b", msg)
        if m:
            updates["image_id"] = m.group(1)
        else:
            # Bare PR number like "123" — expand using known branch
            branch = updates.get("branch") or session.get("branch") or settings.DEFAULT_BRANCH
            if branch.startswith("V"):
                version = branch.lstrip("V")
                m2 = re.search(r"\b(\d{2,4})\b", msg)
                if m2:
                    updates["image_id"] = f"{version}.{m2.group(1)}"

    # Repo
    if not session.get("repo"):
        for repo in settings.SUPPORTED_REPOS:
            if repo.lower() in msg_lower:
                updates["repo"] = repo
                break
        # If only one repo configured, default to it
        if not updates.get("repo") and len(settings.SUPPORTED_REPOS) == 1:
            updates["repo"] = settings.SUPPORTED_REPOS[0]

    return updates


def _build_summary(session: dict) -> str:
    return (
        f"📋 **Deployment Summary**\n\n"
        f"• **Repo:** {session['repo']}\n"
        f"• **Branch:** {session['branch']}\n"
        f"• **Environment:** {session['environment'].upper()}\n"
        f"• **Image ID:** {session['image_id']}\n\n"
        + ("⚠️  **This is a PROD deployment!**\n\n" if session['environment'] == 'prod' else "")
        + "Type **yes** to confirm and deploy, or **no** to cancel."
    )


@router.post("/chat", response_model=ChatResponse, summary="Conversational deployment agent")
async def chat(msg: ChatMessage) -> ChatResponse:
    """
    Stateful conversational agent. Send messages naturally:
    - 'deploy to qa'
    - 'image is 5.0.123'
    - 'branch V5.0'
    - 'yes' to confirm
    """
    session_id = msg.session_id or str(uuid.uuid4())
    session = _get_or_create(session_id)
    text = msg.message.strip()
    text_lower = text.lower()

    # ── Handle reset / cancel ────────────────────────────────────────────────
    if text_lower in ("reset", "cancel", "start over", "restart"):
        _new_session(session_id)
        return ChatResponse(
            session_id=session_id,
            reply="🔄 Restarted! Let's begin again.\n\nWhich environment do you want to deploy to? (`dev`, `qa`, `uat`, `prod`)",
            state="collecting",
        )

    # ── Confirmation state ───────────────────────────────────────────────────
    if session["state"] == "confirming":
        if text_lower in ("yes", "y", "confirm", "deploy", "go", "proceed"):

            # PROD extra confirmation
            if session["environment"] == "prod" and settings.PROD_CONFIRMATION_REQUIRED:
                if session.get("prod_confirmation") != settings.PROD_CONFIRMATION_TOKEN:
                    session["prod_confirmation"] = settings.PROD_CONFIRMATION_TOKEN

            session["state"] = "deploying"

            # Validate image ID before triggering
            ok, err = settings.validate_image_id(session["branch"], session["image_id"])
            if not ok:
                session["state"] = "collecting"
                session["image_id"] = None
                return ChatResponse(
                    session_id=session_id,
                    reply=f"❌ {err}\n\nPlease provide a valid image ID.",
                    state="collecting",
                )

            # Trigger deployment
            success, error_msg, run_id = await github_service.trigger_workflow(
                repo=session["repo"],
                branch=session["branch"],
                environment=session["environment"],
                image_id=session["image_id"],
            )

            if success:
                workflow_url = settings.get_workflow_url(session["repo"], run_id) if run_id else "Check GitHub Actions"
                session["state"] = "done"
                return ChatResponse(
                    session_id=session_id,
                    reply=(
                        f"✅ **Deployment triggered successfully!**\n\n"
                        f"🔗 [View on GitHub Actions]({workflow_url})\n"
                        f"🆔 Run ID: `{run_id}`\n\n"
                        f"Type **reset** to start a new deployment."
                    ),
                    state="done",
                    deployment={
                        "repo": session["repo"],
                        "branch": session["branch"],
                        "environment": session["environment"],
                        "image_id": session["image_id"],
                        "run_id": run_id,
                        "workflow_url": workflow_url,
                    },
                )
            else:
                session["state"] = "error"
                return ChatResponse(
                    session_id=session_id,
                    reply=f"❌ **Deployment failed:**\n\n{error_msg}\n\nType **reset** to try again.",
                    state="error",
                )

        elif text_lower in ("no", "n", "cancel", "abort"):
            _new_session(session_id)
            return ChatResponse(
                session_id=session_id,
                reply="❌ Deployment cancelled.\n\nType **reset** to start over.",
                state="collecting",
            )
        else:
            return ChatResponse(
                session_id=session_id,
                reply=_build_summary(session) + "\n\n_(Type **yes** to deploy or **no** to cancel)_",
                state="confirming",
            )

    # ── Collecting state — extract fields from message ───────────────────────
    updates = _extract_from_message(text, session)
    session.update({k: v for k, v in updates.items() if v})

    missing = _missing(session)

    if not missing:
        # Validate image vs branch
        ok, err = settings.validate_image_id(session["branch"], session["image_id"])
        if not ok:
            session["image_id"] = None
            return ChatResponse(
                session_id=session_id,
                reply=f"⚠️ {err}\n\nWhat is the correct image ID?",
                state="collecting",
            )

        session["state"] = "confirming"
        return ChatResponse(
            session_id=session_id,
            reply=_build_summary(session),
            state="confirming",
        )

    # Still collecting — ask for next missing field
    prompts = {
        "environment": "🌍 Which **environment** do you want to deploy to?\n`dev` · `qa` · `uat` · `prod`",
        "branch":      "🌿 Which **branch** should be used?\n`V5.0` · `V6.0`",
        "image_id":    f"🐳 What is the **image ID** (PR/build number)?\n{'Example: ' + (session['branch'] or 'V5.0').lstrip('V') + '.123' if session.get('branch') else 'Example: 5.0.123'}",
        "repo":        f"📦 Which **repository**?\n{' · '.join(settings.SUPPORTED_REPOS)}",
    }

    next_field = missing[0]
    filled = [f for f in ["repo", "branch", "environment", "image_id"] if session.get(f)]
    progress = ""
    if filled:
        progress = "Got so far: " + " | ".join(
            f"**{f}**: `{session[f]}`" for f in filled
        ) + "\n\n"

    return ChatResponse(
        session_id=session_id,
        reply=progress + prompts[next_field],
        state="collecting",
    )
