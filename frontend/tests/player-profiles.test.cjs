const assert = require("node:assert/strict");
const { test } = require("node:test");
const { jsx } = require("react/jsx-runtime");
const { renderToStaticMarkup } = require("react-dom/server");
const createLoader = require("./load-ts.cjs");

const player = (id, tribe, risk = 0.2) => ({
  castaway_id: id,
  castaway: id === "US0759" ? "Cristian" : `Player ${id}`,
  tribe,
  original_tribe: "Savu",
  tribe_status: "Swapped",
  tribe_status_display: "Swapped",
  occupation: "Farmer",
  soc_code: "",
  soc_title: "",
  soc_major_group: "",
  raw_next_boot_risk: risk,
  next_boot_probability: risk,
  winner_probability: 0.25,
  explanation: ["Recorded model signal."]
});

const players = [
  player("US0759", "Dina", 0.3),
  player("B", "Toka", 0.2),
  player("C", "Dina", 0.3),
  player("D", "Savu", 0.2)
];
const predictions = {
  metadata: {
    current_season: 51,
    latest_episode: 5,
    latest_final_n: 16,
    active_players: 4,
    generated_at: "2026-10-19T12:00:00Z",
    model_name: "baseline",
    disclaimer: "For fun."
  },
  players,
  projected_boot_order: players.map((row, index) => ({
    castaway_id: row.castaway_id,
    castaway: row.castaway,
    projected_order: index + 1,
    projected_final_n_before_boot: 4 - index,
    projected_boot_probability: row.next_boot_probability
  })),
  evaluation: {}
};

test("tribe grouping uses current tribes, preserves order and handles new or empty tribes", () => {
  const { groupByTribe, bootRowsWithTribes } = createLoader()(
    "../lib/predictions.ts"
  );
  const rows = bootRowsWithTribes(players, predictions.projected_boot_order);
  assert.deepEqual(
    groupByTribe(rows).map((group) => [
      group.tribe,
      group.rows.map((row) => row.castaway_id)
    ]),
    [
      ["Dina", ["US0759", "C"]],
      ["Savu", ["D"]],
      ["Toka", ["B"]]
    ]
  );
  assert.equal(rows[0].projected_boot_probability, 0.3);
  assert.deepEqual(
    groupByTribe([
      { tribe: " Merge " },
      { tribe: "merge" },
      { tribe: " " }
    ]).map((group) => group.rows.length),
    [2, 1]
  );
  assert.deepEqual(groupByTribe([]), []);
  assert.equal(
    bootRowsWithTribes([], predictions.projected_boot_order)[0].tribe,
    "Unknown tribe"
  );
});

test("tribe and combined views render distinct boards with contestant links", () => {
  for (const view of ["tribe", "all"]) {
    const Board = createLoader({ view })("../app/player-board.tsx").default;
    const markup = renderToStaticMarkup(
      jsx(Board, { players, bootOrder: predictions.projected_boot_order })
    );
    assert.match(
      markup,
      new RegExp(
        `aria-pressed="true"[^>]*>${view === "tribe" ? "By tribe" : "All players"}`
      )
    );
    assert.match(markup, /href="\/contestants\/US0759"/);
    assert.equal((markup.match(/class="playerCard"/g) || []).length, 4);
    assert.equal(
      (markup.match(/class="tableFrame"/g) || []).length,
      view === "tribe" ? 3 : 1
    );
    assert.match(markup, /30%/);
    if (view === "tribe") assert.match(markup, /Overall order/);
  }
});

test("portrait lookup is scoped to both season and exact castaway ID", () => {
  const { getContestantPortrait } = createLoader()(
    "../lib/contestant-portraits.ts"
  );
  assert.equal(getContestantPortrait(51, "US0759").fullName, "Cristian Chavez");
  assert.match(
    getContestantPortrait(51, "US0759").url,
    /image-97-1024x683.jpeg$/
  );
  assert.equal(getContestantPortrait(52, "US0759"), null);
  assert.equal(getContestantPortrait(51, "Cristian"), null);
  assert.equal(getContestantPortrait(51, "toString"), null);
});

test("missing portraits render accessible initials without a broken image", () => {
  const Portrait = createLoader()(
    "../app/contestants/[castawayId]/portrait.tsx"
  ).default;
  const markup = renderToStaticMarkup(
    jsx(Portrait, { name: "New Contestant" })
  );
  assert.match(markup, /Portrait unavailable for New Contestant/);
  assert.match(markup, />NC</);
  assert.doesNotMatch(markup, /<img/);
});

test("stats distinguish zeros from missing values and forecast ranks preserve ties", () => {
  const { formatCount, recordedRate, forecastPosition } = createLoader()(
    "../lib/player-profile.ts"
  );
  assert.equal(formatCount(0), "0");
  assert.equal(formatCount(null), "Not available");
  assert.equal(recordedRate(0, 2), 0);
  assert.equal(recordedRate(0, 0), null);
  assert.equal(recordedRate(null, 2), null);
  assert.equal(recordedRate(3, 2), null);
  assert.equal(recordedRate(NaN, 2), null);
  assert.equal(
    forecastPosition(players, players[0], "next_boot_probability"),
    1
  );
  assert.equal(
    forecastPosition(players, players[2], "next_boot_probability"),
    1
  );
  assert.equal(
    forecastPosition(players, players[1], "next_boot_probability"),
    3
  );
});

const stats = {
  age: 26,
  challenge_appearances_total: 4,
  challenge_wins_total: 2,
  team_challenge_appearances_total: 4,
  team_challenge_wins_total: 2,
  individual_immunity_appearances_total: 0,
  individual_immunity_wins_total: 0,
  votes_received_total: 0,
  votes_cast_total: 2,
  confessionals_total: 8,
  confessional_time_total: 90
};

function profileLoader({ failedStats = false, oldSnapshot = false } = {}) {
  return createLoader({
    fetch: async (url) => ({
      ok: !failedStats || url.endsWith("/api/predictions/current"),
      json: async () =>
        url.endsWith("/api/predictions/current")
          ? predictions
          : {
              metadata: {
                ...predictions.metadata,
                generated_at: oldSnapshot
                  ? "2026-01-01T00:00:00Z"
                  : predictions.metadata.generated_at
              },
              player: players[0],
              stats_status: "available",
              stats,
              notes: []
            }
    })
  });
}

test("profile renders the official photo, observations and forecast", async () => {
  const Profile = profileLoader()(
    "../app/contestants/[castawayId]/page.tsx"
  ).default;
  const markup = renderToStaticMarkup(
    await Profile({ params: Promise.resolve({ castawayId: "US0759" }) })
  );
  assert.match(markup, /Cristian Chavez/);
  assert.match(markup, /Official cast portrait of Cristian Chavez/);
  assert.match(markup, /image-97-1024x683.jpeg/);
  assert.match(markup, /50%/);
  assert.match(markup, /Counted votes received/);
  assert.match(markup, /Official cast announcement/);
  assert.match(markup, /2026/);
});

test("stats API failures and snapshot mismatches retain the profile with explicit missing stats", async () => {
  for (const options of [{ failedStats: true }, { oldSnapshot: true }]) {
    const Profile = profileLoader(options)(
      "../app/contestants/[castawayId]/page.tsx"
    ).default;
    const markup = renderToStaticMarkup(
      await Profile({ params: Promise.resolve({ castawayId: "US0759" }) })
    );
    assert.match(markup, /Performance statistics are temporarily unavailable/);
    assert.match(markup, /Cristian Chavez/);
    assert.match(markup, /Not available/);
    assert.doesNotMatch(markup, /50%/);
  }
});

test("unknown profiles use the not-found route", async () => {
  const Profile = profileLoader()(
    "../app/contestants/[castawayId]/page.tsx"
  ).default;
  await assert.rejects(
    Profile({ params: Promise.resolve({ castawayId: "missing" }) }),
    /NEXT_NOT_FOUND/
  );
});
