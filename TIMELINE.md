# Timeline

Open **Timeline** in the main navigation, or visit `/timeline`, to browse forecasts for recorded episodes and checkpoints. The **Predictions** page at `/` shows the latest current-season forecast.

Timeline opens with only its selection panel and no prediction loaded. Choose a season, then an episode and checkpoint to view its forecast. Changing the season clears the displayed forecast until you choose another episode. Separate checkpoints preserve multiple recorded councils within an episode. The selected board shows the recorded active cast, next-boot probabilities, exploratory winner scores and projected boot order. **Back to current prediction** restores the latest checkpoint on Timeline; **Predictions** in the navigation returns to the current-only page.

## Training boundary and interpretation

The same fitted model scores the current board and Timeline. Ordinary chronological builds exclude the latest five completed seasons from training. Timeline only offers seasons after the model's last training season; its controls describe that boundary using snapshot metadata. If evaluation lacks enough completed seasons, all available historical seasons train the model and only later unseen seasons are eligible.

Historical forecasts are reconstructions using today's model and retained source data. They are not archived forecasts proven to have been issued before broadcast. Each checkpoint uses its recorded roster, completed-council information and conservatively lagged episode features. Winner estimates and projected boot order remain exploratory.

Known episodes without a validated voting forecast remain selectable and explain why predictions are unavailable. Missing/ambiguous records, non-voting exits or terminal states can prevent a forecast. Historical boards omit links to current-season contestant profiles.

## Build and serve

Run the normal build or refresh. Timeline is included in the existing ignored `data/processed/current_predictions.json` artifact, and deployment bundles include that artifact. API requests and application startup do not fit models or download raw data. Older snapshots keep serving current predictions but need rebuilding to enable Timeline.

- `GET /api/predictions/timeline`: episode coverage and available checkpoint index.
- `GET /api/predictions/timeline/{season}/{episode}/{checkpoint}`: one prepared prediction board; the checkpoint counts completed exits.

Training-season, unknown and unavailable checkpoint requests return 404. If the frontend's snapshot has been replaced by a newer one, it asks for a refresh rather than displaying predictions from mixed snapshots.

The existing 60-second frontend revalidation policy applies. Keep the API and frontend pointed at the same snapshot when building or deploying. In Netlify, `NEXT_PUBLIC_API_BASE_URL` must be the public API URL, not a local preview port.
