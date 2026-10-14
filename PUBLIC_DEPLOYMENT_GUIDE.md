# Survivor Calculator: deploy a fully working public site

> The prep files in section 3 have now been applied in this local checkout, including a data readiness endpoint. Keep the current files rather than replacing them with older snippets below. For the no-payment-card route, use [FREE_DEPLOYMENT.md](FREE_DEPLOYMENT.md). See [DEPLOYMENT_CHECKS.md](DEPLOYMENT_CHECKS.md) for current verification results.

Follow this guide in order. It supersedes `NETLIFY_SETUP.md` and covers a fresh website, the Python API, persistent data, browser access, and verification. Checked against this repository and official documentation on October 14, 2026.

The previous 404 is still undiagnosed: the deploy log and generated routing have not been inspected. A correct settings screen alone does not prove that the intended commit built, the Next.js adapter ran, or the working deployment was published.

## What you will deploy

```text
Visitors -> Netlify HTTPS website
                +-> Next.js server -> Render API -> prepared predictions JSON
                +-> Browser charts -> Render API -> prepared analytics CSV
```

Use Netlify for Next.js and Render for the existing FastAPI backend. Generate data on your laptop and upload two output files directly to Render. Your laptop can then be switched off.

**This route requires a paid Render web service and persistent disk.** Check [Render pricing](https://render.com/pricing) and [Netlify pricing](https://www.netlify.com/pricing/) first. Free Render services cannot use this disk/SSH workflow. A custom domain and a third storage provider are unnecessary.

Netlify does not start the Python API when it imports GitHub. Netlify-only hosting would require rewriting the API for supported functions or redesigning the site around static data. [Netlify function runtimes](https://www.netlify.com/platform/core/functions/).

## 1. Confirm your source and tools

Keep the old Netlify project while testing. Create a new project with a different name so its settings and deployments are independent.

In local PowerShell:

```powershell
Set-Location 'C:\Dev\Survivor Calculator'
python --version
node --version
npm.cmd --version
Get-Command git, ssh, ssh-keygen, scp
git status --short
git branch --show-current
```

Use Python 3.11+ and Node.js with npm. If SSH tools are missing, install **OpenSSH Client** through Windows Optional Features.

This checkout uses `master`. Both hosts must deploy the branch containing your latest application. Confirm on GitHub that it contains `pyproject.toml`, `src/survivor_calculator/api.py`, `frontend/package.json`, `frontend/package-lock.json`, `frontend/app/page.tsx`, `frontend/app/analytics-panel.tsx`, and `frontend/lib/analyticsApi.ts`.

**Checkpoint:** the intended files are visible on GitHub in the chosen branch. Local uncommitted changes will not deploy.

## 2. Generate working prediction and analytics files

Use your project environment. If `.venv` already exists, omit the first command:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[api]"
.\.venv\Scripts\python.exe -m survivor_calculator.cli build --workbook survivoR.xlsx
Get-Item data/processed/current_predictions.json, data/processed/analytics_player_season.csv
.\.venv\Scripts\python.exe -c "from survivor_calculator.api import prediction_payload, analytics_schema_payload; p=prediction_payload(); s=analytics_schema_payload(); print('Season:', p['metadata']['current_season']); print('Players:', len(p['players'])); print('Analytics rows:', s['dataset']['row_count'])"
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

The `[api]` libraries are already declared in this repository. The default historical-rate model needs no ML extras. The API reads prepared outputs; it does not generate them at startup.

**Checkpoint:** generation and tests succeed, players are present, and analytics has rows. If the workbook is missing, obtain the documented workbook first. GitHub does not contain it.

Keep the raw workbook and generated data excluded from Git. The API needs only the JSON and CSV above, which you will transfer separately.

Before serving derived data publicly, complete the existing provenance, redistribution, code-license, and attribution checklist in `DATA_CARD.md` and `README.md`. These items remain unresolved in the repository. Record the source/version/date, confirm permission to host derived data, and add required attribution to the website. Obtain a workbook checksum with `Get-FileHash survivoR.xlsx -Algorithm SHA256`.

## 3. Create the deployment files

The following changes are instructions for you to apply. This guide has not changed the application or configured your accounts.

### A. Root-level `netlify.toml`

Create it beside `README.md`:

```toml
[build]
  base = "frontend"
  command = "npm run build"
  publish = ".next"

[build.environment]
  NODE_VERSION = "22"
```

`.next` is relative to the base, so this means `frontend/.next`. Keep the Netlify Package directory empty and avoid a competing configuration in `frontend/`. Netlify automatically installs its Next.js adapter. [Subdirectory builds](https://docs.netlify.com/build/configure-builds/monorepos/), [official Next.js settings](https://github.com/netlify/context-and-tools/blob/main/skills/netlify-frameworks/references/nextjs.md).

### B. `frontend/next.config.ts`

Use the ordinary Next.js configuration for this deployment:

```typescript
import type { NextConfig } from "next";

const nextConfig: NextConfig = {};

export default nextConfig;
```

This removes the current unnecessary `output: "standalone"`; the adapter manages the server. That removal is not a confirmed fix for the old 404. Do not change to `output: "export"`, since this setup uses server fetching and revalidation. [Netlify Next.js reference](https://github.com/netlify/context-and-tools/blob/main/skills/netlify-frameworks/references/nextjs.md).

### C. Root-level `.python-version`

Create a file with this single line:

```text
3.11
```

Render selects a matching patch version. Do not add a conflicting `PYTHON_VERSION` variable. [Render Python version configuration](https://render.com/docs/python-version).

### D. `src/survivor_calculator/deployment.py`

Create this complete file. It exposes the existing API with browser CORS support and uses the already-declared FastAPI extras:

```python
"""Hosted API entry point with explicit browser origins."""

from __future__ import annotations

import os

from fastapi.middleware.cors import CORSMiddleware

from survivor_calculator.api import create_app

app = create_app()
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

CORS allows your website's browser to read responses from another domain. Server-rendered predictions can work while browser charts fail if this is missing. CORS is not authentication; you are serving public data. [FastAPI CORS documentation](https://fastapi.tiangolo.com/tutorial/cors/).

### E. Verify and publish the source changes

```powershell
.\.venv\Scripts\python.exe -c "from survivor_calculator.deployment import app; print(app.title)"
Set-Location frontend
npm.cmd ci
npm.cmd run build
Set-Location ..
git diff --check
git status --short
```

`npm ci` replaces local `node_modules` using the committed lockfile. Review the files, then commit and push. These commands publish code to GitHub; substitute your actual branch for `master` if different:

```powershell
git add netlify.toml .python-version frontend/next.config.ts src/survivor_calculator/deployment.py
git diff --cached
git commit -m "Configure public frontend and API deployment"
git push origin master
git rev-parse HEAD
```

Review any previously staged files before committing. Publish other required application changes intentionally. Do not force-push or force-add data.

**Checkpoint:** GitHub shows the deployment files. Record the commit SHA for comparison with each host's build.

## 4. Deploy the API on Render first

Select **New > Web Service**, connect GitHub, and choose this repository:

| Setting | Value |
| --- | --- |
| Name | A new API service name |
| Branch | Your deployment branch |
| Runtime | Python |
| Root directory | Empty |
| Build command | `python -m pip install -e ".[api]"` |
| Start command | `uvicorn survivor_calculator.deployment:app --host 0.0.0.0 --port $PORT` |
| Health check | `/health` |
| Instance | Paid service supporting persistent disks |
| Disk mount | `/var/data` |

Enter `$PORT` literally in Render. Use **`deployment:app`**, which activates the CORS wrapper. Attach the smallest suitable persistent disk during creation or from the service's Disks page. [Render FastAPI setup](https://render.com/docs/deploy-fastapi).

Add these backend variables:

```text
SURVIVOR_PREDICTIONS_PATH=/var/data/current_predictions.json
SURVIVOR_ANALYTICS_PATH=/var/data/analytics_player_season.csv
```

Leave `SURVIVOR_ALLOWED_ORIGINS` unset until the new Netlify URL is known. Deploy and confirm the expected commit, successful install, and running Uvicorn in the logs. Copy the public HTTPS service address.

In local PowerShell:

```powershell
$survivorApiUrl = 'https://YOUR-ACTUAL-API-HOSTNAME'
Invoke-RestMethod "$survivorApiUrl/health"
```

**Checkpoint:** `status: ok`. Data endpoints can still return `503` until you upload the files.

## 5. Upload the two files directly from Windows

This uses Render SSH/SCP; no external storage account is required. Only files under `/var/data` survive restarts. The disk is accessible to the running service, not its build step. [Render disk transfers](https://render.com/docs/disks).

### A. Authorize your SSH key

Reuse an existing key if you prefer. Otherwise create a dedicated key with a new filename:

```powershell
ssh-keygen -t ed25519 -f "$env:USERPROFILE/.ssh/survivor_render" -C 'survivor-render'
Get-Content "$env:USERPROFILE/.ssh/survivor_render.pub"
```

Choose a passphrase. If the filename already exists, reuse it or choose another rather than overwriting it. Add only the `.pub` contents under **Render Account settings > SSH Public Keys**. Keep the private key private and out of Git. [Render SSH setup](https://render.com/docs/ssh).

### B. Connect and transfer

Open **Render service > Connect > SSH**. Copy the `USER@HOST` destination from Render's SSH command, not the public API hostname. Set:

```powershell
$survivorSshDestination = 'YOUR-RENDER-SSH-USER@YOUR-RENDER-SSH-HOST'
$survivorSshKey = "$env:USERPROFILE/.ssh/survivor_render"
ssh -i $survivorSshKey $survivorSshDestination
```

Retain any additional options in Render's supplied command. Compare the first-connection fingerprint with Render's documented fingerprints before accepting. Type `exit` after connecting to return to PowerShell.

From the repository root, upload temporary files:

```powershell
scp -i $survivorSshKey 'data/processed/current_predictions.json' "${survivorSshDestination}:/var/data/current_predictions.json.upload"
scp -i $survivorSshKey 'data/processed/analytics_player_season.csv' "${survivorSshDestination}:/var/data/analytics_player_season.csv.upload"
```

Check both commands succeed. Modern OpenSSH uses SFTP by default; older versions may require the `-s` option described in Render's documentation. Do not use legacy SCP mode when SFTP is required.

### C. Validate and activate on Render

Open the running service's **Shell**. Run this block in its Linux shell, not PowerShell:

```bash
python - <<'PY'
from pathlib import Path
from survivor_calculator.api import prediction_payload, analytics_schema_payload

root = Path('/var/data')
predictions = root / 'current_predictions.json.upload'
analytics = root / 'analytics_player_season.csv.upload'
p = prediction_payload(predictions_path=predictions)
s = analytics_schema_payload(analytics_path=analytics)
assert p['players'], 'No prediction players found'
assert s['dataset']['row_count'] > 0, 'No analytics rows found'
predictions.replace(root / 'current_predictions.json')
analytics.replace(root / 'analytics_player_season.csv')
print('Activated season:', p['metadata']['current_season'])
print('Analytics rows:', s['dataset']['row_count'])
PY
```

This validates both files before activating them. It replaces existing active files on subsequent updates; back them up first as described in section 10. Each rename is atomic, but the pair is not one transaction.

### D. Test the full API

In local PowerShell:

```powershell
$survivorPredictions = Invoke-RestMethod "$survivorApiUrl/api/predictions/current"
$survivorPredictions.metadata
$survivorPredictions.players.Count
Invoke-RestMethod "$survivorApiUrl/api/current-season"
$survivorSchema = Invoke-RestMethod "$survivorApiUrl/api/analytics/schema"
$survivorSchema.dataset
Invoke-RestMethod "$survivorApiUrl/api/analytics/presets"
$survivorQuery = '{"dimension":"occupation","metric":"contestant_count","limit":5}'
Invoke-RestMethod "$survivorApiUrl/api/analytics/query" -Method Post -ContentType 'application/json' -Body $survivorQuery
```

**Checkpoint:** every request returns data, including POST. Fix backend errors before continuing. PowerShell does not enforce browser CORS.

## 6. Create a fresh Netlify project

Choose **Add new project > Import an existing project > GitHub**, select this repository and your deployment branch, and choose the `frontend` app if detection offers a list.

| Setting | Value |
| --- | --- |
| Base | `frontend` |
| Package directory | Empty |
| Build command | `npm run build` |
| Publish directory | `.next` |
| Functions directory | Default/empty; handled by the adapter |

Use a new name, such as `survivor-calculator-fresh-EXAMPLE`. The root `netlify.toml` is the configuration source; resolve any conflicting dashboard values. Use Git-based deployment, which runs the adapter. Do not drag-and-drop `.next` or add `/* /index.html 200`. [Netlify Next.js deployment](https://docs.netlify.com/build/frameworks/framework-setup-guides/nextjs/overview/).

Add this variable before the build if the import screen allows it:

```text
NEXT_PUBLIC_API_BASE_URL=https://YOUR-ACTUAL-API-HOSTNAME
```

Use the Render address with **no trailing slash and no `/api` suffix**. Apply to production Builds and Functions, or all scopes if scope controls are unavailable. If you can only add it after creation, use **Project configuration > Environment variables**, then trigger another production build.

This value is public and compiled into the browser bundle. Never put credentials in it. Changes require a rebuild. [Netlify environment variables](https://docs.netlify.com/build/configure-builds/environment-variables/).

Record the actual new `https://...netlify.app` production URL.

## 7. Check the generated deploy, not just settings

In Netlify deploy details, confirm:

1. The commit SHA matches section 3.
2. Resolved base and publish paths correspond to `frontend` and `frontend/.next`.
3. `next build` completes and its route table includes `/`.
4. The Next.js/OpenNext adapter processes the output successfully. Search logs for `nextjs`, `OpenNext`, or `@netlify/plugin-nextjs`; wording can vary.
5. The completed deploy is published to production. Check for a production deploy locked to an older version.

Open **both the unique deploy URL from those details and the new production URL**. Use those exact links, not the old website address.

**Checkpoint:** both render the app and predictions. Analytics may await section 8. If the unique deploy URL still has Netlify's generic root 404, inspect adapter output and generated routing before continuing. An unreachable API normally renders the app's unavailable screen; it does not explain Netlify's generic root 404.

## 8. Enable browser analytics

In Render's Environment settings add:

```text
SURVIVOR_ALLOWED_ORIGINS=https://YOUR-NEW-PROJECT.netlify.app
```

Use the exact website origin, without a trailing slash. Save and redeploy/restart Render to load it. Its start command must still use `survivor_calculator.deployment:app`.

Check browser preflight from PowerShell:

```powershell
$survivorSiteOrigin = 'https://YOUR-NEW-PROJECT.netlify.app'
curl.exe -i -X OPTIONS "$survivorApiUrl/api/analytics/query" -H "Origin: $survivorSiteOrigin" -H 'Access-Control-Request-Method: POST' -H 'Access-Control-Request-Headers: content-type'
```

**Checkpoint:** successful response with `access-control-allow-origin` matching the site. Then actually load a preset, change a filter, and submit a chart in the browser. In **F12 > Network**, requests must use the Render HTTPS address and return successful JSON. Preview URLs are separate origins; test production or explicitly allow intended previews.

## 9. Verify public access and the final address

Open the new production website in a private window while logged out, and on a phone using cellular data. Confirm:

- HTTPS page loads without a hosting login/password.
- Predictions show the intended season, players, and generated date.
- Presets and custom charts work after refresh.
- Requests never use localhost or `127.0.0.1`.
- The site still works after a Render restart, proving persistent data survives.

If a hosting login is required, review Netlify site/deploy access controls. This app has no visitor login.

Keep the new URL, or move to your final project name/custom domain after these checks. Update Render's allowed-origin list whenever the website origin changes, then restart and retest charts. Multiple origins can be comma-separated. Do not detach the old domain before the new setup works. For a custom domain, follow [Netlify domain configuration](https://docs.netlify.com/manage/domains/configure-domains/) and HTTPS setup.

## 10. Maintain and roll back

For code: test, commit, push, and compare deploy SHAs. For data: regenerate locally and upload `.upload` files again. Before activating updates, make a matching backup pair in Render's shell:

```bash
python - <<'PY'
from datetime import datetime, timezone
from pathlib import Path
from shutil import copy2

root = Path('/var/data')
stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
for name in ('current_predictions.json', 'analytics_player_season.csv'):
    copy2(root / name, root / f'{name}.{stamp}.bak')
print('Backup timestamp:', stamp)
PY
```

Use section 5's validation/activation block. Keep the previous successful pair; restore both if an update fails. Choose a quiet update window because activating the pair is not transactional. Disk-backed Render redeploys can briefly interrupt service.

Predictions use 60-second revalidation. Allow time and another page request; if stale, verify the live API generated date and trigger a Netlify production rebuild. Browser analytics query the API directly.

## Troubleshooting the result you actually see

| Result | Next evidence to inspect |
| --- | --- |
| Unique deploy has generic root 404 | Correct commit contents, resolved configuration, adapter processing, generated routing |
| Unique deploy works; production URL fails | Published/locked deploy and whether URL belongs to the new project |
| Netlify URL works; custom domain fails | DNS, domain attachment, HTTPS |
| Build fails | First meaningful build error; no new working deploy was created |
| `package.json` missing | Base directory or branch |
| App shows data unavailable | API URL at build time, Render reachability, predictions endpoint |
| Health works; data is 503 | Uploaded files, `/var/data`, environment paths, read permissions |
| Data is 500 | API loader validation and backend logs |
| Predictions work; charts fail | CORS origin/entry point, CSV, POST response, browser console |
| Browser calls localhost | Set API URL and rebuild frontend |
| Data vanishes on restart | Files were outside persistent disk |

If root 404 persists, collect the **full build log, commit SHA, unique deploy URL, production URL, and resolved configuration**. These identify the missing step far better than repeating builds. The old 404's cause remains unknown.

## What was verified while writing this guide

- Ran `$env:PYTHONPATH = 'src'; python -m unittest discover -s tests`: 52 tests, passed, one skipped.
- Ran `npm.cmd run build` from `frontend/`: compilation, build lint/type validation, and page generation passed on Next.js 15.5.27, including route `/`.
- Checked the guide's TOML with Python `tomllib` and its Python code examples with `ast.parse`; syntax passed. This does not substitute for executing them against the hosting services.
- Ran `git diff --check` with no whitespace errors and reviewed both documentation diffs. Git reported LF-to-CRLF conversion warnings for the documentation.
- These results apply to the current repository, before the proposed deployment-file changes above. Verify those changes using section 3 after applying them.
- This request adds this guide and marks the earlier guide as superseded. It does not modify application code or hosting settings. Live Netlify/Render behavior, the proposed hosted entry point, file transfers, and browser CORS remain unverified. The web tool could not inspect the existing live site.

The next step is section 1, followed by preparing and validating the local data before creating hosting resources.
