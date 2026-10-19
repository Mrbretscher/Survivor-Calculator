import Link from "next/link";
import { notFound } from "next/navigation";
import { getContestantPortrait } from "../../../lib/contestant-portraits";
import {
  formatPercent,
  formatSnapshot,
  getPredictions
} from "../../../lib/predictions";
import {
  forecastPosition,
  formatCount,
  getPlayerProfile,
  recordedRate
} from "../../../lib/player-profile";
import { ProbabilityMeter } from "../../player-board";
import Portrait from "./portrait";

export default async function ContestantProfile({
  params
}: {
  params: Promise<{ castawayId: string }>;
}) {
  const { castawayId } = await params;
  const predictions = await getPredictions();
  if (!predictions) {
    return (
      <main className="shell">
        <Link className="backLink" href="/">
          ← Back to dashboard
        </Link>
        <section className="unavailablePanel">
          <h1>Profile temporarily unavailable</h1>
          <p>
            The prediction API could not be reached. Please refresh to try
            again.
          </p>
        </section>
      </main>
    );
  }
  const player = predictions.players.find(
    (candidate) => candidate.castaway_id === castawayId
  );
  if (!player) notFound();
  const profile = await getPlayerProfile(castawayId);
  const portrait = getContestantPortrait(
    predictions.metadata.current_season,
    castawayId
  );
  const fullName = portrait?.fullName ?? player.castaway;
  const sameSnapshot =
    profile?.metadata.generated_at === predictions.metadata.generated_at &&
    profile?.metadata.current_season === predictions.metadata.current_season &&
    profile?.player.castaway_id === castawayId;
  const stats =
    sameSnapshot && profile?.stats_status === "available"
      ? profile.stats
      : null;
  const tribePlayers = predictions.players.filter(
    (candidate) =>
      candidate.tribe.trim().toLowerCase() === player.tribe.trim().toLowerCase()
  );
  const bootPosition = predictions.projected_boot_order.find(
    (row) => row.castaway_id === castawayId
  )?.projected_order;
  const teamRate = recordedRate(
    stats?.team_challenge_wins_total,
    stats?.team_challenge_appearances_total
  );
  const immunityRate = recordedRate(
    stats?.individual_immunity_wins_total,
    stats?.individual_immunity_appearances_total
  );

  return (
    <main className="shell profileShell">
      <Link className="backLink" href="/#current-board">
        ← Back to contestant board
      </Link>
      <header className="profileHero">
        <figure className="profilePhoto">
          <Portrait
            key={portrait?.url ?? castawayId}
            name={fullName}
            src={portrait?.url}
          />
          {portrait ? (
            <figcaption>
              <a href={portrait.source} target="_blank" rel="noreferrer">
                {portrait.credit} · Official cast announcement
              </a>
            </figcaption>
          ) : null}
        </figure>
        <div className="profileIntro">
          <p className="eyebrow">
            Season {predictions.metadata.current_season} · Contestant profile
          </p>
          <h1>{fullName}</h1>
          <span
            className="tribe"
            data-tribe={player.tribe.trim().toLowerCase()}
          >
            {player.tribe}
          </span>
          <p className="profileOccupation">
            {player.occupation || "Occupation unavailable"}
            {stats?.age != null ? ` · Age ${formatCount(stats.age)}` : ""}
          </p>
          <dl className="profileFacts">
            <div>
              <dt>Current tribe</dt>
              <dd>
                {player.tribe} · {tribePlayers.length} active players
              </dd>
            </div>
            <div>
              <dt>Starting tribe</dt>
              <dd>{player.original_tribe || "Not available"}</dd>
            </div>
            <div>
              <dt>Tribe status</dt>
              <dd>{player.tribe_status_display}</dd>
            </div>
          </dl>
          <p className="profileSnapshot">
            Forecast state: episode {predictions.metadata.latest_episode}.
            Snapshot updated {formatSnapshot(predictions.metadata.generated_at)}
            .
          </p>
        </div>
      </header>

      <section className="section" aria-labelledby="forecast-title">
        <div className="sectionHeader">
          <div>
            <p className="eyebrow">Forecast</p>
            <h2 id="forecast-title">Where {player.castaway} stands</h2>
          </div>
          <p className="sectionNote">{predictions.metadata.disclaimer}</p>
        </div>
        <div className="profileForecast">
          <article className="methodPanel">
            <ProbabilityMeter
              label="Winner probability"
              value={player.winner_probability}
              tone="positive"
            />
            <p className="mutedText">
              Winner probability rank:{" "}
              {forecastPosition(
                predictions.players,
                player,
                "winner_probability"
              )}{" "}
              of {predictions.players.length}. Equal scores share a rank.
            </p>
          </article>
          <article className="methodPanel">
            <ProbabilityMeter
              label="Next-boot probability"
              value={player.next_boot_probability}
              tone="risk"
            />
            <p className="mutedText">
              Risk rank in {player.tribe}:{" "}
              {forecastPosition(tribePlayers, player, "next_boot_probability")}{" "}
              of {tribePlayers.length}. Percentages use all active players.
            </p>
          </article>
          <article className="methodPanel">
            <h3>Overall boot projection</h3>
            <p className="profileStatValue">
              {bootPosition ?? "Not available"}
            </p>
            <p className="mutedText">
              Position in the current ordered next-boot projection, with
              higher-risk contestants first. This is a model estimate.
            </p>
          </article>
        </div>
        <aside className="notesPanel">
          <h3>Current model signals</h3>
          {player.explanation.length ? (
            <ul>
              {player.explanation.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          ) : (
            <p className="mutedText">
              No model signal notes are available for this snapshot.
            </p>
          )}
        </aside>
      </section>

      <section className="section" aria-labelledby="performance-title">
        <div className="sectionHeader">
          <div>
            <p className="eyebrow">Observed game stats</p>
            <h2 id="performance-title">Performance in the recorded game</h2>
          </div>
          <p className="sectionNote">
            Cumulative totals from the available season records in this
            snapshot.
          </p>
        </div>
        {!stats ? (
          <p className="analyticsStatus" role="status">
            Performance statistics are temporarily unavailable for this
            snapshot. The current forecast is shown above.
          </p>
        ) : null}
        <div className="profileStatsGrid">
          <StatPanel
            title="Challenges"
            value={formatCount(stats?.challenge_wins_total)}
            label="Recorded wins"
          >
            <dl className="detailList">
              <Stat
                label="Appearances"
                value={formatCount(stats?.challenge_appearances_total)}
              />
              <Stat
                label="Team wins / appearances"
                value={`${formatCount(stats?.team_challenge_wins_total)} / ${formatCount(stats?.team_challenge_appearances_total)}`}
              />
              <Stat
                label="Team win rate"
                value={
                  teamRate === null ? "Not available" : formatPercent(teamRate)
                }
              />
              <Stat
                label="Individual immunity wins"
                value={formatCount(stats?.individual_immunity_wins_total)}
              />
              <Stat
                label="Individual immunity appearances"
                value={formatCount(
                  stats?.individual_immunity_appearances_total
                )}
              />
              <Stat
                label="Individual immunity win rate"
                value={
                  immunityRate === null
                    ? "Not available"
                    : formatPercent(immunityRate)
                }
              />
            </dl>
          </StatPanel>
          <StatPanel
            title="Voting record"
            value={formatCount(stats?.votes_received_total)}
            label="Counted votes received"
          >
            <dl className="detailList">
              <Stat
                label="Votes cast"
                value={formatCount(stats?.votes_cast_total)}
              />
            </dl>
            <p className="mutedText">
              Voting totals include recorded voting rounds and revotes. Received
              votes exclude recorded nullified votes.
            </p>
          </StatPanel>
          <StatPanel
            title="On-screen visibility"
            value={formatCount(stats?.confessionals_total)}
            label="Recorded confessionals"
          >
            <dl className="detailList">
              <Stat
                label="Confessional time (seconds)"
                value={formatCount(stats?.confessional_time_total)}
              />
            </dl>
            <p className="mutedText">
              Edited screen time describes visibility in the show; it does not
              measure social influence or jury support.
            </p>
          </StatPanel>
        </div>
        <p className="boardNote">
          Zero means no events were recorded for that metric in the available
          data. “Not available” means the value could not be established.
          Incomplete source coverage can affect these totals.
        </p>
      </section>
      <Link className="backLink" href="/#boot-order-title">
        ← Compare projected boot order
      </Link>
    </main>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function StatPanel({
  title,
  value,
  label,
  children
}: {
  title: string;
  value: string;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <article className="methodPanel profileStatPanel">
      <h3>{title}</h3>
      <p className="profileStatValue">{value}</p>
      <p className="mutedText">{label}</p>
      {children}
    </article>
  );
}
