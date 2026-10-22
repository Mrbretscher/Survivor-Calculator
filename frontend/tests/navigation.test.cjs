const assert = require("node:assert/strict");
const { test } = require("node:test");
const { jsx } = require("react/jsx-runtime");
const { renderToStaticMarkup } = require("react-dom/server");
const createLoader = require("./load-ts.cjs");

const predictions = {
  metadata: {
    current_season: 51, latest_episode: 5, latest_final_n: 16,
    active_players: 0, model_name: "historical_rate_baseline",
    generated_at: "2026-10-21T12:00:00Z", disclaimer: "For fun.",
    model_selection_policy: "Keep the baseline until evidence supports a change."
  },
  players: [],
  projected_boot_order: [],
  evaluation: {
    status: "ok",
    split: { strategy: "chronological", training_seasons: [1, 45], holdout_seasons: [46, 50] },
    metrics: {
      event_count: 50, candidate_count: 400,
      ranking: { top1_accuracy: 0.12, top3_recall: 0.35 },
      probability: { brier_score: 0.076, log_loss: 2.375 }
    },
    baseline_comparisons: [{ name: "uniform", events: 50, top1_accuracy: 0.1, top3_recall: 0.3, brier_score: 0.077, log_loss: 2.38 }],
    calibration: { bins: [{ range: "0–10%", count: 20, mean_predicted_probability: 0.05, observed_boot_rate: 0.06, absolute_error: 0.01 }] },
    notes: ["Historical inspection limits generalization."]
  }
};

test("navigation links open separate routes and identify the current section", () => {
  for (const [pathname, activeHref, current] of [
    ["/", "/", "page"],
    ["/timeline", "/timeline", "page"],
    ["/analytics", "/analytics", "page"],
    ["/methodology", "/methodology", "page"],
    ["/contestants/US0759", "/", "location"]
  ]) {
    const Navigation = createLoader({ pathname })("../app/site-navigation.tsx").default;
    const markup = renderToStaticMarkup(jsx(Navigation, {}));
    assert.match(markup, /<nav[^>]*aria-label="Main navigation"/);
    for (const [href, label] of [["/", "Predictions"], ["/timeline", "Timeline"], ["/analytics", "Analytics"], ["/methodology", "Methodology"]]) {
      assert.ok(markup.includes(`href="${href}"${href === activeHref ? ` aria-current="${current}"` : ""}>${label}</a>`));
    }
    assert.equal((markup.match(/aria-current=/g) || []).length, 1);
  }
});

test("predictions page contains the board without analytics or evaluation", async () => {
  const calls = [];
  const Home = createLoader({ fetch: async (url) => {
    calls.push(url);
    return { ok: true, json: async () => predictions };
  } })("../app/page.tsx").default;
  const markup = renderToStaticMarkup(await Home());
  assert.match(markup, /id="current-board"/);
  assert.match(markup, /Projected boot order/);
  assert.doesNotMatch(markup, /evaluation-title|analytics-title|Methodology Notes|timeline-title|<select/);
  assert.equal(calls.length, 1);
  assert.ok(calls[0].endsWith("/api/predictions/current"));
});

test("methodology route preserves split, metrics, comparisons, calibration, and notes", async () => {
  const Page = createLoader({ fetch: async () => ({ ok: true, json: async () => predictions }) })("../app/methodology/page.tsx").default;
  const markup = renderToStaticMarkup(await Page());
  for (const text of ["Model methodology", "Chronological", "1-45", "46-50", "12%", "35%", "0.076", "2.375", "Uniform", "0–10%", "Historical inspection limits generalization."]) {
    assert.ok(markup.includes(text), text);
  }
  assert.doesNotMatch(markup, /id="current-board"|analytics-title/);
});

test("methodology handles missing predictions and skipped evaluation", async () => {
  for (const [payload, expected] of [
    [null, "Evaluation temporarily unavailable"],
    [{ ...predictions, evaluation: { status: "skipped", reason: "Not enough completed seasons." } }, "Not enough completed seasons."]
  ]) {
    const Page = createLoader({ fetch: async () => ({ ok: !!payload, json: async () => payload }) })("../app/methodology/page.tsx").default;
    assert.ok(renderToStaticMarkup(await Page()).includes(expected));
  }
});

test("analytics route renders independently of the predictions API", () => {
  const Page = createLoader({ fetch: () => { throw new Error("Predictions must not be fetched here"); } })("../app/analytics/page.tsx").default;
  const markup = renderToStaticMarkup(jsx(Page, {}));
  assert.match(markup, /Survivor analytics/);
  assert.match(markup, /id="analytics-title"/);
  assert.doesNotMatch(markup, /Prediction API unavailable|evaluation-title|id="current-board"/);
});

const timelineIndex = {
  metadata: predictions.metadata,
  note: "Reconstructed with the current model.",
  states: [{ season: 51, episode: 5, checkpoint: 5, final_n: 16, active_players: 0 }],
  episodes: [{ season: 51, episode: 5, available: true }]
};

test("Timeline route loads the index separately and renders its episode controls", async () => {
  const calls = [];
  const load = createLoader({ fetch: async (url) => {
    calls.push(url);
    return { ok: true, json: async () => url.endsWith("/timeline") ? timelineIndex : predictions };
  } });
  const route = load("../app/timeline/page.tsx");
  const markup = renderToStaticMarkup(await route.default());
  assert.equal(route.metadata.title, "Timeline | Survivor Calculator");
  assert.match(markup, /id="timeline-title"/);
  assert.equal((markup.match(/<select/g) || []).length, 3);
  assert.ok(calls.some((url) => url.endsWith("/api/predictions/current")));
  assert.ok(calls.some((url) => url.endsWith("/api/predictions/timeline")));
});

test("Timeline route handles missing predictions without rendering selection controls", async () => {
  const Page = createLoader({ fetch: async () => ({ ok: false }) })("../app/timeline/page.tsx").default;
  const markup = renderToStaticMarkup(await Page());
  assert.match(markup, /Timeline temporarily unavailable/);
  assert.match(markup, /href="\/"/);
  assert.doesNotMatch(markup, /<select|id="current-board"/);
});

test("Timeline route preserves current predictions when the index is missing or from another snapshot", async () => {
  for (const index of [null, { ...timelineIndex, metadata: { ...predictions.metadata, generated_at: "older" } }]) {
    const Page = createLoader({ fetch: async (url) => ({
      ok: url.endsWith("/current") || !!index,
      json: async () => url.endsWith("/current") ? predictions : index
    }) })("../app/timeline/page.tsx").default;
    const markup = renderToStaticMarkup(await Page());
    assert.match(markup, /Timeline is temporarily unavailable/);
    assert.match(markup, /id="current-board"/);
    assert.doesNotMatch(markup, /<select/);
  }
});
