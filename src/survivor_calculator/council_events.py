"""Normalize voting events and enforce prediction-time information boundaries."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Mapping

Record = Mapping[str, object]


def integer(value: object) -> int | None:
    """Parse the workbook/JSON numeric convention without inventing a value."""
    try:
        return int(float(str(value))) if value not in (None, "") else None
    except (ValueError, OverflowError):
        return None


def season_key(row: Record) -> str:
    """Canonical franchise-season identity, including legacy US-only fixtures."""
    version = str(row.get("version") or "")
    if not version:
        label = str(row.get("version_season") or "")
        version = label.rstrip("0123456789") or "US"
    return f"{version}:{integer(row.get('season'))}"


@dataclass(frozen=True)
class Ballot:
    voter: str
    target: str
    nullified: bool
    split_vote: str


@dataclass(frozen=True)
class Council:
    """One council; rounds and extra ballots are not independent councils."""
    id: str
    season: str
    episode: int
    order: int | None
    participants: frozenset[str]
    immune_targets: frozenset[str]
    rounds: dict[int, tuple[Ballot, ...]]
    warnings: tuple[str, ...]

    day: int | None = None
    eliminated_ids: frozenset[str] = frozenset()

    def completed_before(self, state: Record) -> bool:
        """Allow same-episode earlier councils only with an explicit exit order."""
        if self.season != season_key(state):
            return False
        episode = integer(state.get("episode")) or 0
        if self.episode > episode:
            return False
        if self.order is not None:
            return self.order <= (integer(state.get("completed_exit_order", state.get("n_boots"))) or 0)
        return self.episode < episode


def normalize_councils(rows: list[dict[str, str | None]]) -> list[Council]:
    """Group by season/exit/stage/day, preserving joint councils and voting rounds.

    Rows with no exit order use an episode/tribe fallback and can only enter
    later episodes. Exact ordinary duplicates are removed and reported; extra
    or stolen ballots remain, with at most one council of relationship evidence.
    """
    groups: dict[tuple[str, int, int, int, int, str], list[dict[str, str | None]]] = defaultdict(list)
    for row in rows:
        episode = integer(row.get("episode"))
        if episode is None or integer(row.get("season")) is None:
            raise ValueError("Vote History requires a valid season and episode on every row.")
        order = integer(row.get("order"))
        key = (season_key(row), order or 0, episode, integer(row.get("day")) or 0,
               integer(row.get("sog_id")) or 0, str(row.get("tribe") or "") if order is None else "")
        groups[key].append(row)
    councils = []
    for key, records in sorted(groups.items()):
        warnings: set[str] = set()
        if key[1] == 0:
            warnings.add("No exit order; only prior-episode use is supported.")
        seen: set[tuple[tuple[str, str], ...]] = set()
        rounds: dict[int, list[Ballot]] = defaultdict(list)
        participants: set[str] = set()
        immune: set[str] = set()
        for row in records:
            voter, target = str(row.get("castaway_id") or ""), str(row.get("vote_id") or "")
            if voter:
                participants.add(voter)
                if str(row.get("immunity") or "").lower() in {"individual", "individual immunity"}:
                    immune.add(voter)
            signature = tuple(sorted((k, str(v or "")) for k, v in row.items()))
            event = str(row.get("vote_event") or "").lower()
            extra = any(token in event for token in ("extra vote", "steal", "banked vote", "control the vote"))
            if signature in seen and not extra:
                warnings.add("Exact duplicate ordinary record removed.")
                continue
            seen.add(signature)
            if extra:
                warnings.add("Additional/controlled ballots normalized per voter for relationship evidence.")
            if not voter or not target or target == voter:
                continue
            if any(token in event for token in ("fire challenge", "rock draw", "countback", "deadlock")):
                continue
            participants.add(target)
            rounds[integer(row.get("vote_order")) or 1].append(Ballot(
                voter, target, str(row.get("nullified") or "").lower() in {"1", "true"},
                str(row.get("split_vote") or ""),
            ))
        councils.append(Council(
            "|".join(map(str, key)), key[0], key[2], key[1] or None,
            frozenset(participants), frozenset(immune),
            {number: tuple(sorted(ballots, key=lambda b: (b.voter, b.target, b.nullified, b.split_vote)))
             for number, ballots in sorted(rounds.items())}, tuple(sorted(warnings)),
            key[3] or None, frozenset(str(r["voted_out_id"]) for r in records if r.get("voted_out_id")),
        ))
    return councils
