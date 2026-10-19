import AnalyticsPanel from "./analytics-panel";

type Player = {
  castaway_id: string;
  castaway: string;
  tribe: string;
  original_tribe: string;
  tribe_status: string;
  tribe_status_display: string;
  occupation: string;
  soc_code: string;
  soc_title: string;
  soc_major_group: string;
  raw_next_boot_risk: number;
  next_boot_probability: number;
  winner_probability: number;
  explanation: string[];
};

type ProjectedBoot = {
  projected_order: number;
  projected_final_n_before_boot: number;
  castaway_id: string;
  castaway: string;
  projected_boot_probability: number;
};

type EvaluationComparison = {
  name: string;
  events: number;
  top1_accuracy: number;
  top3_recall: number;
  brier_score: number;
  log_loss: number;
  mean_actual_probability: number;
};

type CalibrationBin = {
  range: string;
  count: number;
  mean_predicted_probability: number;
  observed_boot_rate: number;
  absolute_error: number;
};

type PredictionPayload = {
  metadata: {
    generated_at: string;
    model_name: string;
    model_selection_policy: string;
    source_workbook: string;
    current_season: number;
    latest_episode: number;
    latest_final_n: number;
    active_players: number;
    disclaimer: string;
  };
  players: Player[];
  projected_boot_order: ProjectedBoot[];
  evaluation: Record<string, unknown>;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

async function getPredictions(): Promise<PredictionPayload | null> {
  try {
    const response = await fetch(`${API_BASE}/api/predictions/current`, {
      next: { revalidate: 60 }
    });
    if (!response.ok) {
      return null;
    }
    return response.json();
  } catch {
    return null;
  }
}

export default async function Home() {
  const payload = await getPredictions();

  if (!payload) {
    return <UnavailableDashboard apiBase={API_BASE} />;
  }

  const evaluation = normalizeEvaluation(payload.evaluation);
  const board = payload.players.map((player, index) => ({ ...player, rank: index + 1 }));
  const highestBoot = payload.projected_boot_order[0];

  return (
    <main className="shell">
      <a className="skipLink" href="#current-board">Skip to current board</a>

      <header className="masthead" aria-labelledby="dashboard-title">
        <div>
          <p className="eyebrow">Survivor Calculator</p>
          <h1 id="dashboard-title">Season {payload.metadata.current_season} prediction dashboard</h1>
          <p className="lede">
            Episode {payload.metadata.latest_episode}, final {payload.metadata.latest_final_n}. {payload.metadata.disclaimer}
          </p>
        </div>
        <dl className="statusGrid" aria-label="Prediction run summary">
          <SummaryStat label="Active players" value={payload.metadata.active_players.toString()} />
          <SummaryStat label="Model" value={formatModelName(payload.metadata.model_name)} />
          <SummaryStat
            label="Highest boot risk"
            value={highestBoot ? `${highestBoot.castaway} ${formatPercent(highestBoot.projected_boot_probability)}` : "Unavailable"}
          />
          <SummaryStat label="Generated" value={formatDateTime(payload.metadata.generated_at)} />
        </dl>
      </header>

      <section className="section" id="current-board" aria-labelledby="current-board-title">
        <div className="sectionHeader">
          <div>
            <p className="eyebrow">Current Board</p>
            <h2 id="current-board-title">Winner and next-boot probabilities</h2>
          </div>
          <p className="sectionNote">
            Ranking reflects the latest generated prediction file.
          </p>
        </div>

        <div className="playerGrid">
          {board.map((player) => (
            <article className="playerCard" key={player.castaway_id} aria-labelledby={`player-${player.castaway_id}`}>
              <div className="playerHeader">
                <div>
                  <p className="rank">Rank {player.rank}</p>
                  <h3 id={`player-${player.castaway_id}`}>{player.castaway}</h3>
                </div>
                <span className="tribe" data-tribe={player.tribe.trim().toLowerCase()}>{player.tribe}</span>
              </div>
              <dl className="playerMeta">
                <div>
                  <dt>Tribe status</dt>
                  <dd>{player.tribe_status_display}</dd>
                </div>
                {player.tribe_status_display === "Swapped" ? (
                  <div>
                    <dt>Original tribe</dt>
                    <dd>{player.original_tribe}</dd>
                  </div>
                ) : null}
                <div>
                  <dt>Occupation</dt>
                  <dd>{player.occupation || "Under review"}</dd>
                </div>
                <div>
                  <dt>SOC title</dt>
                  <dd>{formatSocTitle(player)}</dd>
                </div>
                <div>
                  <dt>SOC major group</dt>
                  <dd>{player.soc_major_group || "Manual review"}</dd>
                </div>
              </dl>
              <div className="metricsRow">
                <ProbabilityMeter label="Winner" value={player.winner_probability} tone="positive" />
                <ProbabilityMeter label="Next boot" value={player.next_boot_probability} tone="risk" />
              </div>
              <p className="signal">{player.explanation.length ? player.explanation.join(" ") : "No model signal notes available."}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="section splitSection" aria-labelledby="boot-order-title">
        <div className="sectionHeader">
          <div>
            <p className="eyebrow">Projection</p>
            <h2 id="boot-order-title">Projected boot order</h2>
          </div>
          <p className="sectionNote">Boot order is a ranked view of the current next-boot probabilities.</p>
        </div>

        <div className="tableFrame" role="region" aria-label="Projected boot order table" tabIndex={0}>
          <table>
            <thead>
              <tr>
                <th scope="col">Order</th>
                <th scope="col">Castaway</th>
                <th scope="col">Final N before boot</th>
                <th scope="col">Boot probability</th>
              </tr>
            </thead>
            <tbody>
              {payload.projected_boot_order.map((row) => (
                <tr key={row.castaway_id}>
                  <td>{row.projected_order}</td>
                  <th scope="row">{row.castaway}</th>
                  <td>{row.projected_final_n_before_boot}</td>
                  <td>{formatPercent(row.projected_boot_probability)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <AnalyticsPanel />

      <section className="section" aria-labelledby="evaluation-title">
        <div className="sectionHeader">
          <div>
            <p className="eyebrow">Evaluation</p>
            <h2 id="evaluation-title">Methodology and holdout results</h2>
          </div>
          <p className="sectionNote">{payload.metadata.model_selection_policy}</p>
        </div>

        <div className="methodGrid">
          <article className="methodPanel">
            <h3>Validation Split</h3>
            <dl className="detailList">
              <Detail label="Strategy" value={evaluation.splitStrategy} />
              <Detail label="Training seasons" value={evaluation.trainingSeasons} />
              <Detail label="Holdout seasons" value={evaluation.holdoutSeasons} />
              <Detail label="Events evaluated" value={evaluation.eventCount} />
              <Detail label="Candidates evaluated" value={evaluation.candidateCount} />
            </dl>
          </article>

          <article className="methodPanel">
            <h3>Primary Metrics</h3>
            {evaluation.status === "ok" ? (
              <dl className="detailList metricDetails">
                <Detail label="Top-1 accuracy" value={formatPercent(evaluation.top1Accuracy)} />
                <Detail label="Top-3 recall" value={formatPercent(evaluation.top3Recall)} />
                <Detail label="Brier score" value={formatDecimal(evaluation.brierScore)} />
                <Detail label="Log loss" value={formatDecimal(evaluation.logLoss)} />
              </dl>
            ) : (
              <p className="mutedText">{evaluation.reason || "Evaluation did not run for this prediction file."}</p>
            )}
          </article>
        </div>

        {evaluation.comparisons.length > 0 ? (
          <div className="tableFrame comparisonFrame" role="region" aria-label="Baseline comparison table" tabIndex={0}>
            <table>
              <caption>Baseline comparisons</caption>
              <thead>
                <tr>
                  <th scope="col">Model</th>
                  <th scope="col">Events</th>
                  <th scope="col">Top-1</th>
                  <th scope="col">Top-3</th>
                  <th scope="col">Brier</th>
                  <th scope="col">Log loss</th>
                </tr>
              </thead>
              <tbody>
                {evaluation.comparisons.map((row) => (
                  <tr key={row.name}>
                    <th scope="row">{formatModelName(row.name)}</th>
                    <td>{formatInteger(row.events)}</td>
                    <td>{formatPercent(row.top1_accuracy)}</td>
                    <td>{formatPercent(row.top3_recall)}</td>
                    <td>{formatDecimal(row.brier_score)}</td>
                    <td>{formatDecimal(row.log_loss)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}

        {evaluation.calibrationBins.length > 0 ? (
          <div className="calibrationGrid" aria-label="Calibration bins">
            {evaluation.calibrationBins.map((bin) => (
              <article className="calibrationBin" key={bin.range}>
                <h3>{bin.range}</h3>
                <dl>
                  <Detail label="Count" value={formatInteger(bin.count)} />
                  <Detail label="Mean predicted" value={formatPercent(bin.mean_predicted_probability)} />
                  <Detail label="Observed boot rate" value={formatPercent(bin.observed_boot_rate)} />
                  <Detail label="Absolute error" value={formatPercent(bin.absolute_error)} />
                </dl>
              </article>
            ))}
          </div>
        ) : null}

        {evaluation.notes.length > 0 ? (
          <aside className="notesPanel" aria-labelledby="notes-title">
            <h3 id="notes-title">Methodology Notes</h3>
            <ul>
              {evaluation.notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          </aside>
        ) : null}
      </section>
    </main>
  );
}

function UnavailableDashboard({ apiBase }: { apiBase: string }) {
  return (
    <main className="shell shellCentered">
      <section className="unavailablePanel" aria-labelledby="unavailable-title">
        <p className="eyebrow">Survivor Calculator</p>
        <h1 id="unavailable-title">Prediction API unavailable</h1>
        <p className="lede">
          The dashboard could not reach <code>{apiBase}</code>. Start the Python API after building predictions, then refresh this page.
        </p>
        <div className="commandPanel" aria-label="Local startup commands">
          <code>$env:PYTHONPATH = "src"</code>
          <code>python -m survivor_calculator.cli build --workbook survivoR.xlsx</code>
          <code>python -m survivor_calculator.cli serve-api</code>
        </div>
        <p className="mutedText">
          This state is intentional so the frontend remains useful during local setup, failed API starts, or missing generated prediction data.
        </p>
      </section>
    </main>
  );
}

function SummaryStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="summaryStat">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function ProbabilityMeter({ label, value, tone }: { label: string; value: number; tone: "positive" | "risk" }) {
  const percent = Math.round(value * 1000) / 10;
  return (
    <div className="probability">
      <div>
        <span>{label}</span>
        <strong>{formatPercent(value)}</strong>
      </div>
      <div
        className={`meter meter-${tone}`}
        role="meter"
        aria-label={`${label}: ${formatPercent(value)}`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
      >
        <span style={{ width: `${Math.max(1, percent)}%` }} />
      </div>
    </div>
  );
}

function normalizeEvaluation(evaluation: Record<string, unknown>) {
  const split = asRecord(evaluation.split);
  const metrics = asRecord(evaluation.metrics);
  const ranking = asRecord(metrics.ranking);
  const probability = asRecord(metrics.probability);
  const calibration = asRecord(evaluation.calibration);

  const trainingSeasons = asNumberArray(split.training_seasons);
  const holdoutSeasons = asNumberArray(split.holdout_seasons ?? evaluation.holdout_seasons);

  return {
    status: asString(evaluation.status) || "unknown",
    reason: asString(evaluation.reason),
    splitStrategy: formatModelName(asString(split.strategy) || "Unavailable"),
    trainingSeasons: formatRange(trainingSeasons),
    holdoutSeasons: formatRange(holdoutSeasons),
    eventCount: formatInteger(asNumber(metrics.event_count ?? evaluation.events ?? split.evaluated_events)),
    candidateCount: formatInteger(asNumber(metrics.candidate_count ?? split.evaluated_candidates)),
    top1Accuracy: asNumber(ranking.top1_accuracy ?? evaluation.top1_accuracy),
    top3Recall: asNumber(ranking.top3_recall ?? evaluation.top3_recall),
    brierScore: asNumber(probability.brier_score ?? evaluation.brier_score),
    logLoss: asNumber(probability.log_loss ?? evaluation.log_loss),
    comparisons: asComparisonRows(evaluation.baseline_comparisons),
    calibrationBins: asCalibrationBins(calibration.bins),
    notes: asStringArray(evaluation.notes)
  };
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function asNumber(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function asNumberArray(value: unknown): number[] {
  return Array.isArray(value) ? value.filter((item): item is number => typeof item === "number" && Number.isFinite(item)) : [];
}

function asComparisonRows(value: unknown): EvaluationComparison[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map(asRecord).map((row) => ({
    name: asString(row.name) || "unknown",
    events: asNumber(row.events),
    top1_accuracy: asNumber(row.top1_accuracy),
    top3_recall: asNumber(row.top3_recall),
    brier_score: asNumber(row.brier_score),
    log_loss: asNumber(row.log_loss),
    mean_actual_probability: asNumber(row.mean_actual_probability)
  }));
}

function asCalibrationBins(value: unknown): CalibrationBin[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map(asRecord).map((row) => ({
    range: asString(row.range) || "Unspecified",
    count: asNumber(row.count),
    mean_predicted_probability: asNumber(row.mean_predicted_probability),
    observed_boot_rate: asNumber(row.observed_boot_rate),
    absolute_error: asNumber(row.absolute_error)
  }));
}

function formatRange(values: number[]): string {
  if (values.length === 0) {
    return "Unavailable";
  }
  if (values.length === 1) {
    return values[0].toString();
  }
  return `${values[0]}-${values[values.length - 1]}`;
}

function formatPercent(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "percent",
    maximumFractionDigits: 1
  }).format(value);
}

function formatDecimal(value: number): string {
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: 3,
    minimumFractionDigits: 3
  }).format(value);
}

function formatInteger(value: number): string {
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: 0
  }).format(value);
}

function formatModelName(value: string): string {
  return value
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) {
    return "Unavailable";
  }
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit"
  }).format(date);
}

function formatSocTitle(player: Player): string {
  if (!player.soc_title) {
    return "Manual review";
  }
  return player.soc_code ? `${player.soc_title} (${player.soc_code})` : player.soc_title;
}
