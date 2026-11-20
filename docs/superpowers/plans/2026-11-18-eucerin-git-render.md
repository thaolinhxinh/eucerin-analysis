# EUCERIN GitHub to Render Deployment Implementation Plan

> **For agentic workers:** Execute this plan task-by-task in the current workspace.

**Goal:** Prepare the existing FastAPI project for a safe private GitHub repository with Render Docker auto-deploy from `main` and persistent production run storage.

**Architecture:** Preserve the existing app/model/n8n layout and the working API. Exclude credentials, local databases, the historical source CSV, and generated outputs from Git and the Docker image; keep the 3.4 MB frozen model and required metric reference files. Document GitHub-to-Render setup and local verification limits.

**Tech Stack:** Git, GitHub, Render Blueprints, Docker, FastAPI, pytest, n8n JSON.

**Spec:** User-provided requirements in `Pasted text.txt` (external attachment).

## Global Constraints

- Push only to a verified private GitHub repository owned by the authenticated account.
- Do not overwrite existing Git history or use force push.
- Render uses Docker, binds `0.0.0.0:$PORT`, checks `/health`, and auto-deploys commits on `main`.
- Keep SQLite and generated run files under `/app/storage`, backed by a paid persistent disk.
- Never commit `.env`, secrets, credentials, real databases, logs/caches, or sensitive source/output datasets.
- Do not auto-retrain the model during deployment.

## Review Focus

- A clean checkout must not need the ignored private source CSV just to run the app; API inference still requires the caller's CSV.
- Docker image must contain the frozen model and metric CSVs used by report generation, without bundling the full historical source dataset.
- The production Render Blueprint must continue to attach storage at the application's exact `STORAGE_DIR`.
- Tests and n8n JSON must be committed even though they are not copied into the production image.
- Render setup must not be claimed complete without a verified GitHub repository and Render deployment evidence.

## File Map

- Create `.gitignore` for credentials, local runtime state, caches, and private/generated data.
- Update `.dockerignore` to keep test/n8n/docs out of the image and omit the sensitive dataset.
- Update `Dockerfile` to copy only runtime metric references, model, and app.
- Update `render.yaml` to explicitly link `main` and preserve paid persistent storage.
- Update `tests/test_api.py` to accept an external private CSV path and skip dataset-dependent integration checks when absent.
- Add `docs/GIT_GITHUB_RENDER_DEPLOYMENT.md` and update README onboarding.
- Keep FastAPI behavior, model schema, n8n payloads, and notebook training behavior unchanged.

## Tasks

### Task 1: Secure repository and Docker packaging

- Add `.gitignore` patterns for `.env*` (except `.env.example`), storage/database files, caches, raw private data, and generated `sample_outputs`.
- Ensure `.dockerignore` excludes source data and non-runtime files while allowing `reference/Validation_Metrics.csv` and `reference/Holdout_Metrics.csv`.
- Change Dockerfile to copy only the two metric CSVs required by `app/reporting.py`.
- Add assertions to `tests/test_render_package.py` for these packaging rules.
- Verify the 3.4 MB model is below GitHub's 100 MiB individual file rejection limit.

### Task 2: Reproducible tests and deployment instructions

- Allow `EUCERIN_TEST_DATA` to point to the ignored source CSV; default to the workspace copy.
- Skip source-data integration cases clearly when neither path exists, while retaining structural/security tests.
- Add Vietnamese deployment instructions for private repo creation/authentication, Render Blueprint setup, auto-deploy, env vars, log triage, rollback, and model version updates.
- Update README's initial deployment steps to use Git/GitHub, not ZIP upload.
- Verify Render Blueprint, Docker startup command, n8n workflow JSON, Python imports, pytest, and Node workflow checks when tools are available.

### Task 3: Local Git and remote gate

- Initialize Git only after ignore rules and secret scan are verified; preserve all workspace content and do not reinitialize an existing repo.
- Stage and inspect `git status` and `git diff --cached`; verify no private data/secrets are staged.
- Commit the deployment setup locally.
- Push only if an authenticated account and verified private origin are available; otherwise provide exact next steps without inventing an owner or claiming deployment.

## Interfaces

- `EUCERIN_TEST_DATA` is an optional filesystem path consumed by integration tests.
- Runtime settings remain `MODEL_DIR=/app/models`, `STORAGE_DIR=/app/storage`, and Render-provided `PORT` and `ML_API_KEY`.
