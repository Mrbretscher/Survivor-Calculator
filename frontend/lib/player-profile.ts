import { API_BASE, type Player } from "./predictions";

export type ProfileStats = {
  age: number | null;
  challenge_appearances_total: number | null;
  challenge_wins_total: number | null;
  team_challenge_appearances_total: number | null;
  team_challenge_wins_total: number | null;
  individual_immunity_appearances_total: number | null;
  individual_immunity_wins_total: number | null;
  votes_received_total: number | null;
  votes_cast_total: number | null;
  confessionals_total: number | null;
  confessional_time_total: number | null;
};

export type PlayerProfile = {
  metadata: {
    current_season: number;
    latest_episode: number;
    generated_at: string;
    disclaimer: string;
  };
  player: Player;
  stats_status: "available" | "unavailable";
  stats: ProfileStats;
  notes: string[];
};

export async function getPlayerProfile(
  castawayId: string
): Promise<PlayerProfile | null> {
  try {
    const response = await fetch(
      `${API_BASE}/api/players/${encodeURIComponent(castawayId)}`,
      { next: { revalidate: 60 } }
    );
    return response.ok ? await response.json() : null;
  } catch {
    return null;
  }
}

export function formatCount(value: number | null | undefined): string {
  return value == null || !Number.isFinite(value)
    ? "Not available"
    : new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 }).format(
        value
      );
}

export function recordedRate(
  wins: number | null | undefined,
  appearances: number | null | undefined
): number | null {
  return wins == null ||
    appearances == null ||
    !Number.isFinite(wins) ||
    !Number.isFinite(appearances) ||
    appearances <= 0 ||
    wins < 0 ||
    wins > appearances
    ? null
    : wins / appearances;
}

export function forecastPosition(
  players: Player[],
  player: Player,
  metric: "winner_probability" | "next_boot_probability"
): number {
  return (
    1 + players.filter((candidate) => candidate[metric] > player[metric]).length
  );
}
