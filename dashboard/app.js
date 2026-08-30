/* Forecast performance · canonical real-data browser adapter */
(() => {
  const appBody = document.querySelector(".body");
  const rail = document.querySelector('[role="tablist"][aria-orientation]');
  const railToggle = document.querySelector('[data-action="rail"]');
  const tabs = Array.from(rail.querySelectorAll(':scope [role="tab"]'));
  const panes = Array.from(
    document.querySelectorAll('.stage > [role="tabpanel"]'),
  );
  const validTabs = new Set(tabs.map((tab) => tab.dataset.target));
  const scopeButton = document.querySelector('[data-action="scope"]');
  const scopeDrawer = document.querySelector("#scope-drawer");
  const controls = new Map(
    Array.from(document.querySelectorAll("[data-control]")).map((control) => [
      control.dataset.control,
      control,
    ]),
  );
  const toast = document.querySelector(".toast");
  const loading = document.querySelector(".loading");
  const stage = document.querySelector(".stage");
  let toastTimer;
  let refreshTimer;
  let requestSerial = 0;
  let defaults = null;
  let currentPayload = null;
  let currentRequest = null;

  const apiUrl = (path) => new URL(path.replace(/^\//, ""), document.baseURI);
  const escapeHtml = (value) =>
    String(value ?? "—")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  const finite = (value) => typeof value === "number" && Number.isFinite(value);
  const number = (value, digits = 0) =>
    finite(value)
      ? new Intl.NumberFormat("en-US", {
          minimumFractionDigits: digits,
          maximumFractionDigits: digits,
        }).format(value)
      : "—";
  const count = (value) => number(value, 0);
  const pct = (value, digits = 1) =>
    finite(value) ? `${number(value, digits)}%` : "—";
  const pp = (value, digits = 1) =>
    finite(value) ? `${value > 0 ? "+" : ""}${number(value, digits)} pp` : "—";
  const kl = (value, digits = 1) =>
    finite(value) ? `${number(value, digits)} KL` : "—";
  const signedKl = (value, digits = 1) =>
    finite(value) ? `${value > 0 ? "+" : ""}${number(value, digits)} KL` : "—";
  const monthLabel = (value, short = true) => {
    if (!value) return "—";
    const date = new Date(`${value}T00:00:00Z`);
    return new Intl.DateTimeFormat("en-US", {
      month: short ? "short" : "long",
      year: "numeric",
      timeZone: "UTC",
    }).format(date);
  };
  const dateLabel = (value) => {
    if (!value) return "—";
    const date = new Date(`${value}T00:00:00Z`);
    return new Intl.DateTimeFormat("en-US", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      timeZone: "UTC",
    }).format(date);
  };
  const labelize = (value) =>
    String(value ?? "—")
      .replaceAll("_", " ")
      .replace(/\b\w/g, (letter) => letter.toUpperCase());
  const sourceBadge = (source) =>
    `<i class="source source--${escapeHtml(source)}">${escapeHtml(String(source).toUpperCase())}</i>`;
  const rowMap = (rows, key) =>
    new Map((rows || []).map((row) => [row[key], row]));

  function setHtml(element, markup) {
    const documentFragment = new DOMParser().parseFromString(
      `<body>${markup}</body>`,
      "text/html",
    );
    element.replaceChildren(...documentFragment.body.childNodes);
  }

  function pane(id) {
    return panes.find((item) => item.id === `pane-${id}`);
  }

  function showToast(message, error = false) {
    clearTimeout(toastTimer);
    toast.textContent = message;
    toast.classList.toggle("toast--error", error);
    toast.classList.add("is-visible");
    toastTimer = setTimeout(() => toast.classList.remove("is-visible"), 3200);
  }

  function setLoading(active, message = "Computing active population") {
    loading.querySelector("strong").textContent = message;
    loading.classList.toggle("is-visible", active);
    stage.setAttribute("aria-busy", String(active));
  }

  async function jsonRequest(path, options = {}) {
    const response = await fetch(apiUrl(path), {
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
      ...options,
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok)
      throw new Error(payload.error || `Request failed (${response.status})`);
    return payload;
  }

  function closeScopeDrawer() {
    scopeDrawer.hidden = true;
    scopeButton.setAttribute("aria-expanded", "false");
  }

  function activate(id, { historyMode = "replace" } = {}) {
    if (!validTabs.has(id)) return;
    tabs.forEach((tab) => {
      const selected = tab.dataset.target === id;
      tab.classList.toggle("is-active", selected);
      tab.setAttribute("aria-selected", String(selected));
      tab.setAttribute("tabindex", selected ? "0" : "-1");
    });
    panes.forEach((item) =>
      item.classList.toggle("is-active", item === pane(id)),
    );
    if (location.hash !== `#${id}`) {
      if (historyMode === "push") history.pushState(null, "", `#${id}`);
      else if (historyMode === "replace")
        history.replaceState(null, "", `#${id}`);
    }
    closeScopeDrawer();
  }

  function setRailCollapsed(collapsed, { persist = true } = {}) {
    appBody.classList.toggle("is-rail-collapsed", collapsed);
    railToggle.setAttribute("aria-expanded", String(!collapsed));
    const label = collapsed ? "Expand navigation" : "Collapse navigation";
    railToggle.setAttribute("aria-label", label);
    railToggle.title = label;
    tabs.forEach((tab) => {
      tab.title = tab.getAttribute("aria-label") || "Dashboard section";
    });
    if (!persist) return;
    try {
      localStorage.setItem(
        "forecast-dashboard:rail-collapsed",
        String(collapsed),
      );
    } catch {
      // Storage can be unavailable in hardened browser contexts.
    }
  }

  function initializeRail() {
    let collapsed = false;
    try {
      collapsed =
        localStorage.getItem("forecast-dashboard:rail-collapsed") === "true";
    } catch {
      collapsed = false;
    }
    setRailCollapsed(collapsed, { persist: false });
  }

  function currentIndex() {
    const focusedIndex = tabs.indexOf(document.activeElement);
    return focusedIndex >= 0
      ? focusedIndex
      : tabs.findIndex((tab) => tab.classList.contains("is-active"));
  }

  function activateSubpanel(group, target) {
    const buttons = Array.from(
      document.querySelectorAll(
        `[data-subtabs="${group}"] [data-subtab-target]`,
      ),
    );
    const panels = Array.from(
      document.querySelectorAll(`[data-subpanel^="${group}:"]`),
    );
    buttons.forEach((button) => {
      const selected = button.dataset.subtabTarget === target;
      button.classList.toggle("is-active", selected);
      button.setAttribute("aria-pressed", String(selected));
    });
    panels.forEach((panel) => {
      const selected = panel.dataset.subpanel === `${group}:${target}`;
      panel.classList.toggle("is-active", selected);
      panel.hidden = !selected;
    });
  }

  function option(value, label, selectedValue) {
    return `<option value="${escapeHtml(value ?? "")}"${String(value ?? "") === String(selectedValue ?? "") ? " selected" : ""}>${escapeHtml(label)}</option>`;
  }

  function populateSelect(name, entries, selected, allLabel = null) {
    const control = controls.get(name);
    if (!control) return;
    const values = [];
    if (allLabel !== null) values.push(option("", allLabel, selected));
    entries.forEach((entry) =>
      values.push(option(entry.value, entry.label, selected)),
    );
    setHtml(control, values.join(""));
  }

  function populateVintageValue(prefix, selectedKind, selectedValue, options) {
    const control = controls.get(`${prefix}_value`);
    if (!control) return;
    if (selectedKind === "specific_calculation_month") {
      setHtml(
        control,
        options.calculation_months
          .map((value) => option(value, monthLabel(value), selectedValue))
          .join(""),
      );
      control.disabled = false;
    } else if (selectedKind === "specific_horizon") {
      setHtml(
        control,
        options.horizons
          .map((value) => option(value, `M−${value}`, selectedValue))
          .join(""),
      );
      control.disabled = false;
    } else {
      setHtml(control, option("", "Not required", ""));
      control.disabled = true;
    }
  }

  function syncControls(payload) {
    const { request, options } = payload;
    controls.get("comparison_mode").value = String(request.comparison_mode);
    controls.get("source").value = request.source;
    controls.get("source").disabled = request.comparison_mode;
    document.querySelector("[data-vintage-group]").disabled =
      request.comparison_mode;
    document.querySelector("[data-performance-group]").disabled =
      request.comparison_mode;

    populateSelect(
      "target_start",
      options.target_months.map((value) => ({
        value,
        label: monthLabel(value),
      })),
      request.target_start,
    );
    populateSelect(
      "target_end",
      options.target_months.map((value) => ({
        value,
        label: monthLabel(value),
      })),
      request.target_end,
    );
    populateSelect(
      "brand",
      options.brands.map((value) => ({ value, label: value })),
      request.brand,
      "All brands + quality groups",
    );
    populateSelect(
      "parent_code",
      options.parent_products.map((row) => ({
        value: row.parent_code,
        label: `${row.parent_code} · ${row.parent_description}`,
      })),
      request.parent_code,
      `All ${options.parent_products.length} products`,
    );
    const horizonValues = request.comparison_mode
      ? options.common_horizons
      : options.horizons;
    populateSelect(
      "horizon",
      horizonValues.map((value) => ({ value, label: `M−${value}` })),
      request.horizon,
      request.comparison_mode
        ? "Default shared horizon"
        : "All available horizons",
    );

    for (const [name, value] of Object.entries(request)) {
      const control = controls.get(name);
      if (
        !control ||
        [
          "source",
          "comparison_mode",
          "target_start",
          "target_end",
          "brand",
          "parent_code",
          "horizon",
        ].includes(name)
      )
        continue;
      if (control.type === "checkbox") control.checked = Boolean(value);
      else if (value !== null && typeof value !== "object")
        control.value = String(value);
      else if (value === null) control.value = "";
    }
    controls.get("vintage_a_kind").value = request.vintage_a.kind;
    controls.get("vintage_b_kind").value = request.vintage_b.kind;
    populateVintageValue(
      "vintage_a",
      request.vintage_a.kind,
      request.vintage_a.value,
      options,
    );
    populateVintageValue(
      "vintage_b",
      request.vintage_b.kind,
      request.vintage_b.value,
      options,
    );
    updateFilterCount();
  }

  function buildRequest() {
    const value = (name) => controls.get(name)?.value ?? "";
    const numeric = (name) => (value(name) === "" ? null : Number(value(name)));
    const vintage = (prefix) => ({
      kind: value(`${prefix}_kind`),
      value: controls.get(`${prefix}_value`).disabled
        ? null
        : value(`${prefix}_value`),
    });
    return {
      source: value("source"),
      comparison_mode: value("comparison_mode") === "true",
      target_start: value("target_start") || null,
      target_end: value("target_end") || null,
      brand: value("brand") || null,
      parent_code: numeric("parent_code"),
      horizon: numeric("horizon"),
      minimum_actual_volume: numeric("minimum_actual_volume") ?? 0,
      vintage_a: vintage("vintage_a"),
      vintage_b: vintage("vintage_b"),
      revision_direction: value("revision_direction") || null,
      revision_outcome: value("revision_outcome") || null,
      revision_tolerance_kl: numeric("revision_tolerance_kl") ?? 0.01,
      forecast_direction: value("forecast_direction") || null,
      accuracy_band: value("accuracy_band") || null,
      bias_band: value("bias_band") || null,
      minimum_absolute_error_kl: numeric("minimum_absolute_error_kl") ?? 0,
      top_n: numeric("top_n"),
      top_n_metric: value("top_n_metric"),
      hierarchy_status: value("hierarchy_status") || null,
      actual_status: value("actual_status") || null,
      pair_status: value("pair_status") || null,
      source_availability: value("source_availability") || null,
      zero_forecast_only: controls.get("zero_forecast_only").checked,
      complete_vintage_history_only: controls.get(
        "complete_vintage_history_only",
      ).checked,
      product_parent_code: null,
      product_target_month: null,
    };
  }

  function updateFilterCount() {
    if (!defaults) return;
    const request = buildRequest();
    const ignored = new Set(["product_parent_code", "product_target_month"]);
    const active = Object.keys(defaults).filter((key) => {
      if (ignored.has(key) || !(key in request)) return false;
      return JSON.stringify(request[key]) !== JSON.stringify(defaults[key]);
    }).length;
    scopeButton.textContent = `Filters · ${active}`;
  }

  async function refreshView({ announce = false } = {}) {
    clearTimeout(refreshTimer);
    const serial = ++requestSerial;
    const request = buildRequest();
    setLoading(true);
    document.querySelector("[data-filter-note]").textContent =
      "Recomputing canonical metrics…";
    try {
      const payload = await jsonRequest("api/view", {
        method: "POST",
        body: JSON.stringify(request),
      });
      if (serial !== requestSerial) return;
      currentPayload = payload;
      currentRequest = payload.request;
      syncControls(payload);
      render(payload);
      if (announce) showToast("Shared population recomputed");
    } catch (error) {
      if (serial !== requestSerial) return;
      showToast(error.message, true);
      renderError(error.message);
    } finally {
      if (serial === requestSerial) {
        setLoading(false);
        document.querySelector("[data-filter-note]").textContent =
          "Changes apply automatically.";
      }
    }
  }

  function scheduleRefresh() {
    updateFilterCount();
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(() => refreshView({ announce: true }), 220);
  }

  function render(payload) {
    renderMeta(payload);
    renderState(payload.state);
    renderScope(payload);
    renderOverview(payload);
    renderTrends(payload);
    renderComparison(payload);
    renderProduct(payload.product_detail);
    renderExceptions(payload);
    renderQuality(payload.quality);
  }

  function renderMeta(payload) {
    const refresh =
      payload.meta.refresh_timestamp === "unknown"
        ? "Refresh time unknown"
        : `Inputs refreshed ${new Date(payload.meta.refresh_timestamp).toLocaleString()}`;
    document.querySelector("[data-refresh]").textContent = refresh;
    document.querySelector("[data-status]").textContent =
      "canonical dataset ready";
    document.querySelector("[data-status-population]").textContent =
      `population · ${count(payload.meta.dataset_rows)} forecast rows`;
    document.querySelector("[data-status-source]").textContent =
      payload.meta.data_source;
  }

  function renderState(state) {
    const banner = document.querySelector(".state-banner");
    const workspace = document.querySelector(".workspace");
    const messages = state.empty
      ? ["No eligible rows", state.message]
      : state.comparison_blocked
        ? ["Comparison unavailable", state.message]
        : state.zero_denominator
          ? ["Undefined ratio metrics", state.message]
          : null;
    banner.hidden = !messages;
    workspace.classList.toggle("has-state", Boolean(messages));
    if (messages) {
      banner.querySelector("[data-state-title]").textContent = messages[0];
      banner.querySelector("[data-state-copy]").textContent = messages[1] || "";
    }
  }

  function renderScope(payload) {
    const summary = payload.population_summary;
    const request = payload.request;
    const mode = request.comparison_mode ? "TM vs ML" : "Single source";
    const source = request.comparison_mode
      ? "TM + ML"
      : request.source.toUpperCase();
    const horizon =
      request.horizon === null ? "All available" : `M−${request.horizon}`;
    setHtml(
      document.querySelector("[data-scope-primary]"),
      [
        ["Mode", mode],
        ["Source", source],
        [
          "Target",
          `${monthLabel(request.target_start)}–${monthLabel(request.target_end)}`,
        ],
        ["Products", count(summary.products)],
        ["Horizons", horizon],
      ]
        .map(
          ([key, value]) =>
            `<span class="scope-token"><b>${key}</b><strong>${escapeHtml(value)}</strong></span>`,
        )
        .join(""),
    );
    setHtml(
      document.querySelector("[data-scope-audit]"),
      [
        `<span><b>Actual</b> ${kl(summary.actual_volume_kl)}</span>`,
        `<span><b>Eligible</b> ${count(summary.eligible_observations)}</span>`,
        `<span><b>Comparable</b> ${count(summary.comparable_pairs)}</span>`,
        `<span><b>Coverage</b> ${kl(summary.coverage_numerator_actual_kl)} / ${kl(summary.coverage_denominator_actual_kl)} · ${pct(summary.coverage_pct)}</span>`,
      ].join(""),
    );
  }

  function populationItem(label, value) {
    return `<span><b>${escapeHtml(label)}</b><strong>${escapeHtml(value)}</strong></span>`;
  }

  function kpi(label, value, delta, caption, tone = "") {
    return `<article class="kpi"><p class="kpi__label">${escapeHtml(label)}</p><div class="kpi__line"><strong class="kpi__val">${escapeHtml(value)}</strong><span class="delta ${tone}">${escapeHtml(delta)}</span></div><p class="kpi__cap">${escapeHtml(caption)}</p></article>`;
  }

  function renderOverview(payload) {
    const summary = payload.population_summary;
    const metrics = payload.metrics;
    document.querySelector("[data-overview-stamp]").textContent = payload
      .request.comparison_mode
      ? `canonical · exact M−${payload.request.horizon ?? "—"}`
      : `canonical · ${summary.vintage_a_rule || "—"} → ${summary.vintage_b_rule || "—"}`;
    setHtml(
      document.querySelector("[data-population]"),
      [
        populationItem("Forecast rows", count(summary.forecast_rows)),
        populationItem("Pair rows", count(summary.selected_pair_rows)),
        populationItem("Complete pairs", count(metrics.complete_pairs)),
        populationItem(
          "Missing vintages",
          count(metrics.missing_vintage_pairs),
        ),
        populationItem("Vintage A", summary.vintage_a_rule || "comparison N/A"),
        populationItem("Vintage B", summary.vintage_b_rule || "comparison N/A"),
        populationItem("Zero actual", count(metrics.zero_actual_observations)),
        populationItem(
          "Missing actual",
          count(metrics.missing_actual_observations),
        ),
      ].join(""),
    );
    const accuracyDelta = metrics.accuracy_delta_pp;
    const errorImprovement = metrics.total_error_improvement_kl;
    const netError =
      finite(metrics.forecast_kl) && finite(metrics.actual_kl)
        ? metrics.forecast_kl - metrics.actual_kl
        : null;
    setHtml(
      document.querySelector("[data-kpis]"),
      [
        kpi(
          "Forecast accuracy",
          pct(metrics.forecast_accuracy_pct),
          pp(accuracyDelta),
          `1 − ${kl(metrics.accuracy_numerator_kl)} / ${kl(metrics.accuracy_denominator_actual_kl)} · n ${count(metrics.eligible_observations)}`,
          accuracyDelta >= 0 ? "delta--up" : "delta--down",
        ),
        kpi(
          "Bias",
          pct(metrics.bias_pct),
          finite(metrics.bias_pct)
            ? metrics.bias_pct >= 0
              ? "over forecast"
              : "under forecast"
            : "undefined",
          `${signedKl(metrics.bias_numerator_kl)} / ${kl(metrics.bias_denominator_actual_kl)}`,
          Math.abs(metrics.bias_pct || 0) < 5 ? "delta--up" : "delta--down",
        ),
        kpi(
          "Absolute error",
          kl(metrics.absolute_error_kl),
          signedKl(errorImprovement),
          `Σ|forecast − actual| · n ${count(metrics.absolute_error_observations)}`,
          errorImprovement >= 0 ? "delta--up" : "delta--down",
        ),
        kpi(
          "Coverage",
          pct(metrics.coverage_pct),
          `${count(summary.coverage_pair_rows)} keys`,
          `${kl(metrics.coverage_numerator_actual_kl)} / ${kl(metrics.coverage_denominator_actual_kl)} actual`,
          "delta--up",
        ),
        kpi(
          "Actual volume",
          kl(metrics.actual_kl),
          `${count(metrics.population_observations)} rows`,
          "selected actual population",
        ),
        kpi(
          "Forecast volume",
          kl(metrics.forecast_kl),
          `${signedKl(netError)} net`,
          "selected Vintage B forecast",
          netError && Math.abs(netError) > 0 ? "delta--down" : "",
        ),
        kpi(
          "MAE",
          kl(metrics.mae_kl),
          `${count(metrics.mae_observations)} obs`,
          `${kl(metrics.absolute_error_kl)} / observations`,
        ),
        kpi(
          "Revision effectiveness",
          pct(metrics.revision_effectiveness_pct),
          `${count(metrics.effectiveness_numerator)} / ${count(metrics.effectiveness_denominator)}`,
          "improved / materially revised",
        ),
      ].join(""),
    );
    setHtml(
      document.querySelector("[data-overview-chart]"),
      lineChart(payload.monthly_performance.rows, "forecast_accuracy_pct", {
        volumeBars: true,
        label: "Monthly forecast accuracy",
      }),
    );
  }

  function chartExtent(values, includeZero = false) {
    const clean = values.filter(finite);
    if (!clean.length) return [0, 1];
    let min = Math.min(...clean);
    let max = Math.max(...clean);
    if (includeZero) {
      min = Math.min(min, 0);
      max = Math.max(max, 0);
    }
    if (min === max) return [min - 1, max + 1];
    const padding = (max - min) * 0.12;
    return [min - padding, max + padding];
  }

  function lineChart(
    rows,
    metric,
    { volumeBars = false, label = "Trend" } = {},
  ) {
    if (!rows.length) return emptyVisual("No monthly metric rows");
    const sources = [...new Set(rows.map((row) => row.source))];
    const months = [...new Set(rows.map((row) => row.snop_month))].sort();
    const width = 1000;
    const height = 230;
    const left = 72;
    const right = 950;
    const top = 28;
    const bottom = 190;
    const [min, max] = chartExtent(
      rows.map((row) => row[metric]),
      metric === "bias_pct",
    );
    const x = (month) =>
      left +
      (months.indexOf(month) / Math.max(1, months.length - 1)) * (right - left);
    const y = (value) =>
      bottom - ((value - min) / (max - min)) * (bottom - top);
    const colors = { tm: "var(--amber)", ml: "var(--teal)" };
    const grid = [0, 0.25, 0.5, 0.75, 1]
      .map((ratio) => {
        const gy = top + ratio * (bottom - top);
        const value = max - ratio * (max - min);
        return `<line x1="${left}" y1="${gy}" x2="${right}" y2="${gy}"/><text x="28" y="${gy + 4}">${escapeHtml(number(value, metric.includes("pct") ? 0 : 1))}</text>`;
      })
      .join("");
    const bars = volumeBars
      ? rows
          .filter((row) => row.source === sources[0])
          .map((row) => {
            const volumes = rows.map((item) => item.actual_kl).filter(finite);
            const maxVolume = Math.max(...volumes, 1);
            const barHeight = finite(row.actual_kl)
              ? (row.actual_kl / maxVolume) * 75
              : 0;
            return `<rect x="${x(row.snop_month) - 13}" y="${bottom - barHeight}" width="26" height="${barHeight}"/>`;
          })
          .join("")
      : "";
    const series = sources
      .map((source) => {
        const sourceRows = rows.filter(
          (row) => row.source === source && finite(row[metric]),
        );
        const points = sourceRows
          .map((row) => `${x(row.snop_month)},${y(row[metric])}`)
          .join(" ");
        const circles = sourceRows
          .map(
            (row) =>
              `<circle cx="${x(row.snop_month)}" cy="${y(row[metric])}" r="4"><title>${source.toUpperCase()} · ${monthLabel(row.snop_month)} · ${number(row[metric], 2)} · actual ${kl(row.actual_kl)} · forecast ${kl(row.forecast_kl)} · n ${count(row.eligible_observations)}</title></circle>`,
          )
          .join("");
        return `<polyline points="${points}" fill="none" stroke="${colors[source] || "var(--blue)"}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><g class="chart__points" style="--series:${colors[source] || "var(--blue)"}">${circles}</g>`;
      })
      .join("");
    const labels = months
      .map(
        (month) =>
          `<text x="${x(month)}" y="216">${escapeHtml(monthLabel(month).replace(/ \d{4}/, ""))}</text>`,
      )
      .join("");
    return `<svg class="chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(label)}"><title>${escapeHtml(label)}</title><g class="chart__grid">${grid}</g><g class="volume-bars">${bars}</g>${series}<g class="chart__labels">${labels}</g></svg>`;
  }

  function renderTrends(payload) {
    const monthlyMetric = document.querySelector(
      '[data-metric-selector="monthly"]',
    ).value;
    const horizonMetric = document.querySelector(
      '[data-metric-selector="horizon"]',
    ).value;
    const heatmapMetric = document.querySelector(
      '[data-metric-selector="heatmap"]',
    ).value;
    const metricLabels = {
      forecast_accuracy_pct: "Forecast accuracy",
      bias_pct: "Bias",
      absolute_error_kl: "Absolute error",
      forecast_kl: "Forecast and actual volume",
      vintage_a_accuracy_pct: "Vintage A accuracy",
      vintage_b_accuracy_pct: "Vintage B accuracy",
      accuracy_delta_pp: "Accuracy delta",
      revision_effectiveness_pct: "Revision effectiveness",
    };
    document.querySelector("[data-trend-title]").textContent =
      `${metricLabels[monthlyMetric]} by target month`;
    document.querySelector("[data-trend-subtitle]").textContent =
      `${payload.request.comparison_mode ? "Aligned TM and ML" : payload.request.source.toUpperCase()} · ${payload.monthly_performance.total} monthly rows`;
    const sources = [
      ...new Set(payload.monthly_performance.rows.map((row) => row.source)),
    ];
    setHtml(
      document.querySelector("[data-trend-legend]"),
      sources
        .map(
          (source) =>
            `<span><i class="key key--${source === "tm" ? "amber" : "teal"}"></i>${source.toUpperCase()}</span>`,
        )
        .join(""),
    );
    setHtml(
      document.querySelector("[data-trend-chart]"),
      lineChart(payload.monthly_performance.rows, monthlyMetric, {
        label: `${metricLabels[monthlyMetric]} by month`,
      }),
    );
    renderHorizonBars(payload.horizon_performance.rows, horizonMetric);
    renderHeatmap(payload.brand_target_month_performance.rows, heatmapMetric);
  }

  function renderHorizonBars(rows, metric) {
    const container = document.querySelector("[data-horizon-bars]");
    if (!rows.length) {
      setHtml(container, emptyVisual("No horizon rows"));
      return;
    }
    const horizons = [
      ...new Set(rows.map((row) => row.forecast_horizon_months)),
    ].sort((a, b) => b - a);
    const values = rows.map((row) => row[metric]).filter(finite);
    const max = Math.max(
      ...values.map(Math.abs),
      metric.includes("pct") ? 100 : 1,
    );
    const sourceRows = new Map(
      rows.map((row) => [`${row.source}:${row.forecast_horizon_months}`, row]),
    );
    setHtml(
      container,
      horizons
        .map((horizon) => {
          const tm = sourceRows.get(`tm:${horizon}`);
          const ml = sourceRows.get(`ml:${horizon}`);
          const only = tm || ml;
          const tmValue = tm?.[metric];
          const mlValue = ml?.[metric];
          const tmWidth = finite(tmValue)
            ? Math.min(100, (Math.abs(tmValue) / max) * 100)
            : 0;
          const mlWidth = finite(mlValue)
            ? Math.min(100, (Math.abs(mlValue) / max) * 100)
            : only && only.source === "ml"
              ? Math.min(100, (Math.abs(only[metric]) / max) * 100)
              : 0;
          const display =
            tm && ml
              ? `${number(tmValue, 1)} / ${number(mlValue, 1)}`
              : `${only.source.toUpperCase()} ${number(only[metric], 1)}`;
          return `<div class="dual-row"><span>M−${horizon}</span><i style="--tm:${tmWidth}%;--ml:${mlWidth}%"></i><strong>${escapeHtml(display)}</strong></div>`;
        })
        .join(""),
    );
    document.querySelector("[data-horizon-range]").textContent =
      `${number(Math.min(...values), 1)} → ${number(Math.max(...values), 1)}`;
  }

  function renderHeatmap(rows, metric) {
    const container = document.querySelector("[data-heatmap]");
    if (!rows.length) {
      setHtml(container, emptyVisual("No brand-month rows"));
      document.querySelector("[data-heatmap-range]").textContent = "—";
      return;
    }
    const months = [...new Set(rows.map((row) => row.snop_month))]
      .sort()
      .slice(-6);
    const filtered = rows.filter((row) => months.includes(row.snop_month));
    const brandRows = new Map();
    filtered.forEach((row) => {
      if (!brandRows.has(row.brand_display))
        brandRows.set(row.brand_display, []);
      brandRows.get(row.brand_display).push(row);
    });
    const score = (items) => {
      const values = items.map((row) => row[metric]).filter(finite);
      if (!values.length) return Infinity;
      if (metric === "bias_pct")
        return (
          -values.reduce((sum, value) => sum + Math.abs(value), 0) /
          values.length
        );
      if (metric === "absolute_error_kl")
        return -values.reduce((sum, value) => sum + value, 0);
      return values.reduce((sum, value) => sum + value, 0) / values.length;
    };
    const brands = [...brandRows.keys()]
      .sort((a, b) => score(brandRows.get(a)) - score(brandRows.get(b)))
      .slice(0, 8);
    const values = filtered.map((row) => row[metric]).filter(finite);
    const [min, max] = chartExtent(values);
    const level = (value) =>
      finite(value)
        ? Math.max(
            1,
            Math.min(5, Math.ceil(((value - min) / (max - min || 1)) * 5)),
          )
        : 0;
    const lookup = new Map(
      filtered.map((row) => [`${row.brand_display}:${row.snop_month}`, row]),
    );
    container.style.gridTemplateColumns = `84px repeat(${months.length}, minmax(22px, 1fr))`;
    const header = `<span></span>${months.map((month) => `<b>${escapeHtml(monthLabel(month).split(" ")[0])}</b>`).join("")}`;
    const body = brands
      .map(
        (brand) =>
          `<b title="${escapeHtml(brand)}">${escapeHtml(brand)}</b>${months
            .map((month) => {
              const row = lookup.get(`${brand}:${month}`);
              const value = row?.[metric];
              return `<i data-level="${level(value)}" title="${escapeHtml(brand)} · ${monthLabel(month)} · ${number(value, 2)} · n ${count(row?.eligible_observations)}">${finite(value) ? number(value, metric.includes("kl") ? 0 : 1) : "—"}</i>`;
            })
            .join("")}`,
      )
      .join("");
    setHtml(container, header + body);
    document.querySelector("[data-heatmap-range]").textContent = values.length
      ? `${number(Math.min(...values), 1)} → ${number(Math.max(...values), 1)}`
      : "—";
  }

  function renderComparison(payload) {
    renderRevisionPanel(payload);
    renderSourcePanel(payload);
  }

  function renderRevisionPanel(payload) {
    const panel = document.querySelector("[data-revision-panel]");
    if (payload.request.comparison_mode) {
      setHtml(
        panel,
        messagePanel(
          "Vintage revisions use single-source mode",
          "Switch to TM or ML single-source scope to compare Vintage A and Vintage B without conflating the source comparison.",
          "Use single-source mode",
          "single",
        ),
      );
      return;
    }
    const metrics = payload.metrics;
    const diagnostics = rowMap(payload.revision_diagnostics.rows, "category");
    const rules = payload.population_summary;
    setHtml(
      panel,
      `
      <div class="comparison-ledger"><span><b>Vintage A</b> ${escapeHtml(rules.vintage_a_rule)}</span><span><b>Vintage B</b> ${escapeHtml(rules.vintage_b_rule)}</span><span><b>Tolerance</b> ${number(payload.request.revision_tolerance_kl, 2)} KL</span><span><b>Complete</b> ${count(metrics.complete_pairs)}</span><span><b>Incomplete</b> ${count(metrics.missing_vintage_pairs)}</span></div>
      <div class="kpis kpis--row comparison-kpis">
        ${kpi("Vintage accuracy delta", pp(metrics.accuracy_delta_pp), metrics.accuracy_delta_pp >= 0 ? "B improved" : "B worsened", `${signedKl(metrics.accuracy_delta_numerator_kl)} / ${kl(metrics.accuracy_delta_denominator_actual_kl)}`, metrics.accuracy_delta_pp >= 0 ? "delta--up" : "delta--down")}
        ${kpi("Revision effectiveness", pct(metrics.revision_effectiveness_pct), `${count(metrics.effectiveness_numerator)} / ${count(metrics.effectiveness_denominator)}`, "improved / materially revised")}
        ${kpi("Total error improvement", signedKl(metrics.total_error_improvement_kl), metrics.total_error_improvement_kl >= 0 ? "positive improves" : "negative worsens", `Σ(|error A| − |error B|) · n ${count(metrics.complete_pairs)}`, metrics.total_error_improvement_kl >= 0 ? "delta--up" : "delta--down")}
      </div>
      <div class="revision-layout">
        <section class="frame"><header class="frame__head"><div><h3 class="frame__title">Revision outcomes</h3><p class="frame__sub">Unchanged rows stay outside effectiveness</p></div><span class="frame__metric">up ${pct(metrics.revised_up_pct)} · down ${pct(metrics.revised_down_pct)}</span></header><div class="outcome-body"><div class="outcome-strip">${["improved", "worsened", "neutral", "unchanged"].map((category) => `<span class="outcome outcome--${category === "improved" ? "good" : category === "worsened" ? "bad" : category === "neutral" ? "neutral" : "idle"}"><b>${labelize(category)}</b><strong>${count(diagnostics.get(category)?.observations || 0)}</strong></span>`).join("")}</div><div class="mini-table">${revisionTable(payload.revision_diagnostics.rows)}</div></div></section>
        <section class="frame"><header class="frame__head"><div><h3 class="frame__title">Revision amount vs error improvement</h3><p class="frame__sub">Zero references expose helped and harmed revisions</p></div><span class="frame__metric">${count(payload.revision_scatter.total)} complete points</span></header><div class="frame__body">${scatterChart(payload.revision_scatter.rows, "revision_kl", "error_improvement_kl", "Revision amount versus error improvement")}</div></section>
      </div>`,
    );
  }

  function revisionTable(rows) {
    const header =
      "<span><b>Outcome</b><strong>Rows</strong><em>Revision KL</em><i>Error improvement</i></span>";
    return (
      header +
      rows
        .map(
          (row) =>
            `<span><b>${escapeHtml(labelize(row.category))}</b><strong>${count(row.observations)}</strong><em>${signedKl(row.revision_kl)}</em><i class="${row.error_improvement_kl > 0 ? "good" : row.error_improvement_kl < 0 ? "bad" : ""}">${signedKl(row.error_improvement_kl)}</i></span>`,
        )
        .join("")
    );
  }

  function renderSourcePanel(payload) {
    const panel = document.querySelector("[data-source-panel]");
    const comparison = payload.comparison;
    if (!payload.request.comparison_mode || !comparison) {
      setHtml(
        panel,
        messagePanel(
          "TM vs ML requires comparison mode",
          "The source comparison uses one exact horizon and a common product-target population. Source-only rows remain coverage evidence.",
          "Enable comparison",
          "comparison",
        ),
      );
      return;
    }
    if (comparison.blocked) {
      setHtml(
        panel,
        messagePanel(
          "No aligned comparison is available",
          comparison.warning ||
            comparison.coverage_warning ||
            "Choose a shared exact horizon.",
          "Review filters",
          "filters",
        ),
      );
      return;
    }
    const tm = comparison.tm_metrics;
    const ml = comparison.ml_metrics;
    const deltas = new Map(
      comparison.deltas.rows.map((row) => [row.metric, row]),
    );
    const population = comparison.population_summary.rows;
    setHtml(
      panel,
      `
      <div class="comparison-alert"><span class="severity severity--good">Aligned</span><strong>Exact M−${comparison.selected_horizon} · ${count(comparison.comparable_pairs)} common product-target observations</strong><span>${escapeHtml(comparison.coverage_warning || "Source-only populations affect coverage, not like-for-like metrics.")}</span></div>
      <div class="source-compare-kpis">${sourceCard("tm", tm)}${sourceCard("ml", ml)}<div class="delta-stack">${[
        "Forecast accuracy",
        "Bias",
        "Absolute error",
        "Coverage",
      ]
        .map((metric) => {
          const row = deltas.get(metric);
          const value = row?.delta_ml_minus_tm;
          const formatted = row?.unit === "KL" ? signedKl(value) : pp(value);
          const good =
            metric === "Absolute error"
              ? value <= 0
              : metric === "Bias"
                ? Math.abs(ml.bias_pct || 0) < Math.abs(tm.bias_pct || 0)
                : value >= 0;
          return `<span><b>ML − TM ${escapeHtml(metric)}</b><strong class="${good ? "good" : "bad"}">${escapeHtml(formatted)}</strong></span>`;
        })
        .join("")}</div></div>
      <div class="source-layout"><section class="frame"><header class="frame__head"><div><h3 class="frame__title">Paired absolute error</h3><p class="frame__sub">Points below the diagonal favour ML</p></div><span class="frame__metric">${comparison.winner_counts.rows.map((row) => `${row.winner_label} ${row.observations}`).join(" · ")}</span></header><div class="frame__body">${pairedScatter(comparison.paired_comparison.rows)}</div></section><section class="frame"><header class="frame__head"><div><h3 class="frame__title">Aligned population</h3><p class="frame__sub">Common metrics and source coverage remain distinct</p></div><span class="frame__metric">actual KL</span></header><div class="population-table">${populationTable(population)}</div></section></div>`,
    );
  }

  function sourceCard(source, metrics) {
    return `<article class="source-card source-card--${source}"><header>${sourceBadge(source)}<span>common population</span></header><div><b>Accuracy</b><strong>${pct(metrics.forecast_accuracy_pct)}</strong></div><div><b>Bias</b><strong>${pct(metrics.bias_pct)}</strong></div><div><b>Absolute error</b><strong>${kl(metrics.absolute_error_kl)}</strong></div><div><b>Coverage</b><strong>${pct(metrics.coverage_pct)}</strong></div></article>`;
  }

  function populationTable(rows) {
    return (
      "<div><b>Population</b><strong>Obs</strong><em>Actual</em><i>Status</i></div>" +
      rows
        .map(
          (row) =>
            `<div><b>${escapeHtml(labelize(row.population))}</b><strong>${count(row.observations)}</strong><em>${kl(row.actual_kl)}</em><i>${escapeHtml(row.status)}</i></div>`,
        )
        .join("")
    );
  }

  function scatterChart(rows, xKey, yKey, label) {
    const valid = rows.filter((row) => finite(row[xKey]) && finite(row[yKey]));
    if (!valid.length) return emptyVisual("No comparable scatter points");
    const width = 520;
    const height = 280;
    const left = 62;
    const right = 485;
    const top = 28;
    const bottom = 250;
    const [xMin, xMax] = chartExtent(
      valid.map((row) => row[xKey]),
      true,
    );
    const [yMin, yMax] = chartExtent(
      valid.map((row) => row[yKey]),
      true,
    );
    const x = (value) =>
      left + ((value - xMin) / (xMax - xMin)) * (right - left);
    const y = (value) =>
      bottom - ((value - yMin) / (yMax - yMin)) * (bottom - top);
    const circles = valid
      .map(
        (row) =>
          `<circle class="${row.revision_outcome === "worsened" ? "scatter--warn" : ""}" cx="${x(row[xKey])}" cy="${y(row[yKey])}" r="${Math.max(3, Math.min(8, Math.sqrt(Math.abs(row.actual_kl || 1))))}"><title>${row.parent_code} · ${monthLabel(row.snop_month)} · x ${number(row[xKey], 2)} · y ${number(row[yKey], 2)}</title></circle>`,
      )
      .join("");
    return `<svg class="chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(label)}"><title>${escapeHtml(label)}</title><g class="chart__grid"><line x1="${left}" y1="${top}" x2="${right}" y2="${top}"/><line x1="${left}" y1="${(top + bottom) / 2}" x2="${right}" y2="${(top + bottom) / 2}"/><line x1="${left}" y1="${bottom}" x2="${right}" y2="${bottom}"/></g><line class="zero-line" x1="${x(0)}" y1="${top}" x2="${x(0)}" y2="${bottom}"/><line class="zero-line" x1="${left}" y1="${y(0)}" x2="${right}" y2="${y(0)}"/><g class="scatter">${circles}</g></svg>`;
  }

  function pairedScatter(rows) {
    const xKey =
      rows.length && "tm_absolute_error_kl" in rows[0]
        ? "tm_absolute_error_kl"
        : "tm_error_kl";
    const yKey =
      rows.length && "ml_absolute_error_kl" in rows[0]
        ? "ml_absolute_error_kl"
        : "ml_error_kl";
    const valid = rows.filter((row) => finite(row[xKey]) && finite(row[yKey]));
    if (!valid.length) return emptyVisual("No paired error points");
    const max = Math.max(...valid.flatMap((row) => [row[xKey], row[yKey]]), 1);
    const left = 65;
    const right = 475;
    const top = 35;
    const bottom = 250;
    const x = (value) => left + (value / max) * (right - left);
    const y = (value) => bottom - (value / max) * (bottom - top);
    return `<svg class="chart" viewBox="0 0 520 280" role="img" aria-label="Paired TM versus ML absolute error"><title>Paired TM versus ML absolute error</title><line class="diagonal" x1="${left}" y1="${bottom}" x2="${right}" y2="${top}"/><g class="scatter">${valid.map((row) => `<circle class="${row.winner === "tm" ? "scatter--warn" : ""}" cx="${x(row[xKey])}" cy="${y(row[yKey])}" r="5"><title>${row.parent_code} · TM ${number(row[xKey], 2)} · ML ${number(row[yKey], 2)} · ${row.winner_label || row.winner}</title></circle>`).join("")}</g></svg>`;
  }

  function messagePanel(title, copy, action, kind) {
    return `<section class="frame message-frame"><div class="message-state"><span class="severity severity--warn">Mode</span><h3>${escapeHtml(title)}</h3><p>${escapeHtml(copy)}</p><button class="btn btn--accent" data-mode-action="${escapeHtml(kind)}" type="button">${escapeHtml(action)}</button></div></section>`;
  }

  function renderProduct(detail) {
    const productControl = document.querySelector(
      '[data-product-control="parent"]',
    );
    const monthControl = document.querySelector(
      '[data-product-control="month"]',
    );
    if (!detail || detail.error) {
      setHtml(productControl, option("", "No product available", ""));
      setHtml(monthControl, option("", "No target month available", ""));
      setHtml(
        document.querySelector("[data-product-summary]"),
        populationItem(
          "History",
          detail?.error || "No active product-target keys",
        ),
      );
      setHtml(
        document.querySelector("[data-history-chart]"),
        emptyVisual("No product history"),
      );
      setHtml(document.querySelector("[data-stability]"), "");
      setHtml(document.querySelector("[data-product-revisions]"), "");
      return;
    }
    setHtml(
      productControl,
      detail.product_options
        .map((row) =>
          option(
            row.parent_code,
            `${row.parent_code} · ${row.parent_description}`,
            detail.parent_code,
          ),
        )
        .join(""),
    );
    setHtml(
      monthControl,
      detail.target_options
        .map((value) => option(value, monthLabel(value), detail.target_month))
        .join(""),
    );
    document.querySelector("[data-product-source]").textContent = detail.sources
      .map((source) => source.toUpperCase())
      .join(" + ");
    setHtml(
      document.querySelector("[data-product-summary]"),
      [
        populationItem("Product", detail.parent_code),
        populationItem("Description", detail.parent_description),
        populationItem("Brand", detail.brand || "Unmapped"),
        populationItem("Mapping", labelize(detail.mapping_status)),
        populationItem("Actual", kl(detail.actual_kl)),
        populationItem("History", detail.status_message),
      ].join(""),
    );
    setHtml(
      document.querySelector("[data-history-chart]"),
      historyChart(detail),
    );
    setHtml(
      document.querySelector("[data-stability]"),
      detail.stability.rows.map(stabilityCard).join(""),
    );
    setHtml(
      document.querySelector("[data-product-revisions]"),
      productRevisionTable(detail.revisions.rows),
    );
  }

  function historyChart(detail) {
    const rows = detail.points.rows.filter((row) => finite(row.forecast_kl));
    if (!rows.length)
      return emptyVisual(detail.status_message || "No product history");
    const months = [
      ...new Set(rows.map((row) => row.calculation_month)),
    ].sort();
    const values = rows.map((row) => row.forecast_kl);
    if (finite(detail.actual_kl)) values.push(detail.actual_kl);
    const [min, max] = chartExtent(values);
    const left = 62;
    const right = 730;
    const top = 30;
    const bottom = 220;
    const x = (month) =>
      left +
      (months.indexOf(month) / Math.max(1, months.length - 1)) * (right - left);
    const y = (value) =>
      bottom - ((value - min) / (max - min)) * (bottom - top);
    const colors = { tm: "var(--amber)", ml: "var(--teal)" };
    const series = [...new Set(rows.map((row) => row.source))]
      .map((source) => {
        const sourceRows = rows.filter((row) => row.source === source);
        return `<polyline points="${sourceRows.map((row) => `${x(row.calculation_month)},${y(row.forecast_kl)}`).join(" ")}" fill="none" stroke="${colors[source]}" stroke-width="3"/>${sourceRows.map((row) => `<circle cx="${x(row.calculation_month)}" cy="${y(row.forecast_kl)}" r="4" fill="white" stroke="${colors[source]}" stroke-width="3"><title>${source.toUpperCase()} · ${dateLabel(row.calculation_month)} · M−${row.forecast_horizon_months} · ${kl(row.forecast_kl)} · error ${signedKl(row.error_kl)} · bias ${pct(row.bias_pct)}</title></circle>`).join("")}`;
      })
      .join("");
    const actual = finite(detail.actual_kl)
      ? `<line class="actual-line" x1="${left}" y1="${y(detail.actual_kl)}" x2="${right}" y2="${y(detail.actual_kl)}"/><text x="${right - 45}" y="${y(detail.actual_kl) - 7}">Actual ${number(detail.actual_kl, 1)} KL</text>`
      : "";
    const labels = months
      .map(
        (month) =>
          `<text x="${x(month)}" y="244">${escapeHtml(monthLabel(month).split(" ")[0])}</text>`,
      )
      .join("");
    return `<svg class="chart" viewBox="0 0 760 250" role="img" aria-label="Chronological forecast development"><title>Chronological forecast development</title>${actual}${series}<g class="chart__labels">${labels}</g></svg>`;
  }

  function stabilityCard(row) {
    return `<article><header>${sourceBadge(row.source)}<span>${count(row.vintage_count)} vintages</span></header><div><b>Forecast range</b><strong>${kl(row.forecast_range_kl)}</strong></div><div><b>Volatility</b><strong>${kl(row.forecast_volatility_kl)}</strong></div><div><b>Revision count</b><strong>${count(row.revision_count)}</strong></div><div><b>Maximum revision</b><strong>${kl(row.maximum_absolute_revision_kl)}</strong></div><footer>${escapeHtml(row.history_message)}</footer></article>`;
  }

  function productRevisionTable(rows) {
    const header =
      '<div role="row"><b role="columnheader">Source</b><strong role="columnheader">From → to</strong><em role="columnheader">Horizon</em><i role="columnheader">Revision</i><span role="columnheader">Direction</span><small role="columnheader">Error after</small></div>';
    if (!rows.length)
      return (
        header +
        '<div role="row"><strong role="cell">No consecutive revisions available</strong></div>'
      );
    return (
      header +
      rows
        .slice(-6)
        .reverse()
        .map(
          (row) =>
            `<div role="row"><b role="cell">${sourceBadge(row.source)}</b><strong role="cell">${dateLabel(row.previous_calculation_month)} → ${dateLabel(row.calculation_month)}</strong><em role="cell">M−${row.previous_horizon_months} → M−${row.forecast_horizon_months}</em><i role="cell">${signedKl(row.revision_kl)}</i><span role="cell">${labelize(row.revision_direction)}</span><small role="cell" class="${row.error_improvement_kl > 0 ? "good" : row.error_improvement_kl < 0 ? "bad" : ""}">${signedKl(row.error_kl)}</small></div>`,
        )
        .join("")
    );
  }

  async function refreshProduct() {
    if (!currentRequest) return;
    const request = {
      ...currentRequest,
      product_parent_code:
        Number(
          document.querySelector('[data-product-control="parent"]').value,
        ) || null,
      product_target_month:
        document.querySelector('[data-product-control="month"]').value || null,
    };
    setLoading(true, "Loading product vintage history");
    try {
      const payload = await jsonRequest("api/product", {
        method: "POST",
        body: JSON.stringify(request),
      });
      renderProduct(payload.product_detail);
    } catch (error) {
      showToast(error.message, true);
    } finally {
      setLoading(false);
    }
  }

  function renderExceptions(payload) {
    const rows = payload.exceptions.rows;
    setHtml(
      document.querySelector("[data-exception-summary]"),
      [
        populationItem("Active rows", count(payload.exceptions.total)),
        populationItem("Loaded", count(rows.length)),
        populationItem("Default ranking", "Vintage B absolute error"),
        populationItem(
          "Scope",
          `${count(payload.population_summary.selected_pair_rows)} selected pairs`,
        ),
      ].join(""),
    );
    renderExceptionRows();
  }

  function renderExceptionRows() {
    const table = document.querySelector("[data-exception-table]");
    if (!currentPayload) return;
    const query = document
      .querySelector("[data-exception-search]")
      .value.trim()
      .toLowerCase();
    const limit = Number(
      document.querySelector("[data-exception-limit]").value,
    );
    const rows = currentPayload.exceptions.rows
      .filter((row) => JSON.stringify(row).toLowerCase().includes(query))
      .slice(0, limit);
    const header =
      '<div class="audit-table__head" role="row"><span>Source</span><span>Product</span><span>Brand</span><span>Target</span><span>Actual</span><span>Latest</span><span>Abs error</span><span>Bias</span><span>Outcome</span><span>Pair / mapping</span></div>';
    const body = rows
      .map(
        (row) =>
          `<div class="audit-table__row" role="row"><span>${sourceBadge(row.source)}</span><strong>${escapeHtml(row.parent_code)}</strong><span>${escapeHtml(row.brand)}</span><span>${escapeHtml(monthLabel(row.snop_month))}</span><span>${escapeHtml(kl(row.actual_kl))}</span><span>${escapeHtml(kl(row.vintage_b_forecast_kl))}</span><span class="${row.absolute_error_b_kl > 0 ? "bad" : ""}">${escapeHtml(kl(row.absolute_error_b_kl))}</span><span>${escapeHtml(pct(finite(row.bias_b_kl) && finite(row.actual_kl) && row.actual_kl !== 0 ? (row.bias_b_kl / row.actual_kl) * 100 : null))}</span><span class="${row.revision_outcome === "improved" ? "good" : row.revision_outcome === "worsened" ? "bad" : ""}">${escapeHtml(labelize(row.revision_outcome))}</span><span>${escapeHtml(labelize(row.pair_status))} · ${escapeHtml(labelize(row.mapping_status))}</span></div>`,
      )
      .join("");
    setHtml(
      table,
      `${header}<div class="audit-table__rows">${body || '<div class="empty-row">No loaded exceptions match this search.</div>'}</div><div class="audit-table__foot">The CSV contains every active row and all 21 audit columns, not only the loaded preview.</div>`,
    );
  }

  function qualityGoodStatus(category) {
    return {
      hierarchy: "mapped",
      actual: "matched_positive",
      pairs: "complete",
      source_availability: "both_sources",
    }[category];
  }

  function renderQuality(quality) {
    const attention = quality.attention_categories;
    document.querySelector("[data-quality-badge]").textContent =
      count(attention);
    document.querySelector("[data-quality-stamp]").textContent = attention
      ? `${attention} categories need attention`
      : "No active exceptions";
    const blocking = quality.blocking_errors;
    setHtml(
      document.querySelector("[data-blocking]"),
      blocking.length
        ? `<span class="severity severity--bad">Blocked</span><strong>${count(blocking.length)} blocking input errors</strong><span>${escapeHtml(blocking.join(" · "))}</span>`
        : '<span class="severity severity--good">Inputs valid</span><strong>Blocking input errors: none</strong><span>Quality exceptions remain non-blocking and auditable.</span>',
    );
    const labels = {
      hierarchy: "Hierarchy mapping",
      actual: "Actual availability",
      pairs: "Vintage pairs",
      source_availability: "Source availability",
    };
    setHtml(
      document.querySelector("[data-quality-cards]"),
      Object.entries(quality.categories)
        .map(([category, detail]) => {
          const good = detail.counts.rows.find(
            (row) => row.status === qualityGoodStatus(category),
          );
          const total = detail.counts.rows.reduce(
            (sum, row) => sum + row.observations,
            0,
          );
          const bad = total - (good?.observations || 0);
          return `<article class="qcard"><div class="qcard__top"><p class="qcard__k">${labels[category]}</p><span class="severity ${detail.has_attention ? "severity--warn" : "severity--good"}">${detail.has_attention ? "Review" : "Ready"}</span></div><strong class="qcard__v">${count(good?.observations || 0)} / ${count(total)}</strong><p class="qcard__cap">${count(bad)} observations outside the good status</p></article>`;
        })
        .join(""),
    );
    Object.entries(quality.categories).forEach(([category, detail]) =>
      renderQualityPanel(category, detail),
    );
    const exclusions = quality.scope_exclusion_counts.rows;
    document.querySelector("[data-baseline-summary]").textContent =
      `Baseline scope exclusions · ${count(exclusions.reduce((sum, row) => sum + row.observations, 0))} observations outside active scope`;
    setHtml(
      document.querySelector("[data-baseline]"),
      exclusions.length
        ? exclusions
            .map(
              (row) =>
                `<span>${escapeHtml(labelize(row.category))}: ${escapeHtml(labelize(row.status))} ${count(row.observations)}</span>`,
            )
            .join("") +
            '<button class="btn" type="button" data-export-kind="scope_exclusions" data-export-category="pairs">Scope exclusions · CSV</button>'
        : "<span>No baseline exclusions in this scope.</span>",
    );
  }

  function qualityStatusTone(severity) {
    if (severity === "info") return "good";
    if (severity === "warning") return "warn";
    return "bad";
  }

  function renderQualityPanel(category, detail) {
    const panel = document.querySelector(
      `[data-subpanel="quality:${category}"]`,
    );
    const labels = {
      hierarchy: "Hierarchy mapping",
      actual: "Actual availability",
      pairs: "Vintage pair completeness",
      source_availability: "Source availability",
    };
    const counts = detail.counts.rows;
    const countClass =
      counts.length >= 4
        ? "quality-counts quality-counts--four"
        : "quality-counts";
    setHtml(
      panel,
      `<section class="frame"><header class="frame__head"><div><h3 class="frame__title">${labels[category]}</h3><p class="frame__sub">${escapeHtml(detail.explanation)}</p></div><button class="btn" type="button" data-export-kind="quality" data-export-category="${category}">${labels[category]} exceptions · CSV</button></header><div class="quality-detail"><div class="${countClass}">${counts.map((row) => `<span class="quality-status quality-status--${qualityStatusTone(row.severity)}"><b>${escapeHtml(labelize(row.status))}</b><strong>${count(row.observations)}</strong><em>${count(row.products)} products · ${count(row.target_months)} months</em><i>${kl(row.actual_kl)} actual</i></span>`).join("")}</div><div class="quality-exceptions">${qualityExceptions(detail.exceptions.rows)}</div></div></section>`,
    );
  }

  function qualityExceptions(rows) {
    if (!rows.length)
      return '<article><span class="severity severity--good">Clear</span><div><strong>No active exceptions</strong><p>The selected category has no non-good rows.</p></div><em>0 rows</em></article>';
    return rows
      .slice(0, 5)
      .map(
        (row) =>
          `<article><span class="severity ${row.quality_status_group === "mapped" || row.quality_status_group === "complete" || row.quality_status_group === "both_sources" ? "severity--good" : "severity--warn"}">${escapeHtml(labelize(row.quality_status))}</span><div><strong>${escapeHtml(row.parent_code ?? "Population")} · ${escapeHtml(row.parent_description || monthLabel(row.snop_month))}</strong><p>${escapeHtml(row.quality_explanation)}</p></div><em>${escapeHtml(row.source ? row.source.toUpperCase() : row.available_sources || "")}</em></article>`,
      )
      .join("");
  }

  function emptyVisual(message) {
    return `<div class="empty-visual"><span class="severity severity--warn">Empty</span><strong>${escapeHtml(message)}</strong></div>`;
  }

  function renderError(message) {
    renderState({
      empty: true,
      message,
      comparison_blocked: false,
      zero_denominator: false,
    });
    document.querySelector("[data-status]").textContent =
      "dashboard request failed";
  }

  async function exportCsv(button) {
    if (!currentRequest) return;
    setLoading(true, "Preparing exact-scope CSV");
    try {
      const response = await fetch(apiUrl("api/export"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          request: currentRequest,
          kind: button.dataset.exportKind,
          category: button.dataset.exportCategory || null,
        }),
      });
      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.error || `Export failed (${response.status})`);
      }
      const blob = await response.blob();
      const disposition = response.headers.get("Content-Disposition") || "";
      const filename =
        disposition.match(/filename="([^"]+)"/)?.[1] ||
        "forecast-dashboard.csv";
      const href = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = href;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(href);
      showToast(`${filename} downloaded`);
    } catch (error) {
      showToast(error.message, true);
    } finally {
      setLoading(false);
    }
  }

  function resetDashboard() {
    if (!defaults) return;
    currentRequest = structuredClone(defaults);
    applyRequestToControls(defaults);
    document.querySelectorAll("[data-metric-selector]").forEach((select) => {
      select.selectedIndex = 0;
    });
    document.querySelector("[data-exception-search]").value = "";
    document.querySelector("[data-exception-limit]").value = "10";
    document.querySelector(".baseline").open = false;
    activateSubpanel("comparison", "revision");
    activateSubpanel("history", "product");
    activateSubpanel("quality", "hierarchy");
    activate("overview");
    refreshView({ announce: true });
    tabs.find((tab) => tab.dataset.target === "overview")?.focus();
  }

  function applyRequestToControls(request) {
    controls.get("comparison_mode").value = String(request.comparison_mode);
    controls.get("source").value = request.source;
    Object.entries(request).forEach(([name, value]) => {
      const control = controls.get(name);
      if (!control) return;
      if (control.type === "checkbox") control.checked = Boolean(value);
      else if (value === null || typeof value !== "object")
        control.value = value ?? "";
    });
    controls.get("vintage_a_kind").value = request.vintage_a.kind;
    controls.get("vintage_b_kind").value = request.vintage_b.kind;
  }

  rail.addEventListener("click", (event) => {
    const tab = event.target.closest('[role="tab"]');
    if (tab) activate(tab.dataset.target, { historyMode: "push" });
  });
  rail.addEventListener("keydown", (event) => {
    const keyTargets = {
      ArrowDown: (currentIndex() + 1) % tabs.length,
      ArrowUp: (currentIndex() - 1 + tabs.length) % tabs.length,
      Home: 0,
      End: tabs.length - 1,
    };
    const next = keyTargets[event.key];
    if (next === undefined) return;
    event.preventDefault();
    tabs[next].focus();
    activate(tabs[next].dataset.target, { historyMode: "push" });
  });
  document.querySelectorAll("[data-subtabs]").forEach((list) => {
    list.addEventListener("click", (event) => {
      const button = event.target.closest("[data-subtab-target]");
      if (button)
        activateSubpanel(list.dataset.subtabs, button.dataset.subtabTarget);
    });
  });
  railToggle.addEventListener("click", () => {
    setRailCollapsed(!appBody.classList.contains("is-rail-collapsed"));
  });
  scopeButton.addEventListener("click", () => {
    const opening = scopeDrawer.hidden;
    scopeDrawer.hidden = !opening;
    scopeButton.setAttribute("aria-expanded", String(opening));
  });
  document
    .querySelector('[data-action="reset"]')
    .addEventListener("click", resetDashboard);
  controls.forEach((control, name) => {
    control.addEventListener("change", () => {
      if (["source", "comparison_mode"].includes(name))
        controls.get("horizon").value = "";
      if (name === "target_start") {
        const end = controls.get("target_end");
        if (control.value > end.value) end.value = control.value;
      } else if (name === "target_end") {
        const start = controls.get("target_start");
        if (control.value < start.value) start.value = control.value;
      }
      if (name.endsWith("_kind") && currentPayload) {
        const prefix = name.replace("_kind", "");
        populateVintageValue(
          prefix,
          control.value,
          null,
          currentPayload.options,
        );
      }
      scheduleRefresh();
    });
  });
  document
    .querySelectorAll("[data-metric-selector]")
    .forEach((select) =>
      select.addEventListener(
        "change",
        () => currentPayload && renderTrends(currentPayload),
      ),
    );
  document
    .querySelector("[data-exception-search]")
    .addEventListener("input", renderExceptionRows);
  document
    .querySelector("[data-exception-limit]")
    .addEventListener("change", renderExceptionRows);
  document
    .querySelector('[data-product-control="parent"]')
    .addEventListener("change", () => {
      document.querySelector('[data-product-control="month"]').value = "";
      refreshProduct();
    });
  document
    .querySelector('[data-product-control="month"]')
    .addEventListener("change", refreshProduct);
  document.addEventListener("click", (event) => {
    const exportButton = event.target.closest("[data-export-kind]");
    if (exportButton) exportCsv(exportButton);
    const modeButton = event.target.closest("[data-mode-action]");
    if (modeButton?.dataset.modeAction === "comparison") {
      controls.get("comparison_mode").value = "true";
      scheduleRefresh();
    } else if (modeButton?.dataset.modeAction === "single") {
      controls.get("comparison_mode").value = "false";
      scheduleRefresh();
    } else if (modeButton?.dataset.modeAction === "filters") {
      scopeDrawer.hidden = false;
      scopeButton.setAttribute("aria-expanded", "true");
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !scopeDrawer.hidden) {
      closeScopeDrawer();
      scopeButton.focus();
    }
  });
  window.addEventListener("hashchange", () => {
    const id = location.hash.slice(1);
    if (validTabs.has(id)) activate(id, { historyMode: "none" });
  });

  async function start() {
    initializeRail();
    const initial = location.hash.slice(1);
    activate(validTabs.has(initial) ? initial : "overview");
    setLoading(true, "Loading canonical forecast dataset");
    try {
      const payload = await jsonRequest("api/bootstrap");
      defaults = payload.defaults;
      currentPayload = payload;
      currentRequest = payload.request;
      syncControls(payload);
      render(payload);
    } catch (error) {
      showToast(error.message, true);
      renderError(error.message);
    } finally {
      setLoading(false);
    }
  }

  start();
})();
