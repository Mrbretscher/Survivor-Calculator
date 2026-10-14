# Automatic data updates

The `refresh` command fetches the upstream `doehm/survivoR` JSON tables at one
fixed Git commit, validates their schema, fits the selected model again, and
rebuilds predictions, analytics, and the dashboard. No workbook download or R
installation is required. The existing workbook build still works.

```powershell
.\.venv\Scripts\python.exe -m survivor_calculator.cli refresh
# Existing optional models are supported when the ml extra is installed:
.\.venv\Scripts\python.exe -m survivor_calculator.cli refresh --model hybrid-next-boot
```

The default remains the historical-rate baseline. Changing data, model choice,
Python pipeline source, or missing/modified generated outputs triggers a rebuild.
Unchanged data skips training. Use `--force` to rebuild explicitly. The updater
filters season tables to US records because the feature pipeline keys seasons by
number; analytics from automatic updates consequently cover US seasons only.
Castaway demographics remain available for the US players' identifiers.

Only completed historical seasons supply training labels. New episodes in an
ongoing season refresh inference features without treating unresolved outcomes
as historical training labels. Each rebuild uses chronological holdout evaluation
and retains log loss, Brier score, top-1 accuracy, and top-3 recall in predictions.
Retraining preserves the selected model; it does not automatically choose a more
complex model or establish that its forecasts improved.

`data/processed/refresh_manifest.json` records the source commit, retrieval time,
table URLs and checksums, model, code checksum, and generated file checksums.
Prediction metadata also records provenance. All generated data stays ignored by
Git. Download/schema/training failures leave existing outputs untouched; local
publication uses per-file replacement after a successful staged build. It is not
a transaction across all local files. Hosted deployment uses a complete new
snapshot after staging succeeds, so a build failure leaves the previous API live.
An exclusive lock rejects overlapping local refreshes. A process killed abruptly
may leave a lock beside the output directory; verify no updater is running before
removing that stale lock.

## Hosted setup

`.github/workflows/refresh-data.yml` checks hourly at minute 17 and supports a
manual **Run workflow** with a force option. GitHub schedules run from the default
branch and may be delayed or disabled by GitHub; this is polling, not an immediate
upstream webhook. A cache eviction causes a harmless full rebuild. Workflow
concurrency prevents overlapping production deployments.

Before activation, configure the repository's **production** GitHub environment:

| Kind | Name | Value |
| --- | --- | --- |
| Secret | `VERCEL_TOKEN` | Vercel deployment token for the existing API project |
| Variable | `VERCEL_ORG_ID` | `orgId` from the existing API bundle's `.vercel/project.json` |
| Variable | `VERCEL_PROJECT_ID` | `projectId` from that same file |
| Variable | `SURVIVOR_API_URL` | Stable public HTTPS API origin, e.g. `https://survivorcalc.vercel.app` |
| Optional variable | `SURVIVOR_MODEL` | Existing CLI model alias; defaults to `historical-rate-baseline` |

Never put the token in source files. Keep the existing production Vercel CORS
settings and Netlify `NEXT_PUBLIC_API_BASE_URL` pointing to the stable API project
URL. Check that Vercel's production data-path variables do not override the
bundle's data paths. The workflow needs a publicly accessible deployment `/ready`
endpoint on `SURVIVOR_API_URL`; deployment protection that requires login there
will fail that check. Checks use the stable production origin because Vercel may
protect generated deployment URLs even while the production domain is public.

Push the reviewed workflow and code to the repository's default branch, then run
the workflow manually once. It installs the project's existing extras, runs the
Python tests, restores the last successful snapshot, refreshes changed inputs,
validates the API bundle, deploys it to Vercel production, and checks `/ready`
plus the expected source commit and prediction timestamp on the public API.
The successful snapshot is cached only after deployment, so a failed deployment
will be retried. Inspect GitHub Actions failures and enable GitHub failure
notifications. A successful deployment followed by a failed readiness check can
already be live; use Vercel rollback if needed. This workflow does not implement
automatic rollback or model-quality-based promotion.

The Next.js frontend already revalidates predictions and analytics after 60
seconds, so API data changes need no Netlify rebuild. An already open browser page
may need a reload. Confirm updated prediction `source_data.commit` and episode,
then load predictions and a chart from the public website.

This checkout does not establish whether the workflow has been pushed, whether
the GitHub secret exists, or whether a hosted run succeeds. Those are activation
checks, separate from local tests. GitHub Actions and Vercel account limits apply.
The Vercel CLI is pinned to 64.0.2. Actions use major-version tags and Python
dependencies follow the existing version ranges, so the entire build is not locked.

## Implementation plan and boundaries

1. **Goal:** Refresh data, refit the selected model, and refresh the hosted website.
2. **Current repository state:** Workbook CLI builds local files; Vercel serves an
   immutable API bundle; Netlify reads that API with a 60-second cache.
3. **Scope:** JSON acquisition, change detection, existing training/evaluation,
   provenance, tests, hourly workflow, and Vercel deployment.
4. **Non-goals:** New model architectures, per-request training, R dependencies,
   automated model selection, or changes to the frontend contract.
5. **Dataset and licensing:** User confirms workbook source as
   https://survivorstatsdb.com/download. Automatic builds use the upstream GitHub
   JSON tables (roughly tens of thousands of rows, bounded per download). Preserve
   upstream attribution; remaining redistribution questions are in DATA_CARD.md.
6. **Model inputs and outputs:** Existing episode-state features, historical
   next-boot/winner labels, player probabilities, boot order, and analytics CSV.
7. **Baseline:** Preserve historical-rate baseline as the default.
8. **Advanced modeling approach:** Existing optional sklearn models only, selected
   explicitly through the CLI or repository configuration.
9. **Validation and leakage controls:** Existing feature exclusion and completed
   season labels, chronological evaluation, US-only season keys, pinned snapshot.
10. **Evaluation metrics:** Existing log loss, Brier score, top-1, top-3, and
    baseline comparisons; no new claim of calibration or production readiness.
11. **System architecture:** Scheduled Actions job -> pinned JSON -> validated
    staged build -> API bundle -> Vercel -> existing Netlify frontend.
12. **Repository changes:** CLI table-build reuse, refresh module, refresh tests,
    workflow, and source/setup documentation. No new production dependencies.
13. **Milestones:** Verify upstream schema; implement/test refresh; prepare and
    validate snapshot; configure credentials and verify hosted execution.
14. **Testing and verification:** Fixture tests for no-change skips, changed data,
    failed downloads/schema/builds, provenance, integrity, model changes, locking;
    real upstream smoke build; full suite; bundle validation; Git diff review.
15. **Risks and open decisions:** Schema drift, partial upstream curation, schedule
    delays, credentials/account configuration, existing modeling limitations,
    public data rights, and hosted smoke checks. Hourly polling is the default.
16. **Definition of done:** Passing local checks plus a successful scheduled
    production run and confirmed fresh predictions/analytics on the public site.
