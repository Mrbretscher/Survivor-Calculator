# Survivor Calculator

A for-fun Survivor analytics and prediction project that turns a local `survivoR.xlsx` workbook into current-season baseline probabilities and dashboard-ready JSON.

This is not production-grade forecasting. Survivor is noisy, sample sizes are small, and the model is meant to be playful.

## Current Status

- Robust workbook XML ingestion for the provided `survivoR.xlsx` workbook.
- Clean CSV exports for selected core sheets.
- Episode-state feature generation for historical training rows and current-season inference rows.
- Leakage guard for known target and future outcome columns.
- Historical-rate baseline for next-boot probability, winner probability, and projected remaining boot order.
- Optional experimental scikit-learn next-boot model behind an explicit CLI flag.
- SOC occupation mapping coverage: each distinct occupation is mapped by keyword or marked for review.
- Static local dashboard HTML generated from the latest prediction output.
- Optional FastAPI app and Next.js frontend scaffold.

## Quick Start

Use Python 3.11+ from a project environment. If you are running from source without installing the package, set `PYTHONPATH` first:

```powershell
$env:PYTHONPATH = "src"
python -m survivor_calculator.cli build --workbook survivoR.xlsx
python -m survivor_calculator.cli dashboard
python -m unittest discover -s tests
```

Generated files are written under `data/processed/` and are ignored by Git.

## Automatic Updates

To fetch the latest upstream GitHub JSON data and retrain only when inputs change:

```powershell
.\.venv\Scripts\python.exe -m survivor_calculator.cli refresh
```

The updater rebuilds predictions, analytics, and the dashboard with chronological
evaluation and records the source commit and checksums. The workbook build remains
available. An hourly GitHub Actions workflow can refresh the hosted Vercel API;
the existing Netlify frontend then picks up its new data. See
[AUTO_UPDATES.md](AUTO_UPDATES.md) for required hosting credentials, activation,
model selection, failure handling, and verification. The workflow must be pushed
and configured before automatic hosted updates are active.

The build command defaults to the dependency-light historical-rate baseline. To try the experimental scikit-learn model, install the optional ML extras in your project environment and opt in:

```powershell
pip install -e ".[ml]"
$env:PYTHONPATH = "src"
python -m survivor_calculator.cli build --workbook survivoR.xlsx --model experimental-next-boot
```

Each prediction output includes chronological holdout evaluation with log loss, Brier score, top-1 accuracy, and top-3 recall. When the experimental model is selected, the evaluation also compares it with `historical_rate_baseline`. Keep the baseline as the default unless the experimental model lowers both holdout log loss and Brier score.

## Local API

Run the dependency-light local API:

```powershell
$env:PYTHONPATH = "src"
python -m survivor_calculator.cli serve-api
```

It serves:

- `GET /health`
- `GET /api/current-season`
- `GET /api/predictions/current`

You can also install the FastAPI extras in a project environment:

```powershell
pip install -e ".[api]"
uvicorn survivor_calculator.api:app --reload
```

## Optional Frontend

For prepared public hosting, see [FREE_DEPLOYMENT.md](FREE_DEPLOYMENT.md) for a Netlify frontend and Vercel Hobby API, or [PUBLIC_DEPLOYMENT_GUIDE.md](PUBLIC_DEPLOYMENT_GUIDE.md) for paid Render API hosting. Current checks and remaining public-release requirements are in [DEPLOYMENT_CHECKS.md](DEPLOYMENT_CHECKS.md).

The frontend is a Next.js app under `frontend/`. It expects the API above to be running locally.

```powershell
cd frontend
npm install
npm run dev
```

## Data Source And Attribution

This repository expects a local workbook named `survivoR.xlsx` at the repository root. The workbook is treated as the local source of truth for ingestion, but it is not tracked in Git.

The project name and workbook filename indicate the upstream source is the `survivoR` Survivor dataset project. The upstream [CRAN package page](https://CRAN.R-project.org/package=survivoR) describes `survivoR` as data from all seasons of the U.S. Survivor TV series in tidy format and lists the license metadata as `MIT + file LICENSE`; the upstream GitHub repository is [`doehm/survivoR`](https://github.com/doehm/survivoR).

Do not treat that as full provenance for the local workbook yet. The repo currently does not record:

- the direct workbook file URL (the user confirmed the download page as
  [Survivor Stats DB](https://survivorstatsdb.com/download) on October 14, 2026);
- the upstream package or data version used to create the workbook;
- the workbook download date;
- whether the workbook was modified after download;
- whether every generated CSV, JSON, and HTML artifact can be publicly redistributed.

Before publishing the workbook, generated data, or a public website that serves derived records, verify the upstream license text, preserve required attribution, record the exact source/version/date, and document whether redistribution of the workbook and derived outputs is permitted.

See [DATA_CARD.md](DATA_CARD.md) for the current data inventory, handling notes, and release checklist.

Automatic updates instead use the upstream project's documented
[JSON exports](https://github.com/doehm/survivoR/tree/master/dev/json) and record
their exact Git commit, table URLs, retrieval time, and checksums in generated
metadata. This records provenance for those builds without assigning an upstream
version or download date to the original workbook.

## Workbook Handling

The workbook reader opens the XLSX file as a ZIP package and streams worksheet XML directly. This avoids relying on stale Excel dimension metadata, which can cause high-level readers to report real sheets as `A1:A1`.

The build command exports these core sheets to `data/processed/tables/`:

- `Advantage Timeline`
- `Boot Mapping`
- `Boot Order`
- `Castaway Details`
- `Castaways`
- `Challenge Results`
- `Confessionals`
- `Episodes`
- `Season Summary`
- `Vote History`

The model code then builds historical episode-state features, current episode-state features, SOC occupation mappings, prediction JSON, and static dashboard HTML.

## Generated Files

The following local artifacts are generated and ignored by Git:

- `data/processed/tables/*.csv`: cleaned CSV exports for the core workbook sheets.
- `data/processed/historical_episode_states.csv`: historical training rows with engineered features and targets.
- `data/processed/current_episode_state.csv`: active current-season inference rows.
- `data/processed/soc_mapping.csv`: deterministic occupation-to-SOC mapping output with review flags.
- `data/processed/current_predictions.json`: baseline probability output and evaluation metadata.
- `data/processed/dashboard.html`: static dashboard generated from the latest prediction JSON.
- `api-server.log`, `api-server.err.log`, `frontend/dev-server.log`, and `frontend/dev-server.err.log`: local runtime logs.
- `frontend/.next/` and `frontend/node_modules/`: frontend build and dependency directories.

Because these outputs contain transformed source data, treat them as subject to the same unresolved provenance and redistribution questions as the workbook until the release checklist is complete.

## SOC Mapping

The SOC layer uses the [2023 BLS OEWS occupation structure](https://www.bls.gov/oes/2023/may/oes_stru.htm) as a target taxonomy. The current implementation is deterministic keyword mapping with review flags. It assigns detailed occupation codes and titles where possible, plus a project-specific `Students` major group for contestant descriptions that are education statuses rather than labor-market jobs.

Public reporting should preserve the `review_required`, `confidence`, and `notes` fields from `data/processed/soc_mapping.csv`, and should not present unmapped or keyword-mapped occupations as manually validated SOC assignments.

## Public-Release Constraints

Before making a public release, do these items explicitly:

- Add a project license for this repository's original code.
- Record the exact `survivoR.xlsx` provenance: URL, upstream project, version or commit, download date, and checksum.
- Include the upstream `survivoR` license text or a clear link to the exact upstream license used.
- Confirm whether the raw workbook can be redistributed, or document that users must obtain it separately.
- Confirm whether generated CSV, JSON, and HTML artifacts may be committed, hosted, or served publicly.
- Add required attribution to the README, website, and any published generated artifact.
- Avoid implying affiliation with Survivor, CBS, or the upstream data maintainers.
- Keep `.env`, logs, caches, virtual environments, model artifacts, raw data, and generated data out of Git unless there is a documented release reason.

## Testing

Run the Python suite:

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests
```

Fixture-based tests run without the workbook. Integration tests that inspect the real workbook run only when `survivoR.xlsx` exists at the repository root.

## Limitations

- Baseline probabilities are historical-rate estimates, not calibrated production forecasts.
- The experimental next-boot model is opt-in only. It uses a regularized logistic model on engineered episode-state features and has not shown enough evidence here to replace the baseline by default.
- Chronological holdout seasons are small, and Survivor boot outcomes are sparse; log loss and Brier score are more relevant for probability quality than a single top-k ranking result.
- The model predicts next-boot risk independently before event-level normalization, so it does not understand alliances, episode narrative, edits not present in the workbook, idols played after the current state, or production context.
- The current model is intentionally simple and does not establish causal effects.
- Current-season outputs depend on the local workbook being up to date.
- SOC mapping is deterministic and incomplete; ambiguous occupations require manual review.
- Data license and redistribution status for the local workbook and generated artifacts remain unresolved until provenance is documented.
