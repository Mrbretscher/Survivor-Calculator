# Tribe views and contestant profiles

The current dashboard opens with separate groups for each current tribe. The **By tribe / All players** controls beside both the contestant board and boot-order section are synchronized. Grouping preserves the existing forecasts and probabilities; tribe order is the overall boot list filtered to that tribe, rather than a new prediction conditional on that tribe attending Tribal Council.

Click a contestant name or **View contestant profile** to open `/contestants/{castaway_id}`. The highest-risk summary and boot-order tables also link to profiles. Profiles are available for contestants on the current prediction board; stale or unknown IDs display a not-found page.

Profiles include the existing winner/next-boot estimates and model signals, current and original tribes, challenge wins/appearances, voting totals, confessionals, and recorded confessional time. Equal forecast scores share a rank. An ordered boot-list position remains distinct from a tie-aware probability rank.

Observed counts come from the existing saved analytics artifact, joined by exact castaway ID and current US season. These describe available records, not guaranteed complete source coverage. Voting totals can include revotes, and received votes exclude source-marked nullified votes. Confessionals describe the show's edit, not social influence or jury support. No new performance model is introduced.

`GET /api/players/{castaway_id}` serves the profile data through both the standard-library local API and FastAPI. It validates the current prediction snapshot, returns 404 for unknown/inactive IDs, and leaves absent, malformed or ambiguous statistics unknown. A missing analytics artifact preserves the forecast with `stats_status: unavailable`. The frontend also withholds stats if the two API responses belong to different snapshot generation times. Neither service trains or downloads data on profile requests.

The API deployment bundle already includes the two required artifacts. A feature release needs the updated API source and frontend deployed; an older API still allows the forecast/profile photo to render, with an explicit performance-data-unavailable message. Restart an existing local API process after changing its source.

Official Season 51 portraits are explicitly mapped to castaway IDs in `frontend/lib/contestant-portraits.ts`. The URLs come from [Paramount+'s official cast announcement](https://www.paramountplus.com/sneak-peak/survivor-season-51-cast/), credited to CBS. Photos remain hosted by the publisher, with visible attribution and an initials fallback when absent or unavailable. Future seasons require their own verified mapping.

Verification commands from the repository root:

```text
node --test frontend/tests/palette.test.cjs frontend/tests/player-profiles.test.cjs
.venv\Scripts\python.exe -m unittest discover -s tests -p test_player_profiles.py -v
.venv\Scripts\python.exe -m unittest discover -s tests -p test_api.py -v
.venv\Scripts\python.exe -m unittest discover -s tests -p test_deployment*.py -v
git diff --check -- frontend src/survivor_calculator/api.py src/survivor_calculator/server.py
```

Build the Next.js frontend with `npm.cmd run build` from `frontend/`, or use an isolated copy when a development server is already using its `.next` directory. No new production dependencies are required.
