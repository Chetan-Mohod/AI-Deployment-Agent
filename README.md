# AI Deployment Agent

Trigger GitHub Actions deployment workflows using **natural language** or **structured JSON** — no browser, no manual clicks. Built with FastAPI + OpenAI + GitHub Actions Workflow Dispatch API.

---

## How It Works

```
User Input (NL or JSON)
        ↓
  AI Parsing Layer (OpenAI)
        ↓
  Validation (repo / branch / image ID / env)
        ↓
  PROD Safety Check
        ↓
  GitHub Actions API (workflow_dispatch)
        ↓
  Return run URL + status
```

### Image ID Validation Rule

Your `AKS-CD.yml` validates image IDs against the branch. This agent enforces the same rule **before** triggering:

| Branch | Image ID must start with | Example |
|--------|--------------------------|---------|
| V5.0   | `5.0.`                   | `5.0.123` |
| V6.0   | `6.0.`                   | `6.0.89`  |
| main   | no restriction           | anything  |

---

## Project Structure

```
ai-deployment-agent/
├── run.py                         # Start server
├── requirements.txt
├── .env.example                   # Copy to .env and fill in
│
└── app/
    ├── main.py                    # FastAPI app, CORS, global error handler
    │
    ├── api/
    │   ├── deploy.py              # POST /api/v1/deploy
    │   └── status.py              # GET  /api/v1/status/{repo}/{run_id}
    │
    ├── services/
    │   ├── github_service.py      # GitHub API: trigger, validate, poll
    │   ├── deployment_service.py  # Orchestration: parse → validate → trigger
    │   └── ai_service.py          # OpenAI parsing + fallback parser
    │
    ├── config/
    │   └── settings.py            # ← ALL config lives here
    │
    ├── prompts/
    │   └── deployment_prompt.txt  # System prompt for OpenAI
    │
    ├── utils/
    │   └── validators.py          # Image ID / branch helpers
    │
    └── models/
        └── deployment_models.py   # Pydantic request/response schemas
```

---

## Quick Setup

### 1. Clone and install

```bash
git clone https://github.com/Chetan-Mohod/AI-Deployment-Agent.git
cd AI-Deployment-Agent
pip install -r requirements.txt
```

### 2. Create your .env file

```bash
cp .env.example .env
```

Open `.env` and set:

```env
GITHUB_TOKEN=ghp_your_new_token_here
OPENAI_API_KEY=sk-your_openai_key_here   # optional but enables natural language
GITHUB_OWNER=Chetan-Mohod
```

### 3. GitHub PAT Token Setup

Go to: **GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)**

Click **Generate new token (classic)** and select these scopes:

- ✅ `repo` — read/write repo access
- ✅ `workflow` — trigger GitHub Actions workflows

Set expiry to 90 days for POC. Copy the token and paste into `.env`.

> ⚠️ **Never commit your .env file.** It is already in `.gitignore`.

### 4. Run the server

```bash
python run.py
```

Server starts at: `http://localhost:8000`

Interactive API docs: `http://localhost:8000/docs`

---

## API Reference

### POST /api/v1/deploy

Accepts natural language OR structured JSON.

#### Option A — Natural Language

```bash
curl -X POST http://localhost:8000/api/v1/deploy \
  -H "Content-Type: application/json" \
  -d '{"message": "Deploy AI-Deployment-Agent 5.0.123 to qa"}'
```

More examples:

```bash
# Deploy with explicit branch
curl -X POST http://localhost:8000/api/v1/deploy \
  -H "Content-Type: application/json" \
  -d '{"message": "Deploy AI-Deployment-Agent image 5.0.45 to uat from V5.0"}'

# V6.0 branch deployment
curl -X POST http://localhost:8000/api/v1/deploy \
  -H "Content-Type: application/json" \
  -d '{"message": "Deploy AI-Deployment-Agent 6.0.89 to dev from V6.0"}'
```

#### Option B — Structured JSON

```bash
curl -X POST http://localhost:8000/api/v1/deploy \
  -H "Content-Type: application/json" \
  -d '{
    "repo": "AI-Deployment-Agent",
    "branch": "V5.0",
    "environment": "qa",
    "image_id": "5.0.123"
  }'
```

#### PROD Deployment (requires confirmation)

```bash
curl -X POST http://localhost:8000/api/v1/deploy \
  -H "Content-Type: application/json" \
  -d '{
    "repo": "AI-Deployment-Agent",
    "branch": "V5.0",
    "environment": "prod",
    "image_id": "5.0.123",
    "prod_confirmation": "CONFIRM-PROD"
  }'
```

#### Success Response

```json
{
  "status": "TRIGGERED",
  "repo": "AI-Deployment-Agent",
  "branch": "V5.0",
  "environment": "qa",
  "image_id": "5.0.123",
  "workflow": "AKS-CD (AKS-CD.yml)",
  "workflow_url": "https://github.com/Chetan-Mohod/AI-Deployment-Agent/actions/runs/12345678",
  "run_id": 12345678,
  "message": "Deploying AI-Deployment-Agent | Branch: V5.0 | Image: 5.0.123 | Environment: QA"
}
```

#### Failure Response

```json
{
  "status": "FAILED",
  "error": "Image ID '6.0.123' does not match branch 'V5.0'. Expected format: 5.0.<PR_number>"
}
```

---

### GET /api/v1/status/{repo}/{run_id}

Single status fetch.

```bash
curl http://localhost:8000/api/v1/status/AI-Deployment-Agent/12345678
```

Response:
```json
{
  "status": "in_progress",
  "conclusion": null,
  "workflow_name": "AKS-CD",
  "head_branch": "V5.0",
  "workflow_url": "https://github.com/Chetan-Mohod/AI-Deployment-Agent/actions/runs/12345678",
  "run_id": 12345678,
  "repo": "AI-Deployment-Agent"
}
```

---

### GET /api/v1/status/{repo}/{run_id}/poll

Polls until the run completes (blocking).

```bash
curl http://localhost:8000/api/v1/status/AI-Deployment-Agent/12345678/poll
```

---

### GET /health

```bash
curl http://localhost:8000/health
```

---

## Configuration Guide

All configuration is in `app/config/settings.py`.

### Add a new repository

```python
SUPPORTED_REPOS: List[str] = [
    "AI-Deployment-Agent",
    "billing-service",
    "your-new-service",   # ← add here
]
```

### Add a new environment

```python
SUPPORTED_ENVIRONMENTS: List[str] = ["dev", "qa", "uat", "prod", "staging"]
#                                                                  ^^^^^^^^
```

> Also add it to the `options:` list in your `AKS-CD.yml` workflow file.

### Add a new branch

```python
SUPPORTED_BRANCHES: List[str] = [
    "V5.0",
    "V6.0",
    "V7.0",   # ← add here
    "main",
]
```

### Change the workflow file

```python
WORKFLOW_FILE: str = "AKS-CD.yml"
```

Or via `.env`:
```env
WORKFLOW_FILE=End-to-End-DB-CD.yml
```

### Disable PROD confirmation

```python
PROD_CONFIRMATION_REQUIRED: bool = False
```

---

## Validation Rules Summary

| Check | Rule |
|-------|------|
| Repo | Must be in `SUPPORTED_REPOS` |
| Branch | Must be in `SUPPORTED_BRANCHES` |
| Environment | Must be in `SUPPORTED_ENVIRONMENTS` (case-insensitive) |
| Image ID | For `V5.0` branch → must start with `5.0.` |
| Image ID | For `V6.0` branch → must start with `6.0.` |
| PROD deploy | Requires `prod_confirmation: "CONFIRM-PROD"` |
| GitHub repo | Verified to exist via GitHub API |
| GitHub branch | Verified to exist in the repo via GitHub API |

---

## Security Notes

- PAT token is never logged or returned in any API response
- All values are read from environment variables — never hardcoded
- PROD deployments require an explicit confirmation token
- Repository and branch names are validated against allowlists before any API call

---

## Running Without OpenAI

The agent works without an OpenAI key. A built-in regex-based fallback parser handles:
- Version patterns like `5.0.123`, `6.0.89`
- Environment keywords: `dev`, `qa`, `uat`, `prod`
- Branch names like `V5.0`, `V6.0`
- Repo name matching from the supported list

To use it, just leave `OPENAI_API_KEY` empty in `.env`.
