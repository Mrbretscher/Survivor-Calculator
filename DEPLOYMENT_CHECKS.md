# Deployment preparation checks

Checked October 14, 2026. Release recommendation: **Not ready for a public release yet**. The local website and API checks pass, but public account configuration, hosted builds, and existing data licensing/provenance items remain unresolved. This report follows the `ml-release-review` skill and focuses on the requested deployment preparation.

## Changes and findings

Changed source/configuration files: `netlify.toml`, `.python-version`, `.env.example`, `.gitignore`, `frontend/next.config.ts`, `src/survivor_calculator/api.py`, `src/survivor_calculator/deployment.py`, and `src/survivor_calculator/deployment_bundle.py`. Added tests: `tests/test_deployment.py` and `tests/test_deployment_bundle.py`. Documentation: `README.md`, `NETLIFY_SETUP.md`, `PUBLIC_DEPLOYMENT_GUIDE.md`, `FREE_DEPLOYMENT.md`, and this report. The prepared snapshot is under ignored `outputs/vercel-api/`; generated data remains under ignored `data/processed/`.

Added root Netlify/Python settings, simplified Next.js output, documented environment variables, added the hosted API's CORS/readiness entry point, added an isolated Vercel snapshot builder, and added seven deployment tests. The generated build metadata is now ignored.

Found and fixed a real API startup failure on Python 3.11 with FastAPI/Pydantic installed: inferred analytics response models rejected `typing.TypedDict`. Those route declarations now disable inferred response models and retain the payload loaders' validation. This is separate from the undiagnosed Netlify root 404.

## Commands and successful results

Run from the repository root unless otherwise stated:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --disable-pip-version-check --no-cache-dir -e '.[api]'
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_deployment*.py' -v
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m survivor_calculator.cli build --workbook survivoR.xlsx --evaluation-strategy chronological
.\.venv\Scripts\python.exe -m survivor_calculator.deployment_bundle
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

- Project environment installation succeeded after retrying with network permission; nothing was installed globally. No new production dependency declaration was added.
- Seven new tests passed: allowed/disallowed browser preflight, readiness success/empty/invalid/missing data, bundle file hashes/exclusion/overwrite protection, and missing-input handling.
- Full suite: **59 tests passed with no skips** using the API extras installed.
- Current prepared data: season 51, episode 4, 17 active players, 1,462 analytics rows. The build explicitly used chronological evaluation. No new forecasting-quality or production-readiness claim is made.
- `pip check` found no broken requirements.
- `git diff --check` found no whitespace errors. Git emitted LF-to-CRLF conversion warnings.
- Confirmed `.venv`, generated data, deployment outputs, and egg-info are ignored. A targeted scan found no tracked raw workbook/cache/environment/key artifacts or common secret-token/private-key patterns in the reviewed source; this was not a comprehensive secret audit.

Started `uvicorn survivor_calculator.deployment:app` on loopback and exercised live HTTP requests. GET `/health`, `/ready`, `/api/current-season`, `/api/predictions/current`, `/api/analytics/schema`, and `/api/analytics/presets` returned 200. POST analytics returned rows and the allowed-origin header. Browser OPTIONS preflight passed. Temporary servers were used only for verification.

From `frontend/`, built with the local API running:

```powershell
$env:NEXT_PUBLIC_API_BASE_URL = 'http://127.0.0.1:18765'
npm.cmd run build
```

Compilation, build lint/type validation, and page generation passed. Started the production Next.js server on loopback and requested `/`: HTTP 200 with the Season 51 dashboard. React's HTML comments were removed when checking rendered heading text. Live browser chart clicks were not automated; API behavior and preflight were checked separately.

Imported the generated bundle's `app.py` from its own directory, confirmed it loaded the copied package and bundled files, and verified its data loaders and registered endpoints. The bundle manifest contains SHA-256 hashes of packaged files; no raw workbook or credentials are copied.

## Failures resolved or still limited

- Initial dependency resolution failed under restricted network access; the authorized project-local install succeeded after escalation.
- The first hosted-entry import exposed the Python 3.11 TypedDict/Pydantic problem; the code fix and rerun passed.
- An initial production build failed with sandbox `spawn EPERM`; the build passed when rerun with process-launch permission.
- Python production lint/type tools are not configured in the repository. The existing standalone `npm run lint` uses `next lint`, which is not a valid standalone command for Next.js 15; the successful build's own lint/type validation is the check reported here. This preparation did not change the lint tooling.
- No Docker image was added or built because the selected free route uses Vercel's native Python runtime.

## Checks not completed and required corrections

- Vercel account eligibility, a Vercel build on its supported Python 3.12 runtime, deployed function behavior, and public deployment protection settings need verification. Local Python testing used 3.11.
- Netlify account settings, adapter-generated routes, actual production URL, and original root-404 cause remain unverified.
- API/website production URLs and allowed origins need to be entered after account setup. The local frontend build contains a temporary loopback API URL; production must rebuild with the real HTTPS address.
- Dependency constraints follow the existing repository strategy and are not a fully locked cross-platform environment. A successful local install does not prove all future resolver outcomes.
- Complete the source workbook provenance, redistribution permission, required attribution, and original code license checklist in `DATA_CARD.md` before publishing the snapshot.
- No commits, pushes, uploads, or account changes were made. Review the final diff and publish the intended code when ready.

## Final release checklist

- [ ] Resolve data and code license/provenance items and preserve attribution.
- [ ] Create a personal free Vercel Hobby API project and test its snapshot deployment.
- [ ] Verify production `/ready` and analytics POST from an unauthenticated client.
- [ ] Push reviewed source changes and build a fresh Netlify project with the actual API URL.
- [ ] Allow the final website origin in Vercel and redeploy the API.
- [ ] Confirm public predictions and chart interactions on another device.
- [ ] Verify both unique Netlify deployment and stable production URLs.

Optional later improvements include locking production dependencies and repairing the standalone lint command. The next deployment steps are in `FREE_DEPLOYMENT.md`; paid Render instructions remain in `PUBLIC_DEPLOYMENT_GUIDE.md`.
