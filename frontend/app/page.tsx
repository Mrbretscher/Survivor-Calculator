import Link from "next/link";
import PlayerBoard from "./player-board";
import { API_BASE, contestantHref, getPredictions } from "../lib/predictions";

export default async function Home() {
  const payload = await getPredictions();

  if (!payload) {
    return <UnavailableDashboard apiBase={API_BASE} />;
  }

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
            value={highestBoot ? <Link className="contestantLink" href={contestantHref(highestBoot.castaway_id)}>{highestBoot.castaway} {formatPercent(highestBoot.projected_boot_probability)}</Link> : "Unavailable"}
          />
          <SummaryStat label="Generated" value={formatDateTime(payload.metadata.generated_at)} />
        </dl>
      </header>

      <PlayerBoard players={payload.players} bootOrder={payload.projected_boot_order} />
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

function SummaryStat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="summaryStat">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function formatPercent(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "percent",
    maximumFractionDigits: 1
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
