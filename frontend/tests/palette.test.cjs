const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");
const { renderToStaticMarkup } = require("react-dom/server");
const ts = require("typescript");

const appPath = path.join(__dirname, "../app");
const css = readFileSync(path.join(appPath, "styles.css"), "utf8");
const palette = Object.fromEntries(
  [...css.matchAll(/--([\w-]+):\s*(#[\da-f]{6})/gi)].map((match) => [match[1], match[2]])
);

function contrast(first, second) {
  function luminance(hex) {
    const channels = hex.slice(1).match(/../g).map((part) => parseInt(part, 16) / 255);
    const linear = channels.map((value) => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4);
    return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722;
  }
  const values = [luminance(first), luminance(second)].sort((a, b) => b - a);
  return (values[0] + 0.05) / (values[1] + 0.05);
}

test("page, panels, controls and tribe labels meet normal-text contrast", () => {
  for (const [foreground, background] of [
    ["text", "background"], ["text", "surface"], ["text-muted", "surface"],
    ["text-muted", "track"], ["surface", "accent-gold"], ["surface", "accent-peach"],
    ["accent-gold", "surface"], ["text", "tribe-dina"],
    ["text", "tribe-savu"], ["surface", "tribe-toka"], ["text", "track"]
  ]) {
    const ratio = contrast(palette[foreground], palette[background]);
    assert.ok(ratio >= 4.5, `${foreground} on ${background}: ${ratio.toFixed(2)}:1`);
  }
});

test("probability meters remain distinguishable from their tracks", () => {
  for (const accent of ["accent-green", "accent-peach"]) {
    const ratio = contrast(palette[accent], palette.track);
    assert.ok(ratio >= 3, `${accent} meter on track: ${ratio.toFixed(2)}:1`);
  }
});

test("rendered badges follow current tribes, normalize casing and preserve unknown labels", async () => {
  const source = ts.transpileModule(readFileSync(path.join(appPath, "page.tsx"), "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 }
  }).outputText;
  const module = { exports: {} };
  const fetchPredictions = async () => ({
    ok: true,
    json: async () => ({
      metadata: {
        current_season: 51, latest_episode: 4, latest_final_n: 17, active_players: 4,
        model_name: "historical_rate_baseline", generated_at: "2026-10-19T12:00:00Z"
      },
      players: ["Dina", " SAVU ", "Toka", "Future tribe"].map((tribe, index) => ({
        castaway_id: String(index), castaway: `Player ${index}`, tribe, original_tribe: "Toka",
        tribe_status_display: "Swapped", winner_probability: 0.25, next_boot_probability: 0.25,
        explanation: []
      })),
      evaluation: {}, projected_boot_order: []
    })
  });
  new Function("require", "module", "exports", "fetch", source)(
    (name) => name === "./analytics-panel" ? { default: () => null } : require(name),
    module, module.exports, fetchPredictions
  );
  const markup = renderToStaticMarkup(await module.exports.default());
  const badges = [...markup.matchAll(/<span class="tribe" data-tribe="([^"]*)">([^<]*)<\/span>/g)];
  assert.deepEqual(badges.map((match) => match[1]), ["dina", "savu", "toka", "future tribe"]);
  assert.deepEqual(badges.map((match) => match[2]), ["Dina", " SAVU ", "Toka", "Future tribe"]);
});
