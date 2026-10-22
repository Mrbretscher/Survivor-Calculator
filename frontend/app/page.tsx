import PredictionExplorer from "./prediction-explorer";
import { API_BASE, getPredictions } from "../lib/predictions";

export default async function Home() {
  const payload = await getPredictions();
  if (!payload) return <UnavailableDashboard apiBase={API_BASE} />;
  return (
    <main className="shell">
      <a className="skipLink" href="#current-board">Skip to prediction board</a>
      <PredictionExplorer current={payload} timeline={null} showTimeline={false} />
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
