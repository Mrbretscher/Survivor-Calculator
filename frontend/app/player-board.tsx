"use client";

import Link from "next/link";
import { useState } from "react";
import {
  bootRowsWithTribes,
  contestantHref,
  formatPercent,
  groupByTribe,
  type Player,
  type ProjectedBoot
} from "../lib/predictions";

export default function PlayerBoard({
  players,
  bootOrder
}: {
  players: Player[];
  bootOrder: ProjectedBoot[];
}) {
  const [view, setView] = useState<"tribe" | "all">("tribe");
  const board = players.map((player, index) => ({
    ...player,
    rank: index + 1
  }));
  const bootGroups = groupByTribe(bootRowsWithTribes(players, bootOrder));

  return (
    <>
      <section
        className="section"
        id="current-board"
        aria-labelledby="current-board-title"
      >
        <div className="sectionHeader">
          <div>
            <p className="eyebrow">Current board</p>
            <h2 id="current-board-title">Winner and next-boot probabilities</h2>
          </div>
          <ViewToggle view={view} onChange={setView} label="Board grouping" />
        </div>
        <p className="boardNote">
          View contestants and boot order by current tribe or together.
          Percentages use the full active cast.
        </p>
        <div id="contestant-board">
          {view === "tribe" ? (
            groupByTribe(board).map((group, index) => (
              <section
                className="tribeGroup"
                key={group.tribe}
                aria-labelledby={`board-tribe-${index}`}
              >
                <TribeHeading
                  tribe={group.tribe}
                  count={group.rows.length}
                  id={`board-tribe-${index}`}
                />
                <div className="playerGrid">
                  {group.rows.map((player) => (
                    <PlayerCard key={player.castaway_id} player={player} />
                  ))}
                </div>
              </section>
            ))
          ) : (
            <div className="playerGrid">
              {board.map((player) => (
                <PlayerCard key={player.castaway_id} player={player} />
              ))}
            </div>
          )}
        </div>
      </section>

      <section
        className="section splitSection"
        aria-labelledby="boot-order-title"
      >
        <div className="sectionHeader">
          <div>
            <p className="eyebrow">Projection</p>
            <h2 id="boot-order-title">Projected boot order</h2>
          </div>
          <ViewToggle
            view={view}
            onChange={setView}
            label="Boot order grouping"
          />
        </div>
        <p className="boardNote">
          Tribe order preserves the overall forecast order within each tribe.
          Next-boot probability is across all active players; it does not assume
          a particular tribe attends Tribal Council.
        </p>
        {view === "tribe" ? (
          bootGroups.map((group, index) => (
            <section
              className="tribeGroup"
              key={group.tribe}
              aria-labelledby={`boot-tribe-${index}`}
            >
              <TribeHeading
                tribe={group.tribe}
                count={group.rows.length}
                id={`boot-tribe-${index}`}
              />
              <BootTable rows={group.rows} tribe={group.tribe} />
            </section>
          ))
        ) : (
          <BootTable rows={bootOrder} />
        )}
      </section>
    </>
  );
}

function ViewToggle({
  view,
  onChange,
  label
}: {
  view: "tribe" | "all";
  onChange: (view: "tribe" | "all") => void;
  label: string;
}) {
  return (
    <div className="viewToggle" role="group" aria-label={label}>
      <button
        aria-pressed={view === "tribe"}
        onClick={() => onChange("tribe")}
        type="button"
      >
        By tribe
      </button>
      <button
        aria-pressed={view === "all"}
        onClick={() => onChange("all")}
        type="button"
      >
        All players
      </button>
    </div>
  );
}

function TribeHeading({
  tribe,
  count,
  id
}: {
  tribe: string;
  count: number;
  id: string;
}) {
  return (
    <div className="tribeGroupHeader">
      <h3 id={id}>
        <span className="tribe" data-tribe={tribe.toLowerCase()}>
          {tribe}
        </span>
      </h3>
      <span>
        {count} active player{count === 1 ? "" : "s"}
      </span>
    </div>
  );
}

export function PlayerCard({ player }: { player: Player & { rank: number } }) {
  return (
    <article
      className="playerCard"
      aria-labelledby={`player-${player.castaway_id}`}
    >
      <div className="playerHeader">
        <div>
          <p className="rank">Overall board position {player.rank}</p>
          <h3 id={`player-${player.castaway_id}`}>
            <Link
              className="contestantLink"
              href={contestantHref(player.castaway_id)}
            >
              {player.castaway}
            </Link>
          </h3>
        </div>
        <span className="tribe" data-tribe={player.tribe.trim().toLowerCase()}>
          {player.tribe}
        </span>
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
          <dd>
            {player.soc_title
              ? `${player.soc_title}${player.soc_code ? ` (${player.soc_code})` : ""}`
              : "Manual review"}
          </dd>
        </div>
        <div>
          <dt>SOC major group</dt>
          <dd>{player.soc_major_group || "Manual review"}</dd>
        </div>
      </dl>
      <div className="metricsRow">
        <ProbabilityMeter
          label="Winner"
          value={player.winner_probability}
          tone="positive"
        />
        <ProbabilityMeter
          label="Next boot"
          value={player.next_boot_probability}
          tone="risk"
        />
      </div>
      <p className="signal">
        {player.explanation.length
          ? player.explanation.join(" ")
          : "No model signal notes available."}
      </p>
      <Link className="profileLink" href={contestantHref(player.castaway_id)}>
        View contestant profile <span aria-hidden="true">→</span>
      </Link>
    </article>
  );
}

export function ProbabilityMeter({
  label,
  value,
  tone
}: {
  label: string;
  value: number;
  tone: "positive" | "risk";
}) {
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

export function BootTable({
  rows,
  tribe
}: {
  rows: ProjectedBoot[];
  tribe?: string;
}) {
  return (
    <div
      className="tableFrame"
      role="region"
      aria-label={
        tribe
          ? `${tribe} projected boot order table`
          : "Projected boot order table"
      }
      tabIndex={0}
    >
      <table>
        <thead>
          <tr>
            <th scope="col">{tribe ? "Tribe order" : "Order"}</th>
            <th scope="col">Contestant</th>
            <th scope="col">
              {tribe ? "Overall order" : "Final N before boot"}
            </th>
            <th scope="col">Next-boot probability</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={row.castaway_id}>
              <td>{tribe ? index + 1 : row.projected_order}</td>
              <th scope="row">
                <Link
                  className="contestantLink"
                  href={contestantHref(row.castaway_id)}
                >
                  {row.castaway}
                </Link>
              </th>
              <td>
                {tribe
                  ? row.projected_order
                  : row.projected_final_n_before_boot}
              </td>
              <td>{formatPercent(row.projected_boot_probability)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
