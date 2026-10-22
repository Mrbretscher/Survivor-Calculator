"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import PlayerBoard from "./player-board";
import {
  contestantHref, formatPercent, formatSnapshot, getTimelinePrediction,
  timelineStateKey, type PredictionPayload, type TimelineIndex, type TimelineState
} from "../lib/predictions";

export default function PredictionExplorer({
  current, timeline, showTimeline = true
}: { current: PredictionPayload; timeline: TimelineIndex | null; showTimeline?: boolean }) {
  const [selection, setSelection] = useState<TimelineState | null>(null);
  const [replay, setReplay] = useState<PredictionPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [unavailable, setUnavailable] = useState<{ season: number; episode: number } | null>(null);
  const [season, setSeason] = useState<number | "">("");
  const [episode, setEpisode] = useState<number | "">("");
  const request = useRef(0);
  const states = timeline?.states ?? [];
  const coverage = timeline?.episodes ?? states.map((state) => ({ ...state, available: true }));
  const seasons = [...new Set(coverage.map((item) => item.season))].sort((a, b) => b - a);
  const seasonStates = states.filter((state) => state.season === season);
  const episodes = [...new Set(coverage.filter((item) => item.season === season).map((item) => item.episode))].sort((a, b) => a - b);
  const checkpoints = seasonStates.filter((state) => state.episode === episode);
  const payload = showTimeline ? replay : current;
  const highestBoot = payload?.projected_boot_order[0];
  const lastTraining = Math.max(0, ...(current.metadata.training_seasons ?? []));

  async function selectState(state: TimelineState) {
    const token = ++request.current;
    setSeason(state.season);
    setEpisode(state.episode);
    setSelection(state);
    setUnavailable(null);
    setReplay(null);
    setError(null);
    setLoading(true);
    try {
      const result = await getTimelinePrediction(state, current.metadata.generated_at);
      if (request.current === token) setReplay(result);
    } catch (reason) {
      if (request.current === token) setError(reason instanceof Error ? reason.message : "Checkpoint unavailable. Please try again.");
    } finally {
      if (request.current === token) setLoading(false);
    }
  }

  function showCurrent() {
    ++request.current;
    setSelection(null);
    setUnavailable(null);
    setSeason(current.metadata.current_season);
    setEpisode(current.metadata.latest_episode);
    setReplay(current);
    setError(null);
    setLoading(false);
  }

  function selectSeason(value: string) {
    ++request.current;
    setSeason(value === "" ? "" : Number(value));
    setEpisode("");
    setSelection(null);
    setReplay(null);
    setUnavailable(null);
    setError(null);
    setLoading(false);
  }

  function selectEpisode(seasonValue: number, episodeValue: number) {
    const state = states.find((item) => item.season === seasonValue && item.episode === episodeValue);
    if (state) {
      void selectState(state);
    } else {
      ++request.current;
      setSeason(seasonValue);
      setEpisode(episodeValue);
      setSelection(null);
      setUnavailable({ season: seasonValue, episode: episodeValue });
      setReplay(null);
      setError(null);
      setLoading(false);
    }
  }

  return <>
    {showTimeline && <section className="timelinePanel" aria-labelledby="timeline-title">
      <div className="sectionHeader">
        <div>
          <p className="eyebrow">Explore predictions over time</p>
          <h2 id="timeline-title">Timeline</h2>
        </div>
        <button className="timelineButton" type="button" onClick={showCurrent} disabled={!selection && !unavailable}>Back to current prediction</button>
      </div>
      {timeline && coverage.length ? <>
        <p className="boardNote" id="timeline-help">
          Select an episode to see its recorded forecast checkpoints.
          {lastTraining > 0 ? ` This model was trained through season ${lastTraining}; only later seasons are available.` : " This model has no fitted training seasons."}
          {" "}Past predictions are reconstructed with today’s model, using information available at that checkpoint.
        </p>
        <div className="timelineControls" aria-describedby="timeline-help">
          <label>Season
            <select value={season} onChange={(event) => selectSeason(event.target.value)}>
              <option value="" disabled>Select season</option>
              {seasons.map((value) => <option key={value} value={value}>Season {value}{value === current.metadata.current_season ? " · Current" : " · Held out"}</option>)}
            </select>
          </label>
          <label>Episode
            <select disabled={season === ""} value={episode} onChange={(event) => {
              if (season !== "") selectEpisode(season, Number(event.target.value));
            }}>
              <option value="" disabled>Select episode</option>
              {episodes.map((value) => <option key={value} value={value}>Episode {value}{coverage.some((item) => item.season === season && item.episode === value && item.available) ? "" : " · Unavailable"}</option>)}
            </select>
          </label>
          <label>Checkpoint
            <select disabled={!checkpoints.length} value={selection ? timelineStateKey(selection) : checkpoints.length ? timelineStateKey(checkpoints[checkpoints.length - 1]) : ""} onChange={(event) => {
              const state = checkpoints.find((item) => timelineStateKey(item) === event.target.value);
              if (state) void selectState(state);
            }}>
              {!checkpoints.length && <option value="">{episode === "" ? "Select episode first" : "No validated forecast"}</option>}
              {checkpoints.map((state) => <option key={timelineStateKey(state)} value={timelineStateKey(state)}>
                {state.checkpoint} exits completed · {state.active_players} active players
              </option>)}
            </select>
          </label>
          <button className="timelineButton" type="button" disabled={!checkpoints.length} onClick={() => {
            const state = selection ?? checkpoints[checkpoints.length - 1];
            if (state) void selectState(state);
          }}>View checkpoint</button>
        </div>
        <p className="mutedText">Episodes without a validated voting forecast are marked unavailable. Multiple checkpoints preserve separate councils within an episode.</p>
      </> : <p className="boardNote">Timeline is temporarily unavailable for this snapshot. Please try again later.</p>}
    </section>}

    <div aria-live="polite" aria-busy={loading}>
      {selection && <p className="timelineContext">Timeline · Season {selection.season} · Episode {selection.episode} · {selection.checkpoint} exits completed</p>}
      {unavailable && <section className="timelinePanel" aria-labelledby="episode-unavailable-title">
        <h1 id="episode-unavailable-title">Season {unavailable.season}, episode {unavailable.episode}</h1>
        <h2>Prediction unavailable</h2>
        <p>This episode has no validated voting forecast checkpoint in the source data. Missing or ambiguous records, non-voting exits, and terminal states cannot support a reconstructed prediction.</p>
        <p>Select another episode or return to the current prediction.</p>
      </section>}
      {loading && <p role="status" className="boardNote">Loading checkpoint…</p>}
      {error && <div className="timelineError" role="alert"><p>{error}</p><button className="timelineButton" type="button" onClick={() => { if (selection) void selectState(selection); }}>Try again</button></div>}
      {payload && <header className="masthead" aria-labelledby="dashboard-title">
        <div>
          <p className="eyebrow">{selection ? "Reconstructed prediction" : "Survivor Calculator"}</p>
          <h1 id="dashboard-title">Season {payload.metadata.current_season} prediction dashboard</h1>
          <p className="lede">Episode {payload.metadata.latest_episode}, final {payload.metadata.latest_final_n}. {payload.metadata.disclaimer}</p>
        </div>
        <dl className="statusGrid" aria-label="Prediction run summary">
          <SummaryStat label="Active players" value={String(payload.metadata.active_players)} />
          <SummaryStat label="Model" value={payload.metadata.model_name.split("_").join(" ")} />
          <SummaryStat label="Highest boot risk" value={highestBoot ? selection
            ? `${highestBoot.castaway} ${formatPercent(highestBoot.projected_boot_probability)}`
            : <Link className="contestantLink" href={contestantHref(highestBoot.castaway_id)}>{highestBoot.castaway} {formatPercent(highestBoot.projected_boot_probability)}</Link>
            : "Unavailable"} />
          <SummaryStat label={selection ? "Reconstructed" : "Generated"} value={formatSnapshot(payload.metadata.generated_at)} />
        </dl>
      </header>}
    </div>
    {payload && <PlayerBoard key={selection ? timelineStateKey(selection) : "current"} players={payload.players} bootOrder={payload.projected_boot_order} historical={Boolean(selection)} />}
  </>;
}

function SummaryStat({ label, value }: { label: string; value: React.ReactNode }) {
  return <div className="summaryStat"><dt>{label}</dt><dd>{value}</dd></div>;
}
