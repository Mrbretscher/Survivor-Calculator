type Player = {
  castaway_id: string;
  castaway: string;
  tribe: string;
  occupation: string;
  soc_major_group: string;
  next_boot_probability: number;
  winner_probability: number;
  explanation: string[];
};

type PredictionPayload = {
  metadata: {
    current_season: number;
    latest_episode: number;
    latest_final_n: number;
    active_players: number;
    disclaimer: string;
  };
  players: Player[];
  projected_boot_order: Array<{
    projected_order: number;
    castaway: string;
    projected_final_n_before_boot: number;
    projected_boot_probability: number;
  }>;
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
    return (
      <main className="shell">
        <section className="hero">
          <p className="eyebrow">Survivor Calculator</p>
          <h1>Start the Python API to view current predictions.</h1>
          <p className="subtle">Run the pipeline, then serve the API with uvicorn. The frontend will read the current-season prediction contract from the backend.</p>
        </section>
      </main>
    );
  }

  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">Season {payload.metadata.current_season}</p>
        <h1>Current prediction board</h1>
        <p className="subtle">
          Latest episode {payload.metadata.latest_episode}. Final {payload.metadata.latest_final_n}. {payload.metadata.disclaimer}
        </p>
      </section>

      <section className="grid">
        {payload.players.map((player) => (
          <article className="player" key={player.castaway_id}>
            <div>
              <h2>{player.castaway}</h2>
              <p>{player.tribe} · {player.occupation || "Occupation under review"}</p>
            </div>
            <Metric label="Winner" value={player.winner_probability} />
            <Metric label="Next boot" value={player.next_boot_probability} />
            <p className="signal">{player.explanation.slice(0, 2).join(" ")}</p>
          </article>
        ))}
      </section>

      <section className="panel">
        <h2>Projected boot order</h2>
        <div className="table">
          {payload.projected_boot_order.map((row) => (
            <div className="tableRow" key={`${row.projected_order}-${row.castaway}`}>
              <span>{row.projected_order}</span>
              <strong>{row.castaway}</strong>
              <span>Final {row.projected_final_n_before_boot}</span>
              <span>{formatPercent(row.projected_boot_probability)}</span>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{formatPercent(value)}</strong>
      <div className="bar">
        <i style={{ width: `${Math.max(2, value * 100)}%` }} />
      </div>
    </div>
  );
}

function formatPercent(value: number) {
  return new Intl.NumberFormat("en-US", {
    style: "percent",
    maximumFractionDigits: 1
  }).format(value);
}

