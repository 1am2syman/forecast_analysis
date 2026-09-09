import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(
  new URL("../dashboard/app.js", import.meta.url),
  "utf8",
);
const names = [
  "accuracyVintageSeries",
  "accuracyVintageColor",
  "accuracyVintageSeriesColor",
  "accuracyVintageLegend",
  "overviewVolumeVintageSeries",
  "overviewVolumeLegend",
  "overviewApplicableMonths",
  "overviewPrimaryRows",
  "chartExtent",
  "smoothLinePath",
  "overviewPerformanceChart",
  "overviewVolumeChart",
  "overviewVolumeExtent",
];
const bodies = names
  .map((name) => {
    const start = source.indexOf(`  function ${name}(`);
    assert(start >= 0, `missing ${name}`);
    return source.slice(start, source.indexOf("\n  }", start) + 4);
  })
  .join("\n");
const context = vm.createContext({
  ACCURACY_VINTAGE_COLORS: ["#a", "#b", "#c", "#d"],
  OVERVIEW_VOLUME_Y_MIN_KL: 1600,
  OVERVIEW_VOLUME_Y_MAX_KL: 4500,
  finite: Number.isFinite,
  count: String,
  kl: String,
  number: String,
  signedKl: String,
  monthLabel: String,
  metricValue: String,
  escapeHtml: (value) => String(value).replaceAll('"', "&quot;"),
  emptyVisual: (value) => value,
});
vm.runInContext(`${bodies}\nthis.api={${names.join(",")}}`, context);
const api = context.api;
const plain = (value) => JSON.parse(JSON.stringify(value));
const row = (month, bias, forecast, eligible = 2) => ({
  snop_month: month,
  bias_pct: bias,
  forecast_kl: forecast,
  forecast_accuracy_pct: 80 + bias,
  actual_denominator_kl: 2000,
  eligible_parents: eligible,
});
function fixture(ids) {
  const options = ["m5", "m4", "m3", "m2"].map((id, i) => ({
    id,
    label: id,
    selected: ids.includes(id),
    rows: [
      row("2025-01", i + 1, 2000 + i),
      row("2025-02", -i - 2, 2100 + i),
      row("2025-03", null, null, 0),
    ],
  }));
  const latest = {
    id: "latest",
    label: "Latest M1",
    rows: [
      row("2025-01", 9, 2200),
      row("2025-02", -8, 2300),
      row("2025-03", null, null, 0),
    ],
  };
  const primary = options.find((s) => s.selected) || latest;
  return {
    accuracy_vintages: {
      options,
      latest,
      overview: { primary: { id: primary.id, label: primary.label } },
    },
  };
}
const monthly = ["2025-01", "2025-02", "2025-03"].map((snop_month, i) => ({
  snop_month,
  source: "ml",
  bias_pct: 71 + i,
}));
const biasValues = (html) =>
  [...html.matchAll(/data-tooltip-bias-raw="([^"]*)"/g)].map((m) =>
    Number(m[1]),
  );
const forecastIds = (html) =>
  [
    ...html.matchAll(/data-volume-role="forecast" data-vintage-id="([^"]*)"/g),
  ].map((m) => m[1]);

for (const ids of [
  ["m5"],
  ["m3"],
  ["m2"],
  ["m5", "m4", "m3"],
  ["m5", "m4", "m3", "m2"],
  ["m4", "m3"],
  [],
]) {
  test(`Overview bias/lines/cohort for ${ids.join(",") || "latest-only"}`, () => {
    const payload = fixture(ids),
      vintagePayload = payload.accuracy_vintages;
    const options = {
      vintagePayload,
      primaryBias: true,
      hideUnavailableMonths: true,
    };
    const expectedRows = api
      .overviewPrimaryRows(payload)
      .filter((r) => r.eligible_parents > 0);
    const accuracy = api.overviewPerformanceChart(monthly, options);
    assert.deepEqual(
      biasValues(accuracy),
      plain(expectedRows.map((r) => r.bias_pct)),
    );
    assert(!accuracy.includes("Latest forecast bias"));
    assert(accuracy.includes(`${vintagePayload.overview.primary.label} bias`));
    const volume = api.overviewVolumeChart(monthly, options);
    assert.deepEqual(forecastIds(volume), [...ids, "latest"]);
    assert.deepEqual(
      plain(api.overviewVolumeVintageSeries(payload).map((s) => s.id)),
      [...ids, "latest"],
    );
    assert.equal((volume.match(/data-volume-role="actual"/g) || []).length, 1);
    assert.equal((volume.match(/class="chart__month-hit /g) || []).length, 2);
    const values = [...volume.matchAll(/data-volume-values="([^"]*)"/g)].map(
      (m) => JSON.parse(m[1]),
    );
    assert.deepEqual(values, [
      ...plain(
        api
          .overviewVolumeVintageSeries(payload)
          .map((s) =>
            s.rows
              .filter((r) => r.eligible_parents > 0)
              .map((r) => r.forecast_kl),
          ),
      ),
      [2000, 2000],
    ]);
    const fullscreen = api.overviewPerformanceChart(monthly, {
      ...options,
      height: 720,
    });
    assert.deepEqual(biasValues(fullscreen), biasValues(accuracy));
  });
}
test("Trends default keeps monthly-performance bias rather than opting into Overview policy", () => {
  assert.deepEqual(
    biasValues(
      api.overviewPerformanceChart(monthly, {
        vintagePayload: fixture(["m4"]).accuracy_vintages,
      }),
    ),
    [71, 72, 73],
  );
  const trend = source.slice(
    source.indexOf("  function renderTrendMonthlyChart("),
    source.indexOf("  function renderTrends("),
  );
  assert(!trend.includes("primaryBias: true"));
  const main = source.slice(
    source.indexOf("  function renderOverviewCharts("),
    source.indexOf("  function scheduleOverviewChartRender("),
  );
  assert(main.includes("primaryBias: true"));
  const fullscreen = source.slice(
    source.indexOf("  const chartDialogContent ="),
    source.indexOf(
      "    volume:",
      source.indexOf("  const chartDialogContent ="),
    ),
  );
  assert(fullscreen.includes("primaryBias: true"));
});
test("Missing primary bias does not silently fall back to monthly or latest bias", () => {
  const payload = fixture(["m4"]);
  delete payload.accuracy_vintages.options[1].rows[0].bias_pct;
  const html = api.overviewPerformanceChart(monthly, {
    vintagePayload: payload.accuracy_vintages,
    primaryBias: true,
    hideUnavailableMonths: true,
  });
  assert(html.includes('data-tooltip-bias-raw="undefined"'));
  assert(!html.includes('data-tooltip-bias-raw="71"'));
});
test("Vintage colors are stable through deselection and agree between chart legends", () => {
  const multi = fixture(["m5", "m4", "m3"]),
    single = fixture(["m3"]);
  const series = multi.accuracy_vintages.options[2];
  assert.equal(
    api.accuracyVintageSeriesColor(series, multi.accuracy_vintages),
    api.accuracyVintageSeriesColor(series, single.accuracy_vintages),
  );
  assert.equal(
    api.accuracyVintageSeriesColor(series, single.accuracy_vintages),
    "#c",
  );
  for (const payload of [multi, single, fixture([])]) {
    const colors = (html) =>
      [...html.matchAll(/style="background:([^"]+)"/g)].map((m) => m[1]);
    assert.deepEqual(
      colors(api.overviewVolumeLegend(payload)),
      colors(api.accuracyVintageLegend(payload)),
    );
  }
});
