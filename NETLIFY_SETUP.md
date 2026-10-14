# Survivor Calculator: Netlify setup guide

> Superseded by [PUBLIC_DEPLOYMENT_GUIDE.md](PUBLIC_DEPLOYMENT_GUIDE.md). Use that guide for a fresh deployment with direct data uploads and checks at each stage.

This guide matches the repository inspected on October 14, 2026. It explains how to fix the root-page 404 and how to get predictions and interactive analytics working online. The hosting steps and code examples below are instructions for you to apply; they have not been deployed for you.

## 1. Fix the Netlify 404 first

Your screenshot shows Netlify's own **Page not found** screen at `/`. The most likely cause is that Netlify is publishing the repository root instead of building the Next.js app in `frontend/`. This is a diagnosis from the repository layout and screenshot; the actual Netlify settings and deploy logs have not been inspected.

Open your existing `survivor-calculator` project in Netlify. Go to **Project configuration > Developer settings > Continuous deployment > Build settings** and edit the settings:

| Setting | Value for this repository |
| --- | --- |
| Repository | Your Survivor Calculator GitHub repository |
| Production branch | The branch containing the app you want to deploy; this local checkout is on `master` |
| Base directory | `frontend` |
| Package directory | Leave empty; the base directory already contains this app |
| Build command | `npm run build` |
| Publish directory | `.next` |
| Functions directory | Leave at the default; let the Next.js adapter manage it |

The publish directory is relative to the base directory. These settings mean Netlify builds in `frontend/` and publishes `frontend/.next/`. Do not enter `frontend/.next` with `frontend` already set as the base.

Netlify handles Next.js through its automatically installed OpenNext adapter. You do not need to add a plugin dependency just to deploy this app. Sources: [Netlify subdirectory configuration](https://docs.netlify.com/build/configure-builds/monorepos/), [Netlify's Next.js configuration reference](https://github.com/netlify/context-and-tools/blob/main/skills/netlify-frameworks/references/nextjs.md).

Save, then open **Deploys** and trigger a new production deploy. If available, choose the option to clear the build cache and deploy again. Check that the build log runs `next build`, recognizes Next.js, applies the adapter, and finishes successfully. Also confirm the successful deploy is **published to production**, rather than only being a deploy preview.

Open `https://survivor-calculator.netlify.app/` again. Once the frontend is correctly deployed, the page should show either the dashboard or the app's data-unavailable screen. The latter means the frontend is serving and you can proceed to API setup.

**Avoid these common fixes for other frameworks:** this app does not use `dist` or `build` as its output directory, and the current configuration does not produce an `out` static export. Do not add `/* /index.html 200` as a blanket rewrite. This is a Next.js app with server rendering and revalidation, so use the Next.js adapter's routing.

### Optional: store the settings in Git

To keep deployment settings with the project, create `netlify.toml` at the repository root, alongside `README.md`, with:

```toml
[build]
  base = "frontend"
  command = "npm run build"
  publish = ".next"
```

Commit and push that file to the production branch when ready. File configuration can override dashboard settings, so keep them consistent. This guide does not create that configuration file automatically.

## 2. Understand what still needs hosting

There are two applications here:

| Component | Location | Hosting role |
| --- | --- | --- |
| Next.js website | `frontend/` | Netlify serves the page and runs its Next.js server functions |
| Python API | `src/survivor_calculator/api.py` | A separate Python web service serves predictions and analytics |

Both `frontend/app/page.tsx` and `frontend/lib/analyticsApi.ts` default to `http://127.0.0.1:8000`. In a deployed app that address does not reach your laptop. Predictions are requested by the Next.js server; interactive analytics are requested by the visitor's browser. Both need a public HTTPS API address.

Importing GitHub into Netlify does not start the Python API. Netlify's native function languages are JavaScript, TypeScript, and Go; using the existing Python API requires a separate host. Running Python during a build would not create a continuously running API. Source: [Netlify Functions](https://www.netlify.com/platform/core/functions/).

The route below uses **Netlify for the frontend and Render for the existing FastAPI backend**. It preserves the application architecture. A Netlify-only version would require implementation work to replace the Python HTTP API with supported routes/functions or redesign the app around static data.

## 3. Prepare the data locally

The workbook and generated data are ignored by Git. A fresh GitHub deployment will not contain them.

From the repository root, using your Python 3.11+ project environment, run:

```powershell
python -m pip install -e .
python -m survivor_calculator.cli build --workbook survivoR.xlsx
```

If you need a project environment first:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m survivor_calculator.cli build --workbook survivoR.xlsx
```

The API needs these generated files:

- `data/processed/current_predictions.json`
- `data/processed/analytics_player_season.csv`

Generate them before uploading them. The API reads prepared outputs and does not automatically rebuild the dataset. The raw workbook is not needed on the API host for the prediction and analytics routes used by this frontend.

The README and `DATA_CARD.md` record unresolved workbook provenance and redistribution questions. Complete their existing data-release checklist before serving derived data publicly. Do not force-add ignored data to Git to work around deployment setup.

## 4. Allow the Netlify website to call FastAPI

The current FastAPI app does not configure CORS. CORS tells browsers which websites may read API responses from another domain. Without it, server-rendered predictions can work while interactive charts fail.

Apply this small change to `src/survivor_calculator/api.py` before deploying the backend. Inside the existing optional FastAPI import block, alongside the other imports, add:

```python
from fastapi.middleware.cors import CORSMiddleware
```

Inside `create_app()`, immediately after `app = FastAPI(...)`, add:

```python
allowed_origins = [
    origin.strip()
    for origin in os.environ.get("SURVIVOR_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
```

`os` is already imported. This uses the existing optional FastAPI dependency; it adds no new library to the project. Preserve the surrounding optional-import behavior so the dependency-light CLI still runs without FastAPI installed. Source: [FastAPI CORS documentation](https://fastapi.tiangolo.com/tutorial/cors/).

Before pushing the code change, run the Python tests and review the diff:

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests
git diff -- src/survivor_calculator/api.py
```

Commit and push the intended app files to the branch your hosts deploy. Local uncommitted changes are not included in GitHub deployments. Review other local edits before including them.

## 5. Create the Python backend on Render

This specific walkthrough uses a **paid Python web service with a persistent disk** so manually supplied data survives restarts and redeploys. Check Render's current pricing before choosing a plan. Free services do not support the disk and shell workflow described here. An alternative is to retrieve prepared data from object storage during every build; that needs a separate storage and download setup. Source: [Render persistent disks](https://render.com/docs/disks).

In Render, select **New > Web Service**, connect the same GitHub repository, and use:

| Setting | Value |
| --- | --- |
| Runtime | Python |
| Branch | The branch containing your API and CORS change |
| Root directory | Leave empty; the Python project is at the repository root |
| Build command | `python -m pip install -e ".[api]"` |
| Start command | `uvicorn survivor_calculator.api:app --host 0.0.0.0 --port $PORT` |
| Health check path | `/health` |
| Persistent disk mount path | `/var/data` |

The build command installs the project's already-declared FastAPI extras. The start command binds the API to the host's network interface and assigned port. `$PORT` is Render's Linux environment variable; enter this literally in Render, not in PowerShell. Source: [Render FastAPI deployment](https://render.com/docs/deploy-fastapi).

Select a supported Python 3.11+ version using Render's Python version settings. Set these backend environment variables:

```text
SURVIVOR_PREDICTIONS_PATH=/var/data/current_predictions.json
SURVIVOR_ANALYTICS_PATH=/var/data/analytics_player_season.csv
SURVIVOR_ALLOWED_ORIGINS=https://survivor-calculator.netlify.app
```

The origin must match the browser's address exactly and has no trailing slash. If you later add a custom domain, add its HTTPS origin to the comma-separated list. Deploy preview domains also need explicit permission if you want their charts to work.

Deploy the service and copy its HTTPS URL. Opening `<your-api-url>/health` should return `{"status":"ok"}`. This checks the process only; it does not prove the data files exist.

### Put the generated files on the persistent disk

One concrete upload route is to place the two prepared files in storage you control, create temporary download URLs, and download them from Render's **Shell** on the running service. Do not use an ephemeral shell for this step. Storage-provider URL creation varies; use your provider's download or presigned-URL feature. Keep credentials out of Git and avoid sharing these links.

In Render's Linux shell, replace the placeholders with the actual temporary URLs:

```bash
curl --fail --location 'PREDICTIONS_DOWNLOAD_URL' --output /var/data/current_predictions.json
curl --fail --location 'ANALYTICS_DOWNLOAD_URL' --output /var/data/analytics_player_season.csv
```

These commands download files and replace any outputs already at those paths. On initial setup the paths should be empty. Do not enter the placeholders unchanged. Download file contents, not a storage provider's HTML sharing page. The persistent disk is available to the running service, not the build step. For other transfer methods, see [Render disk file transfers](https://render.com/docs/disks).

Check the live API:

- `<your-api-url>/api/predictions/current`: JSON with metadata, players, and projected boot order.
- `<your-api-url>/api/analytics/schema`: JSON with dimensions, metrics, and a dataset row count.
- `<your-api-url>/api/analytics/presets`: JSON containing preset configurations.

Stop here and fix any API errors before connecting Netlify. A `503` normally means required output files are missing or inaccessible; a `500` can mean invalid data. Check the path environment variables, uploaded file contents, and backend logs.

## 6. Connect Netlify to the live backend

In Netlify, open **Project configuration > Environment variables** and add:

```text
NEXT_PUBLIC_API_BASE_URL=https://YOUR-ACTUAL-API-HOSTNAME
```

Use the backend's real HTTPS base URL with **no trailing slash and no `/api` suffix**. The code appends endpoint paths. Do not use the Netlify website URL unless you have separately implemented an API proxy.

Apply it to the production context and the **Builds** scope. If your plan exposes scopes, include **Functions** as well for server execution; otherwise use all scopes. Include deploy previews only if you want them to use this API.

`NEXT_PUBLIC_` values are public and become part of the browser build. This variable contains an address, not a credential. Rebuild and redeploy after setting or changing it. Source: [Netlify environment variables](https://docs.netlify.com/build/configure-builds/environment-variables/).

For an optional local check against the hosted backend, run from `frontend/`:

```powershell
$env:NEXT_PUBLIC_API_BASE_URL = "https://YOUR-ACTUAL-API-HOSTNAME"
npm.cmd run build
```

This compiles and type-checks the frontend. It does not test Netlify's adapter or browser CORS. To test charts from a local browser, also temporarily allow `http://localhost:3000` in the backend origin list and run `npm.cmd run dev`.

## 7. Verify the complete site

After the new Netlify production deploy is published:

1. Open the site's root URL and confirm it renders the Survivor dashboard.
2. Confirm season, player names, and generated date match the uploaded prediction file.
3. Load an analytics preset, then change a filter and submit a chart query.
4. Refresh the page and repeat from another browser or device.
5. In browser developer tools, inspect failed Network requests if anything is missing. Analytics requests must go to the hosted HTTPS API, not localhost.

The page's prediction fetch uses a 60-second revalidation setting. After an output update, allow for revalidation and another request. A frontend redeploy can also rebuild the page against the latest data.

| Symptom | Check |
| --- | --- |
| Netlify's generic 404 at `/` | Base/publish directories, Next.js adapter log, production branch, published deploy |
| Build says `package.json` is missing | Base directory should be `frontend` |
| Publish directory does not exist | Build succeeded and publish is `.next`, relative to `frontend` |
| App renders but says prediction data is unavailable | API base URL, backend reachability, prediction file, API response status |
| Predictions work but charts fail | FastAPI CORS middleware, allowed origin, analytics CSV, browser Network/Console |
| Browser still calls `127.0.0.1` | API URL was absent from the build; set it and redeploy |
| `/health` works but data routes fail | Process is alive, but data may be missing or invalid |
| Data disappears after redeployment | Files were stored outside the persistent disk |

## 8. Updating predictions later

Update the local workbook, rerun the CLI build, validate the generated outputs, and replace the two backend files. Upload to temporary filenames first and rename into place after successful transfers to avoid serving partially downloaded files. Keep the old outputs until the replacement is verified. This updates data without retraining or rebuilding during ordinary API startup.

Frontend code updates require a GitHub push and Netlify deploy. Backend code updates require a GitHub push and Render deploy. Neither host receives your uncommitted local edits.

## What was checked while writing this guide

The repository's README, data card, frontend configuration, API routes, environment-variable usage, and ignored data paths were inspected, and hosting instructions were checked against official documentation.

- Ran `npm.cmd run build` from `frontend/`: passed compilation, the build's lint/type-validation step, and page generation using Next.js 15.5.27.
- Ran `git diff --check`: no whitespace errors; Git printed existing LF-to-CRLF conversion warnings for modified files.
- Reviewed this guide's added-file diff. Only `NETLIFY_SETUP.md` was added for this request; existing application edits were preserved.

No Netlify or Render account settings were changed. The suggested CORS change has not been applied or tested. The live deploy logs, data uploads, and browser behavior still need verification through the steps above. The next step is to correct the Netlify build settings in section 1 and publish a new deployment.
