export type Player = {
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

export type ProjectedBoot = {
  projected_order: number;
  projected_final_n_before_boot: number;
  castaway_id: string;
  castaway: string;
  projected_boot_probability: number;
};

export type PredictionPayload = {
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
    training_seasons?: number[];
    training_policy?: string;
  };
  players: Player[];
  projected_boot_order: ProjectedBoot[];
  evaluation: Record<string, unknown>;
};

export type TimelineState = {
  season: number;
  episode: number;
  checkpoint: number;
  final_n: number;
  active_players: number;
};

export type TimelineIndex = {
  metadata: PredictionPayload["metadata"];
  note: string;
  states: TimelineState[];
  episodes?: { season: number; episode: number; available: boolean }[];
};

export type TimelinePrediction = PredictionPayload & {
  timeline_context: TimelineState & { note: string };
};

export async function getTimeline(): Promise<TimelineIndex | null> {
  try {
    const response = await fetch(`${API_BASE}/api/predictions/timeline`, {
      next: { revalidate: 60 }
    });
    if (!response.ok) return null;
    const payload = await response.json();
    return Array.isArray(payload.states) ? payload : null;
  } catch {
    return null;
  }
}

export function timelineStateKey(state: TimelineState): string {
  return `${state.season}/${state.episode}/${state.checkpoint}`;
}

export async function getTimelinePrediction(
  state: TimelineState,
  generatedAt: string
): Promise<TimelinePrediction> {
  const response = await fetch(`${API_BASE}/api/predictions/timeline/${timelineStateKey(state)}`, {
    cache: "no-store"
  });
  if (!response.ok) throw new Error("This checkpoint is unavailable. Refresh to load the latest Timeline.");
  const payload: TimelinePrediction = await response.json();
  if (payload.metadata.generated_at !== generatedAt) {
    throw new Error("Predictions have updated. Refresh to load the latest Timeline.");
  }
  if (!payload.timeline_context || timelineStateKey(payload.timeline_context) !== timelineStateKey(state)) {
    throw new Error("The selected checkpoint could not be loaded. Please try again.");
  }
  return payload;
}

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export async function getPredictions(): Promise<PredictionPayload | null> {
  try {
    const response = await fetch(`${API_BASE}/api/predictions/current`, {
      next: { revalidate: 60 }
    });
    return response.ok ? await response.json() : null;
  } catch {
    return null;
  }
}

export function contestantHref(castawayId: string): string {
  return `/contestants/${encodeURIComponent(castawayId)}`;
}

export function groupByTribe<T extends { tribe: string }>(
  rows: T[]
): { tribe: string; rows: T[] }[] {
  const groups = new Map<string, { tribe: string; rows: T[] }>();
  for (const row of rows) {
    const tribe = row.tribe.trim() || "Unknown tribe";
    const key = tribe.toLowerCase();
    if (!groups.has(key)) groups.set(key, { tribe, rows: [] });
    groups.get(key)!.rows.push(row);
  }
  return [...groups.values()].sort((first, second) =>
    first.tribe.localeCompare(second.tribe)
  );
}

export function bootRowsWithTribes(players: Player[], rows: ProjectedBoot[]) {
  const tribes = new Map(
    players.map((player) => [player.castaway_id, player.tribe])
  );
  return rows.map((row) => ({
    ...row,
    tribe: tribes.get(row.castaway_id) ?? "Unknown tribe"
  }));
}

export function formatPercent(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "percent",
    maximumFractionDigits: 1
  }).format(value);
}

export function formatSnapshot(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "Unavailable";
  return (
    new Intl.DateTimeFormat("en-US", {
      dateStyle: "medium",
      timeStyle: "short",
      timeZone: "America/New_York"
    }).format(date) + " ET"
  );
}
