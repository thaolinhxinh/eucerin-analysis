# Eucerin Vercel End-to-End Completion Plan

> **Execution:** Inline in the current workspace, as requested. Run tests before and after changes; commit and push verified changes to `main` only after secret and diff review.

## Scope and constraints

- Keep the existing Vercel project, GitHub repository, frozen model, and Chapter 6 metrics.
- Prove production health and a real prediction using the approved historical CSV only; do not send Telegram messages or modify Google Drive.
- Add a Vercel-specific importable n8n workflow using the verified production host and explicit credential placeholders.
- Add tests, setup guides, API/E2E reports, and Chapter 7 implementation notes that distinguish verified behavior from pending OAuth/credential steps.
- Do not put credentials or the private historical CSV in Git. Do not claim n8n/Drive/Telegram/Power BI service execution without credentials and an actual run.

## Tasks

1. Prepare a compatible Python environment; run existing test and workflow checks; verify deployment health and capture a real model response.
2. Add readiness detail to `/health` if tests show it is missing; add focused regression coverage for API, validation, idempotency, and output contracts.
3. Create `n8n/EUCERIN_Vercel_EndToEnd.json` and `n8n/EUCERIN_Vercel_Error_Handler.json` from existing workflows, with the verified production host and no credentials, while preserving manual/scheduled triggers, retries, Drive acknowledgements, and one-time Telegram reservation.
4. Create requested setup and evidence documents for Vercel, n8n, Drive, Telegram, Power BI, E2E checks, and Chapter 7; update `.env.example` and README.
5. Run the full test suite, JavaScript workflow checks, production health and prediction checks; inspect Git diff and secrets; commit and push to the linked `kl3485058-jpg` repository; verify Auto-Deploy and health.

## Verification contract

- Local unit/integration tests must use the real private CSV when it is available locally, with no changes to its contents.
- Production prediction uses the production key only from the ignored local environment file and reports no secret values.
- n8n execution remains pending until real Google Drive and Telegram credentials are configured by the owner.
- Reports label all evidence by date and clearly list service setup still required.
