# Deploy Eucerin ML API to Vercel

This repository can deploy its FastAPI service to Vercel. Vercel is the primary
deployment target for this guide; `render.yaml` remains available for existing
Render deployments.

The project pins Python 3.12 in `.python-version` to keep builds stable across
changes to Vercel's default Python runtime.

## What the deployment needs

- A Vercel project connected to this private GitHub repository and its `main`
  branch. Pushes to `main` trigger production deployments.
- A Postgres database connected through Vercel Marketplace. The API uses
  `DATABASE_URL` to store run state and upload acknowledgements across
  serverless instances.
- A **private** Vercel Blob store connected to the project. The API stores
  generated CSV artifacts there and reads them through authenticated API
  requests. Vercel supplies the Blob connection variables when the store is
  connected.
- `ML_API_KEY` and `APP_MODE=production` in the Vercel project's Production
  Environment Variables. Set a separate API key for Preview deployments, and
  avoid pointing previews at production data unless intended.

The API is configured for the Singapore region (`sin1`) and a 300 second
function duration. Vercel's request/response limit is 4.5 MB; this service
rejects input CSVs larger than 4 MiB on Vercel to leave room for multipart
overhead. The current approved historical source is about 3 MB. Larger input
files need a direct-to-object-storage upload flow before they can be used.

## Set up the Vercel project

1. The existing Vercel project is `kien-e0d4/eucerin-ml-automation`, linked to
   the private repository `kl3485058-jpg/eucerin-ml-automation`. Choose `main` as the
   Production Branch and keep the repository root as the Root Directory.
2. Add/connect a Postgres database from Vercel Marketplace. Select a Singapore
   region when offered and ensure the project receives `DATABASE_URL` for the
   environments you plan to use.
3. Add/connect a **private** Blob store to the project. Ensure Vercel provides
   its Blob store variables to the deployment.
4. In Project Settings → Environment Variables, add `ML_API_KEY` with a long,
   random secret and `APP_MODE` set to `production` for Production. Add
   environment-appropriate values for Preview if you will use Preview deploys.
5. Deploy `main`. Subsequent pushes to `main` deploy automatically.
6. After deployment, open `https://<project>.vercel.app/health`. A successful
   response includes `status: ok`, `model_version`, and `trained_skus`.

If the deployment fails during startup, check the function logs for a missing
`DATABASE_URL`, Blob connection, or model bundle. Do not put API keys or
database credentials in this repository.

## Connect n8n

Import `n8n/EUCERIN_Vercel_EndToEnd.json` and
`n8n/EUCERIN_Vercel_Error_Handler.json`. The main workflow already uses the
verified production API host. Fill the source Drive file ID, output folder ID,
and Telegram chat ID in the config Code node. Configure an n8n Header Auth
credential with header name `X-API-Key` and the same value as Vercel's
`ML_API_KEY`; attach it to the HTTP Request nodes. Never put the key in the
workflow JSON.

Run the main workflow manually first. Confirm all eight CSV outputs exist in
the Drive output folder and the run reaches its notification step before
enabling the daily 09:00 Asia/Ho_Chi_Minh schedule. Select the separate error
workflow in the main workflow's Error Workflow setting. Drive/Telegram
credentials are configured in n8n and are not included in the exported JSON.

## Operational notes

- Vercel's function filesystem is temporary. Run state is stored in Postgres;
  generated artifacts are stored in private Blob. Local and Render runs keep
  using the existing SQLite/filesystem backend.
- Vercel API input limit is 4 MiB; local and Render input limit remains 20 MiB.
- The model bundle is served with the API function. The historical source CSV
  and local sample outputs are excluded from the function bundle and are not
  uploaded to GitHub.
- `APP_MODE=production` permits later source dates, but it does not validate
  forecast accuracy on new observations. Monitor the API warnings and review
  model performance before relying on new forecasts.
