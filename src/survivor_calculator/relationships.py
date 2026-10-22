"""Evidence-backed voting relationships; scores are not alliance probabilities."""
from __future__ import annotations

from collections import Counter, defaultdict
from itertools import permutations
from typing import Mapping

from survivor_calculator.council_events import Council, season_key

SOCIAL_FEATURE_COLUMNS = (
    "social_known_pair_fraction", "social_strongest_partner", "social_support_sum",
    "social_incoming_targeting", "social_original_tribe_support_gap",
    "social_protective_opposition_received", "social_protective_opposition_outgoing",
)
EVIDENCE_SHRINKAGE = 2.0  # Fixed conservative evidence scale, not a fitted probability prior.
MIN_PARTNER_COUNCILS = 2
RECENT_COUNCILS = 3


def _split_key(value: str) -> tuple[str, ...]:
    return tuple(sorted(part.strip().casefold() for part in value.split(",") if part.strip()))


def build_relationship_snapshot(
    councils: list[Council], players: list[dict[str, object]],
) -> dict[str, object]:
    """Build a directed matrix for active players using only completed councils.

    Coordination uses first-round target distributions and shrinks sparse evidence.
    Targeting uses any actual voting round, once per council. Revotes, extra votes,
    and duplicate records cannot manufacture extra independent observations.
    """
    if not players:
        return {"schema_version": 1, "players": [], "pairs": [], "councils": []}
    state = players[0]
    signature = (season_key(state), state["episode"], state["n_boots"])
    if any((season_key(p), p["episode"], p["n_boots"]) != signature for p in players):
        raise ValueError("Relationship snapshot players must share a season and event cutoff.")
    ids = sorted(str(p["castaway_id"]) for p in players)
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate active player in relationship snapshot.")
    roster = {str(p["castaway_id"]): p for p in players}
    completed = sorted((c for c in councils if c.completed_before(state)),
                       key=lambda c: (c.episode, c.order or 0, c.id))
    pairs: dict[tuple[str, str], dict[str, object]] = {
        (i, j): {"player_id": i, "other_id": j, "shared_councils": 0,
                 "same_target_councils": 0, "coordinated_councils": 0,
                 "recent_shared_councils": 0, "recent_coordinated_councils": 0,
                 "targeting_opportunities": 0, "targeting_councils": 0,
                 "informative_agreement": 0.0, "evidence": []}
        for i, j in permutations(ids, 2)
    }
    recent_ids = {c.id for c in completed[-RECENT_COUNCILS:]}
    for council in completed:
        first = council.rounds.get(1, ())
        choices: dict[str, Counter[str]] = defaultdict(Counter)
        splits: dict[str, set[tuple[str, ...]]] = defaultdict(set)
        for ballot in first:
            choices[ballot.voter][ballot.target] += 1
            split_key = _split_key(ballot.split_vote)
            if len(split_key) >= 2:
                splits[ballot.voter].add(split_key)
        distributions = {v: {t: n / sum(counts.values()) for t, n in counts.items()}
                         for v, counts in choices.items()}
        target_mass: Counter[str] = Counter()
        for distribution in distributions.values():
            target_mass.update(distribution)
        distinguishing_weight = 1.0 - max(target_mass.values(), default=0.0) / max(1, len(distributions))
        all_ballots = [b for ballots in council.rounds.values() for b in ballots]
        voters = {b.voter for b in all_ballots}
        attacks = {(b.voter, b.target) for b in all_ballots}
        for (i, j), cell in pairs.items():
            shared = i in distributions and j in distributions
            opportunity = i in voters and j in council.participants and (j not in council.immune_targets or (i, j) in attacks)
            attacked = (i, j) in attacks
            agreement = sum(p * distributions.get(j, {}).get(t, 0.0) for t, p in distributions.get(i, {}).items()) if shared else 0.0
            split = shared and bool(splits[i] & splits[j])
            coordinated = max(agreement, 1.0 if split else 0.0)
            if shared:
                cell["shared_councils"] += 1
                cell["same_target_councils"] += int(agreement > 0)
                cell["coordinated_councils"] += int(coordinated > 0)
                cell["informative_agreement"] += coordinated * distinguishing_weight
                if council.id in recent_ids:
                    cell["recent_shared_councils"] += 1
                    cell["recent_coordinated_councils"] += int(coordinated > 0)
            cell["targeting_opportunities"] += int(opportunity)
            cell["targeting_councils"] += int(attacked)
            if shared or opportunity or attacked:
                cell["evidence"].append({"council_id": council.id, "episode": council.episode,
                                         "order": council.order, "shared_first_round": shared,
                                         "same_target_fraction": agreement, "documented_split": split,
                                         "targeted_other": attacked})
    for cell in pairs.values():
        shared = cell["shared_councils"]
        opportunities = cell["targeting_opportunities"]
        cell["coordination_strength"] = cell["informative_agreement"] / (shared + EVIDENCE_SHRINKAGE) if shared else None
        cell["targeting_rate"] = cell["targeting_councils"] / opportunities if opportunities else None
    # Use direct evidence only; inferred protective opposition is never fed back.
    for (i, j), cell in pairs.items():
        weighted_threat = support = 0.0
        ally_evidence = []
        same_tribe = bool(roster[i].get("tribe")) and roster[i].get("tribe") == roster[j].get("tribe")
        if same_tribe:
            for k in ids:
                if k in (i, j) or roster[k].get("tribe") != roster[i].get("tribe"):
                    continue
                partner = pairs[(i, k)]
                reverse = pairs[(k, i)]
                strength = (partner["coordination_strength"] or 0.0) * (1.0 -
                            max(partner["targeting_rate"] or 0.0, reverse["targeting_rate"] or 0.0))
                threat = pairs[(j, k)]
                if partner["coordinated_councils"] < MIN_PARTNER_COUNCILS or strength <= 0 or threat["targeting_rate"] is None:
                    continue
                support += strength
                weighted_threat += strength * threat["targeting_rate"]
                ally_evidence.append({"ally_id": k, "coordination_strength": strength,
                                     "opponent_targeting_rate": threat["targeting_rate"]})
        cell["protective_opposition"] = weighted_threat / support if support else None
        cell["protective_evidence"] = ally_evidence
        cell["same_current_tribe"] = same_tribe
    return {
        "schema_version": 1, "season_key": signature[0],
        "cutoff": {"episode": signature[1], "completed_exit_order": signature[2]},
        "parameters": {"evidence_shrinkage": EVIDENCE_SHRINKAGE,
                       "minimum_partner_councils": MIN_PARTNER_COUNCILS, "recent_councils": RECENT_COUNCILS},
        "limitations": ["Evidence scores are not alliance probabilities.",
                        "Protective opposition is viewer-informed; contestant knowledge is unobserved.",
                        "Unknown is distinct from an observed absence of targeting.",
                        "No advantage assistance, reward-choice evidence or coalition simulation is included yet."],
        "players": [{k: p.get(k) for k in ("castaway_id", "castaway", "tribe", "original_tribe")} for p in sorted(players, key=lambda p: str(p["castaway_id"]))],
        "councils": [{"id": c.id, "episode": c.episode, "order": c.order,
                      "warnings": list(c.warnings)} for c in completed],
        "pairs": list(pairs.values()),
    }


def social_features(snapshot: Mapping[str, object]) -> dict[str, dict[str, object]]:
    """Summarize current-tribe evidence while retaining unknown numeric values."""
    players = {p["castaway_id"]: p for p in snapshot["players"]}
    pairs = {(p["player_id"], p["other_id"]): p for p in snapshot["pairs"]}
    result = {}
    for i, player in players.items():
        peers = [j for j, p in players.items() if j != i and player.get("tribe") and p.get("tribe") == player.get("tribe")]
        known = [pairs[i, j] for j in peers if pairs[i, j]["coordination_strength"] is not None]
        strengths = [p["coordination_strength"] for p in known]
        targeting = [pairs[j, i]["targeting_rate"] for j in peers if pairs[j, i]["targeting_rate"] is not None]
        incoming = [pairs[j, i]["protective_opposition"] for j in peers if pairs[j, i]["protective_opposition"] is not None]
        outgoing = [pairs[i, j]["protective_opposition"] for j in peers if pairs[i, j]["protective_opposition"] is not None]
        originals = [j for j in peers if player.get("original_tribe") and players[j].get("original_tribe") == player.get("original_tribe")]
        original_known = [pairs[i, j] for j in originals if pairs[i, j]["coordination_strength"] is not None]
        def average(values: list[float]) -> float | None:
            return sum(values) / len(values) if values else None
        result[i] = {
            "social_known_pair_fraction": len(known) / len(peers) if peers else 0.0,
            "social_strongest_partner": max(strengths) if strengths else None,
            "social_support_sum": sum(strengths) if strengths else None,
            "social_incoming_targeting": average(targeting),
            "social_original_tribe_support_gap": 1.0 - average([p["coordination_strength"] for p in original_known]) if original_known else None,
            "social_protective_opposition_received": average(incoming),
            "social_protective_opposition_outgoing": average(outgoing),
        }
    return result
