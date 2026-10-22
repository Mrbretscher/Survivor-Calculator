const assert = require("node:assert/strict");
const { test } = require("node:test");
const { jsx } = require("react/jsx-runtime");
const { renderToStaticMarkup } = require("react-dom/server");
const createLoader = require("./load-ts.cjs");

const player = {
  castaway_id: "A", castaway: "Ari", tribe: "Tiva", original_tribe: "Tiva",
  tribe_status: "Tribal", tribe_status_display: "Original", occupation: "Teacher",
  soc_code: "", soc_title: "", soc_major_group: "", raw_next_boot_risk: 0.5,
  next_boot_probability: 1, winner_probability: 1, explanation: []
};
const current = {
  metadata: { current_season: 7, latest_episode: 3, latest_final_n: 1, active_players: 1,
    generated_at: "2026-10-21T12:00:00Z", model_name: "historical_rate_baseline",
    model_selection_policy: "baseline", source_workbook: "fixture", disclaimer: "For fun.",
    training_seasons: [1], training_policy: "evaluation_training_split" },
  players: [player], projected_boot_order: [{ projected_order: 1, projected_final_n_before_boot: 1,
    castaway_id: "A", castaway: "Ari", projected_boot_probability: 1 }], evaluation: {}
};
const states = [
  { season: 6, episode: 1, checkpoint: 0, active_players: 1, final_n: 1 },
  { season: 7, episode: 1, checkpoint: 0, active_players: 1, final_n: 1 },
  { season: 7, episode: 3, checkpoint: 0, active_players: 1, final_n: 1 },
  { season: 7, episode: 3, checkpoint: 1, active_players: 1, final_n: 1 }
];
const timeline = { metadata: current.metadata, note: "Reconstructed", states,
  episodes: [...states.map((state) => ({ season: state.season, episode: state.episode, available: true })),
    { season: 7, episode: 2, available: false }] };
const detail = (state) => ({ ...current, metadata: { ...current.metadata,
  current_season: state.season, latest_episode: state.episode }, timeline_context: state });

function elements(node, type) {
  if (!node || typeof node !== "object") return [];
  if (Array.isArray(node)) return node.flatMap((child) => elements(child, type));
  return [...(node.type === type ? [node] : []), ...elements(node.props?.children, type)];
}

function harness(fetch) {
  const slots = [];
  let cursor = 0;
  const hooks = {
    useState(initial) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = initial;
      return [slots[index], (value) => { slots[index] = value; }];
    },
    useRef(initial) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = { current: initial };
      return slots[index];
    }
  };
  const Explorer = createLoader({ fetch, hooks })("../app/prediction-explorer.tsx").default;
  return () => { cursor = 0; return Explorer({ current, timeline }); };
}

test("Timeline renders season, episode and checkpoint controls and an unavailable fallback", () => {
  const Explorer = createLoader()("../app/prediction-explorer.tsx").default;
  const markup = renderToStaticMarkup(jsx(Explorer, { current, timeline }));
  assert.match(markup, /Timeline/);
  assert.match(markup, /Season 6 · Held out/);
  assert.match(markup, /Select season/);
  assert.match(markup, /Select episode/);
  assert.match(markup, /Select episode first/);
  assert.doesNotMatch(markup, /id="dashboard-title"|class="playerCard"|Projected boot order/);
  assert.match(markup, /reconstructed/);
  assert.match(markup, /trained through season 1/);
  assert.equal((markup.match(/<select/g) || []).length, 3);
  const fallback = renderToStaticMarkup(jsx(Explorer, { current, timeline: null }));
  assert.match(fallback, /Timeline is temporarily unavailable/);
  assert.doesNotMatch(fallback, /prediction dashboard|class="playerCard"/);
});

test("historical boards keep probabilities and omit current contestant profile links", () => {
  const Board = createLoader()("../app/player-board.tsx").default;
  const markup = renderToStaticMarkup(jsx(Board, { players: current.players, bootOrder: current.projected_boot_order, historical: true }));
  assert.match(markup, /Timeline board/);
  assert.match(markup, /Ari/);
  assert.match(markup, /100%/);
  assert.doesNotMatch(markup, /href="\/contestants\//);
});

test("detail loading uses the exact checkpoint and rejects updates, errors or mismatched states", async () => {
  const state = states[0];
  const responses = [
    { ok: false },
    { ok: true, json: async () => ({ ...detail(state), metadata: { generated_at: "changed" } }) },
    { ok: true, json: async () => detail(states[1]) },
    { ok: true, json: async () => detail(state) }
  ];
  const urls = [];
  const { getTimelinePrediction } = createLoader({ fetch: async (url, options) => {
    urls.push(url); assert.equal(options.cache, "no-store"); return responses.shift();
  } })("../lib/predictions.ts");
  await assert.rejects(getTimelinePrediction(state, current.metadata.generated_at), /unavailable/);
  await assert.rejects(getTimelinePrediction(state, current.metadata.generated_at), /updated/);
  await assert.rejects(getTimelinePrediction(state, current.metadata.generated_at), /selected checkpoint/);
  assert.deepEqual(await getTimelinePrediction(state, current.metadata.generated_at), detail(state));
  assert.ok(urls.every((url) => url.endsWith("/api/predictions/timeline/6/1/0")));
});

test("selection clears the old board while loading and ignores a late older response", async () => {
  const pending = [];
  const render = harness(() => new Promise((resolve) => pending.push(resolve)));
  elements(render(), "select")[0].props.onChange({ target: { value: "6" } });
  elements(render(), "select")[1].props.onChange({ target: { value: "1" } });
  let tree = render();
  assert.equal(elements(tree, "header").length, 0);
  assert.equal(elements(tree, "p").find((item) => item.props.role === "status").props.children, "Loading checkpoint…");
  elements(tree, "select")[0].props.onChange({ target: { value: "7" } });
  assert.equal(elements(render(), "select")[1].props.value, "");
  assert.equal(elements(render(), "header").length, 0);
  elements(render(), "select")[1].props.onChange({ target: { value: "1" } });
  pending[1]({ ok: true, json: async () => detail(states[1]) });
  await new Promise(setImmediate);
  pending[0]({ ok: true, json: async () => detail(states[0]) });
  await new Promise(setImmediate);
  tree = render();
  assert.equal(elements(tree, "h1")[0].props.children[1], 7);
  elements(tree, "button").find((item) => item.props.children === "Back to current prediction").props.onClick();
  tree = render();
  assert.equal(elements(tree, "h1")[0].props.children[1], 7);
  assert.equal(elements(tree, "select")[1].props.value, 3);
});

test("a failed checkpoint shows a retry action without showing stale predictions", async () => {
  const render = harness(async () => { throw new Error("Network unavailable"); });
  elements(render(), "select")[0].props.onChange({ target: { value: "6" } });
  elements(render(), "select")[1].props.onChange({ target: { value: "1" } });
  await new Promise(setImmediate);
  const tree = render();
  assert.equal(elements(tree, "header").length, 0);
  assert.ok(elements(tree, "div").some((item) => item.props.role === "alert"));
  assert.ok(elements(tree, "button").some((item) => item.props.children === "Try again"));
});

test("episodes without a forecast stay selectable with an explicit unavailable explanation", () => {
  const render = harness(() => { throw new Error("Unavailable episodes must not request a forecast"); });
  elements(render(), "select")[0].props.onChange({ target: { value: "7" } });
  elements(render(), "select")[1].props.onChange({ target: { value: "2" } });
  const tree = render();
  assert.ok(elements(tree, "h2").some((item) => item.props.children === "Prediction unavailable"));
  assert.equal(elements(tree, "header").length, 0);
  assert.equal(elements(tree, "select")[2].props.disabled, true);
  assert.ok(elements(tree, "button").some((item) => item.props.children === "View checkpoint" && item.props.disabled));
  elements(tree, "button").find((item) => item.props.children === "Back to current prediction").props.onClick();
  assert.equal(elements(render(), "h1")[0].props.children[1], 7);
});


test("Timeline waits for both a season and episode before requesting a forecast", async () => {
  const calls = [];
  const render = harness(async (url) => {
    calls.push(url);
    return { ok: true, json: async () => detail(states[0]) };
  });
  let tree = render();
  const selects = elements(tree, "select");
  assert.equal(selects[0].props.value, "");
  assert.equal(selects[1].props.value, "");
  assert.equal(selects[1].props.disabled, true);
  assert.equal(selects[2].props.disabled, true);
  assert.equal(elements(tree, "header").length, 0);
  assert.equal(calls.length, 0);
  selects[0].props.onChange({ target: { value: "6" } });
  tree = render();
  assert.equal(elements(tree, "select")[1].props.disabled, false);
  assert.equal(elements(tree, "select")[1].props.value, "");
  assert.equal(elements(tree, "header").length, 0);
  assert.equal(calls.length, 0);
  elements(tree, "select")[1].props.onChange({ target: { value: "1" } });
  await new Promise(setImmediate);
  assert.equal(calls.length, 1);
  assert.ok(calls[0].endsWith("/api/predictions/timeline/6/1/0"));
  assert.equal(elements(render(), "h1")[0].props.children[1], 6);
});

test("changing season clears a loaded forecast and waits for a new episode", async () => {
  let calls = 0;
  const render = harness(async () => {
    calls += 1;
    return { ok: true, json: async () => detail(states[0]) };
  });
  elements(render(), "select")[0].props.onChange({ target: { value: "6" } });
  elements(render(), "select")[1].props.onChange({ target: { value: "1" } });
  await new Promise(setImmediate);
  assert.equal(elements(render(), "header").length, 1);
  elements(render(), "select")[0].props.onChange({ target: { value: "7" } });
  const tree = render();
  assert.equal(elements(tree, "header").length, 0);
  assert.equal(elements(tree, "select")[1].props.value, "");
  assert.equal(elements(tree, "select")[2].props.disabled, true);
  assert.equal(calls, 1);
});

test("current-only Predictions still renders its latest board immediately", () => {
  const Explorer = createLoader()("../app/prediction-explorer.tsx").default;
  const markup = renderToStaticMarkup(jsx(Explorer, { current, timeline: null, showTimeline: false }));
  assert.match(markup, /Season 7 prediction dashboard/);
  assert.match(markup, /class="playerCard"/);
  assert.doesNotMatch(markup, /id="timeline-title"|<select/);
});
