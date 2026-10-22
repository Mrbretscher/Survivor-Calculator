"""Observed idol assistance, separate from voting coordination and opposition.

Only explicit plays for another identified contestant are edges. Absence of a
record is unknown: this source is not a complete log of opportunities or intent.
Availability is a logical post-council timestamp, not an air/publication time.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Mapping

from survivor_calculator.council_events import Council, season_key

IDOL_SHEETS = ("Advantage Movement", "Advantage Details")
IDOL_FEATURES = ("idol_assist_given_councils", "idol_assist_received_councils")
IDOL_TIMING_VERSION = "identified_idol_post_canonical_council_v1"


def _positive_integer(value: object) -> int | None:
    try:
        number = float(str(value))
        return int(number) if number > 0 and number.is_integer() else None
    except (ValueError, OverflowError):
        return None


def _signature(row: Mapping[str, object]) -> str:
    return hashlib.sha256(json.dumps(dict(row), sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True)
class IdolEvidence:
    """Audited source observations; never infer edges from holders or immunity."""
    observations: tuple[dict[str, object], ...]
    audit: tuple[dict[str, object], ...]
    source_available: bool


def normalize_idol_assistance(
    tables: dict[str, list[dict[str, str | None]]], councils: list[Council],
) -> IdolEvidence:
    """Accept a unique actor/recipient/event with a completed-council clock.

    Advantage IDs are season-scoped. Ambiguous keys, people, types or timestamps
    are excluded with reasons. Self plays never establish social assistance.
    Raw success labels and nullification counts are preserved separately from
    the attempt. A matching ballot count verifies nullification, not whether
    the recipient would otherwise have been eliminated.
    """
    if any(name not in tables for name in IDOL_SHEETS):
        return IdolEvidence((), ({"status": "excluded", "reason": "missing_optional_source_tables"},), False)
    movement = [r for r in tables[IDOL_SHEETS[0]] if season_key(r).startswith("US:")]
    types: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in tables[IDOL_SHEETS[1]]:
        types[season_key(row), str(row.get("advantage_id") or "")].add(str(row.get("advantage_type") or ""))
    people: dict[str, set[str]] = defaultdict(set)
    for row in tables["Castaways"]:
        if row.get("castaway_id"):
            people[season_key(row)].add(str(row["castaway_id"]))
    keyed: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for row in movement:
        keyed[season_key(row), str(row.get("advantage_id") or ""), str(row.get("sequence_id") or "")].add(_signature(row))
    accepted, audit, seen = [], [], set()
    for index, row in enumerate(movement):
        if row.get("event") != "Played":
            continue
        season = season_key(row)
        advantage, sequence = str(row.get("advantage_id") or ""), str(row.get("sequence_id") or "")
        identity = (season, advantage, sequence)
        actor, recipient = str(row.get("castaway_id") or ""), str(row.get("played_for_id") or "")
        episode, day, stage = (_positive_integer(row.get(k)) for k in ("episode", "day", "sog_id"))
        fingerprint = _signature(row)
        entry: dict[str, object] = {"source_sheet": IDOL_SHEETS[0], "us_record_index": index,
            "source_record": dict(row), "source_record_sha256": fingerprint,
            "event_id": "|".join(identity), "actor_id": actor, "recipient_id": recipient,
            "status": "excluded", "reason": "unsupported_advantage_type"}
        audit.append(entry)
        type_values = types.get((season, advantage), set())
        if len(type_values) != 1:
            entry["reason"] = "missing_or_ambiguous_advantage_type"
            continue
        if type_values != {"Hidden Immunity Idol"}:
            continue
        if fingerprint in seen:
            entry["reason"] = "duplicate_source_record"
            continue
        seen.add(fingerprint)
        if len(keyed[identity]) != 1:
            entry["reason"] = "conflicting_event_identity"
            continue
        if not _positive_integer(advantage) or not _positive_integer(sequence):
            entry["reason"] = "missing_event_identity"
            continue
        if actor not in people[season]:
            entry["reason"] = "missing_or_ambiguous_actor"
            continue
        if recipient not in people[season]:
            entry["reason"] = "missing_or_ambiguous_recipient"
            continue
        if actor == recipient:
            entry["reason"] = "self_directed_action"
            continue
        if None in (episode, day, stage):
            entry["reason"] = "missing_or_invalid_availability_timestamp"
            continue
        # Canonical council IDs preserve source stage in their fifth component.
        # Do not substitute n_boots or an assumed offset for this source join.
        matches = [c for c in councils if c.season == season and c.episode == episode
                   and c.day == day and c.order is not None and c.order > 0
                   and len(c.id.split("|")) == 6 and c.id.split("|")[4] == str(stage)
                   and actor in c.participants and recipient in c.participants]
        if len(matches) != 1:
            entry["reason"] = "no_unique_canonical_council"
            continue
        council = matches[0]
        raw_count = row.get("votes_nullified")
        count = _positive_integer(raw_count)
        if str(raw_count) in {"0", "0.0"}:
            count = 0
        recorded_count = sum(b.nullified and b.target == recipient
                             for ballots in council.rounds.values() for b in ballots)
        effect_verified = count is not None and count == recorded_count
        observation = {"event_id": entry["event_id"], "season": season, "actor_id": actor,
            "recipient_id": recipient, "attempt_observed": True, "council_id": council.id,
            "available_after": {"episode": episode, "day": day, "source_stage": stage,
                                "completed_exit_order": council.order},
            "source_success": row.get("success") or None, "source_votes_nullified": raw_count,
            "votes_nullified": count if effect_verified else None,
            "effect_status": ("observed_nullification" if count else "no_recorded_nullification")
                             if effect_verified else "unknown_or_inconsistent_nullification",
            "source_sheet": IDOL_SHEETS[0], "source_record_sha256": fingerprint}
        accepted.append(observation)
        entry.update(status="accepted", reason="identified_post_council_assistance", observation=observation)
    # Several plays for one recipient at the same council cannot each claim the
    # full nullification effect. Retain all attempts, but leave allocation unknown.
    effects = Counter((o["council_id"], o["recipient_id"]) for o in accepted)
    for observation in accepted:
        if effects[observation["council_id"], observation["recipient_id"]] > 1:
            observation.update(votes_nullified=None, effect_status="ambiguous_effect_allocation")
    return IdolEvidence(tuple(sorted(accepted, key=lambda o: str(o["event_id"]))), tuple(audit), True)


def idol_snapshot(evidence: IdolEvidence, players: list[dict[str, object]]) -> dict[str, object]:
    """The same frozen-cutoff contract for historical training and inference.

    Both endpoints must still be active; current tribe matters only when making
    candidate summaries. No future roster fills a missing actor or recipient.
    """
    if not players:
        raise ValueError("Idol assistance requires an active forecast roster.")
    clocks = {(season_key(r), r.get("episode"), r.get("source_stage"), r.get("completed_exit_order")) for r in players}
    ids = [str(r["castaway_id"]) for r in players]
    if len(clocks) != 1 or len(set(ids)) != len(ids):
        raise ValueError("Idol assistance requires one unique forecast state.")
    season, episode, stage, cutoff = next(iter(clocks))
    if _positive_integer(episode) is None or _positive_integer(stage) is None or cutoff is None or int(cutoff) < 0:
        raise ValueError("Idol assistance requires an explicit canonical availability cutoff.")
    visible = [o for o in evidence.observations if o["season"] == season
               and o["available_after"]["episode"] <= int(episode)
               and o["available_after"]["source_stage"] <= int(stage)
               and o["available_after"]["completed_exit_order"] <= int(cutoff)]
    pairs = []
    for actor in sorted(ids):
        for recipient in sorted(ids):
            if actor == recipient:
                continue
            observations = [o for o in visible if o["actor_id"] == actor and o["recipient_id"] == recipient]
            pairs.append({"actor_id": actor, "recipient_id": recipient,
                "assistance_councils": len({o["council_id"] for o in observations}) if observations else None,
                "evidence": observations,
                "explanation": ("Observed idol play for this contestant; strategic assistance is not proof of friendship or alliance membership."
                                if observations else "No identifiable prior assistance observation; relationship unknown.")})
    return {"timing_version": IDOL_TIMING_VERSION, "source_available": evidence.source_available,
            "cutoff": {"season": season, "episode": int(episode), "source_stage": int(stage),
                       "completed_exit_order": int(cutoff)},
            "availability": "After the identified council completes; no wall-clock publication timestamp is supplied.",
            "players": {str(r["castaway_id"]): r.get("tribe") for r in players},
            "pairs": pairs}


def idol_features(snapshot: dict[str, object], players: list[dict[str, object]]) -> dict[str, dict[str, int | None]]:
    """Unique assistance councils involving active current tribemates only.

    Unknowns stay null. Counts measure observed assistance, never a signed bond
    or the absence of opposition. Multiple idols at one council count once.
    """
    tribes = {str(r["castaway_id"]): r.get("tribe") for r in players}
    cutoff = snapshot["cutoff"]
    if (len(tribes) != len(players) or tribes != snapshot["players"]
            or any(season_key(r) != cutoff["season"] or r.get("episode") != cutoff["episode"]
                   or r.get("source_stage") != cutoff["source_stage"]
                   or r.get("completed_exit_order") != cutoff["completed_exit_order"] for r in players)):
        raise ValueError("Idol summaries require the snapshot's same forecast clock and active tribe roster.")
    result = {}
    for player, tribe in tribes.items():
        given, received = set(), set()
        for pair in snapshot["pairs"]:
            actor, recipient = pair["actor_id"], pair["recipient_id"]
            if not tribe or tribe in {"No Tribe", "None"} or tribes[actor] != tribe or tribes[recipient] != tribe:
                continue
            for observation in pair["evidence"]:
                if actor == player:
                    given.add(observation["council_id"])
                if recipient == player:
                    received.add(observation["council_id"])
        result[player] = {IDOL_FEATURES[0]: len(given) if given else None,
                          IDOL_FEATURES[1]: len(received) if received else None}
    return result
