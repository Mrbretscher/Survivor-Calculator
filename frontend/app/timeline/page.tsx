import type { Metadata } from "next";
import Link from "next/link";
import PredictionExplorer from "../prediction-explorer";
import { getPredictions, getTimeline } from "../../lib/predictions";

export const metadata: Metadata = {
  title: "Timeline | Survivor Calculator"
};

export default async function TimelinePage() {
  const [current, timeline] = await Promise.all([getPredictions(), getTimeline()]);
  if (!current) {
    return (
      <main className="shell">
        <section className="unavailablePanel" aria-labelledby="timeline-unavailable-title">
          <p className="eyebrow">Timeline</p>
          <h1 id="timeline-unavailable-title">Timeline temporarily unavailable</h1>
          <p className="lede">The prediction snapshot could not be loaded. Please refresh to try again.</p>
          <Link className="profileLink" href="/">Return to current predictions</Link>
        </section>
      </main>
    );
  }
  const matchingTimeline = timeline?.metadata.generated_at === current.metadata.generated_at ? timeline : null;
  return (
    <main className="shell">
      <a className="skipLink" href="#current-board">Skip to prediction board</a>
      <PredictionExplorer current={current} timeline={matchingTimeline} />
    </main>
  );
}
