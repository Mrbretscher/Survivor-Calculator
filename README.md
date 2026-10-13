# Survivor Calculator

A for-fun Survivor analytics and prediction project. The first version ingests the provided `survivoR.xlsx` workbook, builds episode-state features without trusting Excel's stale sheet dimensions, generates baseline current-season predictions, and exposes an API-ready JSON contract for a future Next.js site.

This is not production-grade forecasting. Survivor is noisy, sample sizes are small, and the model is meant to be playful.

## What Works Now

- Robust workbook XML ingestion for the provided workbook.
- Clean CSV exports for key sheets.
- Episode-state feature generation for historical training rows and current-season inference rows.
- Leakage guard for target/future outcome columns.
- Historical-rate baseline for:
  - next boot probability
  - winner probability
  - projected remaining boot order
- SOC occupation mapping coverage: each distinct occupation is mapped by keyword or marked for review.
- Static local dashboard HTML generated from the latest prediction output.
- Optional FastAPI app and Next.js frontend scaffold.

## Quick Start

Use the bundled or local Python 3.11+ interpreter.

```powershell
python -m survivor_calculator.cli build --workbook survivoR.xlsx
python -m survivor_calculator.cli dashboard
python -m unittest discover -s tests
```

If you are running from source without installing the package, set `PYTHONPATH`:

```powershell
$env:PYTHONPATH = "src"
python -m survivor_calculator.cli build --workbook survivoR.xlsx
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

## Data And Attribution

The included workbook is treated as the local source of truth. Before public hosting, verify the workbook's provenance, preserve the upstream `survivoR` attribution/license, and add a clear data-source note to the website.

The SOC layer uses the 2018 U.S. Bureau of Labor Statistics Standard Occupational Classification structure as the target taxonomy. The first implementation includes deterministic keyword mapping plus review flags rather than pretending ambiguous occupations are certain.

