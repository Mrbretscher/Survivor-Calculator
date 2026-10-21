import type { Metadata } from "next";
import { getPredictions } from "../../lib/predictions";

export const metadata: Metadata = {
  title: "Methodology | Survivor Calculator"
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

export default async function MethodologyPage() {
  const payload = await getPredictions();

  if (!payload) {
    return (
      <main className="shell">
        <section className="unavailablePanel" aria-labelledby="methodology-unavailable-title">
          <p className="eyebrow">Methodology</p>
          <h1 id="methodology-unavailable-title">Evaluation temporarily unavailable</h1>
          <p className="lede">The prediction API could not be reached. Please refresh to try again.</p>
        </section>
      </main>
    );
  }

  const evaluation = normalizeEvaluation(payload.evaluation);

  return (
    <main className="shell">
      <header className="pageIntro">
        <p className="eyebrow">Understand the forecast</p>
        <h1>Model methodology</h1>
        <p className="lede">Validation splits, holdout results, and limitations for the current prediction snapshot.</p>
      </header>
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

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
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
