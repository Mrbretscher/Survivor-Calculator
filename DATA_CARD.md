# Data Card

## Dataset Summary

This project uses a local workbook named `survivoR.xlsx` as the source for Survivor analytics and prediction features. The workbook is not tracked in Git. The generated files under `data/processed/` are derived from that workbook and are also ignored by Git.

The upstream source appears to be the [`survivoR`](https://github.com/doehm/survivoR) dataset project. Upstream [CRAN package metadata](https://CRAN.R-project.org/package=survivoR) currently describes `survivoR` as data from all seasons of the U.S. Survivor TV series in tidy format and lists license metadata as `MIT + file LICENSE`. This data card does not interpret those terms or claim that the local workbook has verified provenance.

## Known Local Source

- Local file: `survivoR.xlsx`
- Local size observed in this checkout: 12,054,220 bytes
- Repository tracking status: ignored by `.gitignore`
- Ingestion entry point: `survivor_calculator.ingest.WorkbookReader`
- Build command: `python -m survivor_calculator.cli build --workbook survivoR.xlsx`
- User-confirmed workbook download page (October 14, 2026):
  [Survivor Stats DB](https://survivorstatsdb.com/download).
- Current unresolved workbook provenance: direct file URL, upstream version,
  download date, modification history, and checksum are not recorded.

## Automatic Source Updates

`python -m survivor_calculator.cli refresh` uses the upstream project's
[JSON exports](https://github.com/doehm/survivoR/tree/master/dev/json) at one pinned
Git commit. It records table URLs, retrieval time, source and output checksums,
model selection, and pipeline code checksum in `refresh_manifest.json`, with source
provenance also included in prediction metadata. These generated files are ignored
by Git. Automatic model tables are filtered to US records to match model season
keys; analytics and exported source tables retain all available franchises.
JSON booleans are converted
to the workbook reader's `1`/`0` convention. This records provenance for newly
fetched snapshots, not the original workbook's version or download date.

See [AUTO_UPDATES.md](AUTO_UPDATES.md) for scheduling, hosting setup, failure
behavior, chronological evaluation, and activation checks. Upstream data remains
subject to its license and attribution requirements; the existing public-release
checklist still applies.

## Workbook Inventory

The local workbook inspection found these sheets:

| Sheet | Rows | Columns |
| --- | ---: | ---: |
| Advantage Details | 431 | 8 |
| Advantage Movement | 986 | 15 |
| Advantage Timeline | 7,479 | 10 |
| Auction Details | 301 | 18 |
| Boot Mapping | 15,960 | 13 |
| Boot Order | 1,478 | 9 |
| Castaway Details | 1,222 | 22 |
| Castaway Scores | 1,442 | 70 |
| Castaways | 1,463 | 26 |
| Challenge Description | 1,960 | 47 |
| Challenge Results | 22,182 | 27 |
| Challenge Summary | 93,654 | 15 |
| Confessionals | 14,116 | 13 |
| Episodes | 1,237 | 13 |
| Journeys | 90 | 12 |
| Jury Votes | 1,653 | 8 |
| Season Summary | 78 | 27 |
| Survivor Auction | 311 | 11 |
| Tribe Colours | 289 | 6 |
| Tribe Mapping | 15,542 | 9 |
| Viewers | 1,237 | 12 |
| Vote History | 9,773 | 23 |

## Sheets Used By This Project

The current build exports and uses these core sheets:

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

Other workbook sheets are visible to inspection but are not currently exported by the build command.

## Workbook Handling

The XLSX reader streams worksheet XML directly from the workbook ZIP package and resolves shared strings itself. This is intentional because the provided workbook can contain stale worksheet dimension metadata that makes some high-level Excel readers misread sheet extents.

The reader exports selected sheets to UTF-8 CSV files in `data/processed/tables/`. Feature engineering then constructs:

- historical episode-state rows for completed seasons;
- current episode-state rows for the latest detected current-season episode;
- cumulative challenge, vote, confessional, and advantage features;
- next-boot and winner targets for historical rows;
- deterministic SOC occupation mapping rows with confidence and review flags.

## Generated Artifacts

Generated files are local build outputs and should not be committed by default:

| Path | Purpose |
| --- | --- |
| `data/processed/tables/*.csv` | Clean CSV exports of core workbook sheets |
| `data/processed/historical_episode_states.csv` | Historical feature rows and targets |
| `data/processed/current_episode_state.csv` | Active current-season inference rows |
| `data/processed/soc_mapping.csv` | Occupation mapping output with review flags |
| `data/processed/current_predictions.json` | Baseline model metadata, player probabilities, projected boot order, and evaluation summary |
| `data/processed/dashboard.html` | Static local dashboard generated from prediction JSON |

Because these files are derived from the workbook, their public redistribution status is unresolved until the workbook provenance and upstream license obligations are confirmed.

## Schema Notes

The raw workbook schema is sheet-specific. The current model-facing feature columns include:

- season and episode state: `season`, `episode`, `n_boots`, `final_n`
- contestant descriptors: `age`, `gender`, `occupation`, `soc_major_group`
- tribe context: `tribe_status`, `tribe_size`
- cumulative performance and visibility: `challenge_wins_to_date`, `individual_immunity_wins_to_date`, `votes_received_to_date`, `votes_cast_to_date`, `confessionals_to_date`, `confessional_time_to_date`, `advantages_held_to_date`

Known target or outcome columns are excluded from `FEATURE_COLUMNS` and checked by `assert_no_leakage_columns`.

## Missing Values And Data Quality

The current preprocessing converts blank numeric fields to `None` or `0.0` depending on context. Unknown gender is represented as `Unknown`. Missing or unmapped occupations are flagged through the SOC mapping output rather than silently treated as verified classifications.

Known data quality risks:

- Current-season results depend on whether the local workbook has been updated after the latest episode.
- Some workbook metadata may be stale even when row data is present.
- Occupation-to-SOC mapping is keyword-based and requires manual review for public reporting.
- Historical Survivor data may reflect editing, availability, and recording biases rather than complete gameplay truth.

## Intended Use

This dataset handling is intended for a for-fun portfolio project, local analytics, and demonstration of data ingestion, feature engineering, baseline modeling, and API/dashboard output.

## Unsuitable Use

Do not use these outputs as production forecasts, betting advice, definitive player assessments, or evidence of causal relationships. Do not publish the raw workbook or generated derivatives until the unresolved license and provenance questions below are answered.

## Attribution And License Status

Known:

- The workbook filename and project context point to the upstream `survivoR` data project.
- Upstream package metadata currently lists license metadata as `MIT + file LICENSE`.
- The project uses the [2018 BLS SOC structure](https://www.bls.gov/soc/2018/home.htm) as the target taxonomy for occupation grouping.

Unresolved:

- The download page is user-confirmed; the direct workbook file URL is not recorded.
- The upstream package version, data version, or commit is not recorded.
- The workbook download date is not recorded.
- The workbook checksum is not recorded.
- It is unknown whether the local workbook was modified after download.
- It is unknown whether generated CSV, JSON, and HTML artifacts may be redistributed publicly.
- The exact attribution text required for a public website has not been selected.

## Public-Release Checklist

Complete this checklist before public hosting or release:

- Record the source URL and download date for `survivoR.xlsx`.
- Record an upstream version, release, package version, or commit.
- Save a checksum for the workbook used to generate public outputs.
- Verify the exact upstream license text and attribution requirements.
- Decide whether the raw workbook is excluded from release or redistributed with permission.
- Decide whether generated files under `data/processed/` are excluded, regenerated by users, or published as derived artifacts.
- Add attribution to the README, website, dashboard, and any generated data bundle.
- Add or confirm a license for this repository's original code.
- Rebuild generated files from the documented workbook and rerun the test suite.

## Verification Commands

Inspect the workbook:

```powershell
$env:PYTHONPATH = "src"
python -m survivor_calculator.cli inspect --workbook survivoR.xlsx
```

Build generated artifacts:

```powershell
$env:PYTHONPATH = "src"
python -m survivor_calculator.cli build --workbook survivoR.xlsx
```

Run tests:

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests
```
