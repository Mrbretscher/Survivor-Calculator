# Survivor Calculator

A for-fun Survivor analytics and prediction project that turns a local `survivoR.xlsx` workbook into current-season baseline probabilities and dashboard-ready JSON.

This is not production-grade forecasting. Survivor is noisy, sample sizes are small, and the model is meant to be playful.

## Current Status

- Robust workbook XML ingestion for the provided `survivoR.xlsx` workbook.
- Clean CSV exports for selected core sheets.
- Episode-state feature generation for historical training rows and current-season inference rows.
- Leakage guard for known target and future outcome columns.
- Historical-rate baseline for next-boot probability, winner probability, and projected remaining boot order.
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

- the exact download URL used for `survivoR.xlsx`;
- the upstream package or data version used to create the workbook;
- the workbook download date;
- whether the workbook was modified after download;
- whether every generated CSV, JSON, and HTML artifact can be publicly redistributed.

Before publishing the workbook, generated data, or a public website that serves derived records, verify the upstream license text, preserve required attribution, record the exact source/version/date, and document whether redistribution of the workbook and derived outputs is permitted.

See [DATA_CARD.md](DATA_CARD.md) for the current data inventory, handling notes, and release checklist.

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

The SOC layer uses the [2018 U.S. Bureau of Labor Statistics Standard Occupational Classification](https://www.bls.gov/soc/2018/home.htm) structure as a target taxonomy. The current implementation is deterministic keyword mapping with review flags. It is a convenience feature for grouping occupations, not a verified labor-statistics classification.

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
- The current model is intentionally simple and does not establish causal effects.
- Current-season outputs depend on the local workbook being up to date.
- SOC mapping is deterministic and incomplete; ambiguous occupations require manual review.
- Data license and redistribution status for the local workbook and generated artifacts remain unresolved until provenance is documented.
