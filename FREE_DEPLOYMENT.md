# Free deployment: Netlify website + Vercel API

This is the prepared route for a personal, non-commercial project when you do not want to provide a payment card. Use a Vercel **Hobby** account, not a Pro trial. Vercel offers free Hobby functions within usage limits and supports FastAPI. An account can still be subject to platform verification; if signup requests a paid plan or payment details, stop rather than upgrading. Sources: [Hobby plan](https://vercel.com/docs/plans/hobby), [FastAPI deployment](https://vercel.com/docs/frameworks/backend/fastapi).

## What is already prepared

- `netlify.toml` builds `frontend/` and publishes `.next`.
- `frontend/next.config.ts` uses ordinary Next.js output.
- `src/survivor_calculator/deployment.py` adds configurable browser CORS and `/ready`.
- The Python 3.11 FastAPI import failure in the analytics route declarations is fixed.
- `.venv` has the existing `[api]` extras installed, and 59 tests pass.
- Current data was regenerated with chronological evaluation: season 51, episode 4, 17 active players, 1,462 analytics rows.
- `outputs/vercel-api/` contains an isolated API deployment and validated data snapshot. Its `manifest.json` records file hashes and dataset summary.

The bundle contains neither the workbook nor secrets, logs, dependencies, or caches. It remains ignored by Git. Publishing it will publish derived data through the API. Resolve the release checklist in `DATA_CARD.md` first; preparation does not establish redistribution permission.

## 1. Publish the prepared API bundle

Sign up for Vercel's personal Hobby plan. Then run these commands yourself from PowerShell. They use the Vercel CLI through `npx`, rather than installing it globally:

```powershell
Set-Location 'C:\Dev\Survivor Calculator\outputs\vercel-api'
npx.cmd vercel@latest login
npx.cmd vercel@latest deploy
```

The second command uploads code and data to Vercel and creates a preview deployment. Select your personal Hobby account, create a new API project, and use `./` as its directory. The framework should be detected as FastAPI. Keep the generated `app.py`, `requirements.txt`, `.python-version`, `vercel.json`, and `.vercelignore` together. Do not import the main GitHub repository for this API route: its ignored data would be absent.

The bundle uses Python **3.12**, which Vercel supports and which satisfies this project's Python >=3.11 requirement. Vercel's build still needs verification; local tests used Python 3.11. Dependencies follow the repository's existing version constraints, so this is not a fully locked cross-platform build. [Python runtime and bundling](https://vercel.com/docs/functions/runtimes/python).

If CLI configuration or account access fails, keep the full error for diagnosis. Nothing has been uploaded automatically by Codex.

## 2. Test the deployed API

Copy the actual preview URL from Vercel. In the same PowerShell session:

```powershell
$survivorApiUrl = 'https://YOUR-ACTUAL-API-DEPLOYMENT.vercel.app'
Invoke-RestMethod "$survivorApiUrl/health"
Invoke-RestMethod "$survivorApiUrl/ready"
Invoke-RestMethod "$survivorApiUrl/api/predictions/current"
Invoke-RestMethod "$survivorApiUrl/api/analytics/schema"
Invoke-RestMethod "$survivorApiUrl/api/analytics/presets"
$survivorQuery = '{"dimension":"occupation","metric":"contestant_count","limit":5}'
Invoke-RestMethod "$survivorApiUrl/api/analytics/query" -Method Post -ContentType 'application/json' -Body $survivorQuery
```

Preview deployment protection can require login. If so, verify while authenticated in the dashboard and proceed to a public production deploy for the external tests. Do not use a protected preview URL in Netlify.

When the Vercel build is successful and you're ready to publish, run from the bundle directory:

```powershell
npx.cmd vercel@latest deploy --prod
```

Use the stable production project URL from Vercel for the website. Repeat the requests above against that URL. `/ready` must return `status: ready`; unlike `/health`, this checks that both bundled datasets are usable. If it returns 503, check that the bundle's data files were uploaded and that there are no stale `SURVIVOR_*_PATH` overrides pointing to Render paths.

Confirm the production API is accessible while logged out. Review **Vercel Project Settings > Deployment Protection** if needed. Netlify and browsers cannot call an API protected by a hosting login.

## 3. Publish the frontend code through GitHub

From the repository root, review and commit the source changes. Keep `.venv`, `data/processed`, and `outputs/vercel-api` out of Git. Include the API fix and the new prep tooling if you want to preserve them. `git status --short` lists the files to review; do not stage everything blindly.

Push to the GitHub branch Netlify builds. In Netlify create a fresh project connected to that branch. The prepared root `netlify.toml` sets:

| Setting | Value |
| --- | --- |
| Base directory | `frontend` |
| Package directory | Empty |
| Build command | `npm run build` |
| Publish directory | `.next` |

Add this Netlify environment variable for production builds and functions (or all scopes):

```text
NEXT_PUBLIC_API_BASE_URL=https://YOUR-STABLE-API-PROJECT.vercel.app
```

Use your real production API URL, with no trailing slash and no `/api` suffix. Deploy through Git so Netlify's Next.js adapter runs. Compare the deploy commit with GitHub, verify adapter processing, and test both the unique deploy URL and the production website URL. If you created the Netlify project before setting the variable, trigger another build.

## 4. Allow the website's browser origin

In the Vercel API project's environment variables, add this for **Production**:

```text
SURVIVOR_ALLOWED_ORIGINS=https://YOUR-ACTUAL-SITE.netlify.app
```

Use the exact website origin with no trailing slash. Redeploy the API bundle using `npx.cmd vercel@latest deploy --prod` so the value is applied.

Open the website, select an analytics preset, change a filter, and submit a chart. Confirm browser Network requests go to the Vercel HTTPS API and return JSON. Predictions render on the Next.js server; working predictions alone do not prove browser CORS works.

Also test in a private window and from another device, refresh the page, and confirm no requests use `127.0.0.1`. Reapply the origin setting if you rename the website or add a custom domain.

## 5. Update the API snapshot later

For automatic hourly upstream checks, retraining, and Vercel deployment, use the
workflow and credential setup in [AUTO_UPDATES.md](AUTO_UPDATES.md). The Netlify
frontend reads fresh API data through its existing 60-second revalidation. The
manual workbook route below remains available.

Rebuild data locally and generate a new bundle directory. Existing bundles are never overwritten:

```powershell
Set-Location 'C:\Dev\Survivor Calculator'
.\.venv\Scripts\python.exe -m survivor_calculator.cli build --workbook survivoR.xlsx --evaluation-strategy chronological
.\.venv\Scripts\python.exe -m survivor_calculator.deployment_bundle --output outputs/vercel-api-next
```

From the new bundle directory, use `npx.cmd vercel@latest link` to select the existing API project, then deploy to preview, test, and deploy with `--prod`. No retraining or file download occurs on ordinary API requests. The data is part of the deployment artifact and survives serverless cold starts without writable persistent storage.

## Other options checked

| Option | Fit for this request |
| --- | --- |
| Vercel Hobby | Free personal API hosting; prepared bundle route above. Usage limits apply. |
| Render Free | Free service exists; sleeps after idle time and lacks persistent disks. Could also serve an immutable bundled snapshot, but you asked for another provider. |
| Koyeb Free | Free compute exists, but card verification and signup billing do not fit your no-card preference. |
| Hugging Face Docker Spaces | Current docs require a paid plan to create Docker Spaces; CPU Basic having no hourly charge does not make new Docker Spaces a fully free option. |
| Cloudflare Python Workers | Supports Python/FastAPI and has free usage, but uses a different runtime and would need additional adaptation and verification. |

Sources: [Render Free](https://render.com/docs/free), [Koyeb billing](https://www.koyeb.com/docs/faqs/pricing), [Spaces creation requirements](https://huggingface.co/docs/hub/spaces-overview), [Cloudflare Python runtime](https://developers.cloudflare.com/workers/languages/python/).

This route is prepared locally, not deployed. Read `DEPLOYMENT_CHECKS.md` for what passed and what still needs verification.
