import type { Metadata } from "next";
import AnalyticsPanel from "../analytics-panel";

export const metadata: Metadata = {
  title: "Analytics | Survivor Calculator"
};

export default function AnalyticsPage() {
  return (
    <main className="shell">
      <header className="pageIntro">
        <p className="eyebrow">Explore the data</p>
        <h1>Survivor analytics</h1>
        <p className="lede">
          Compare player-season records with chart presets, custom metrics, and filters.
        </p>
      </header>
      <AnalyticsPanel />
    </main>
  );
}
