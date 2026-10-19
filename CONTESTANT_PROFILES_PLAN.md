# Tribe views and contestant profiles

## Goal and scope

Let visitors switch the current contestant board and projected boot order between current-tribe groups and a combined view. Link contestant names to dedicated profiles with official cast portraits, saved observed performance statistics and existing forecasts.

## Components and dependencies

- Next.js: shared prediction types/fetching and display helpers, a client-side grouped board, a dynamic contestant profile route, portrait fallback, and responsive styles using the existing palette.
- Python API: a read-only profile endpoint joining validated current predictions to the current-season US analytics row by castaway ID, served through both FastAPI and the local standard-library server.
- Images: explicitly mapped Season 51 CBS portraits from the official Paramount+ cast announcement, with visible source/credit and a fallback when no photo is available. Do not infer identity from first names or reuse another season's photos.
- Tests: backend profile semantics and HTTP behavior; frontend grouping, links, photo selection/fallback and rendering; production build/type checks and browser checks where available.
- Existing libraries only. The existing deployment bundle already contains the two required data artifacts. No model retraining, dependency additions, model promotion or changes to prediction probabilities.

## Behavior and risks

- Default to tribe groups; an accessible By tribe / All players button group changes both board and boot-order presentation.
- Preserve the global forecast order inside each tribe; show a separate within-tribe position. The existing next-boot probability remains global and is not a conditional probability of leaving if that tribe attends council.
- Profiles distinguish observed dataset totals from forecasts, expose snapshot time, and explain recorded votes/confessionals and missing data. Counts describe available records; zero recorded events does not establish complete source coverage.
- Scope analytics joins to the current US season and castaway ID to avoid mixing return appearances or other franchises. Unknown IDs return 404; API failures and missing statistics receive explicit states.
- Use remote official photo URLs with attribution, no generated portraits or copied biography prose. Remote images can fail, so retain an accessible initials fallback.
- Preserve unrelated local changes to model code and documentation.

## Verification and completion

Run profile unit/HTTP integration tests and the existing API tests; test grouping with swaps, missing tribes and ties; test contestant links and season-scoped portrait mapping; run the frontend build in an isolated output directory to protect the running preview. Review the final scoped Git diff and report the actual commands, results and any outstanding limitations.
