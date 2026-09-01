/* Forecast performance · canonical real-data browser adapter */
(() => {
  const appBody = document.querySelector(".body");
  const workspace = document.querySelector(".workspace");
  const overviewDetails = document.querySelector(".overview-details");
  const rail = document.querySelector('[role="tablist"][aria-orientation]');
  const railToggle = document.querySelector('[data-action="rail"]');
  const tabs = Array.from(rail.querySelectorAll(':scope [role="tab"]'));
  const panes = Array.from(
    document.querySelectorAll('.stage > [role="tabpanel"]'),
  );
  const validTabs = new Set(tabs.map((tab) => tab.dataset.target));
  const scopeButton = document.querySelector('[data-action="scope"]');
  const scopeDrawer = document.querySelector("#scope-drawer");
  const chartDialog = document.querySelector("#overview-chart-dialog");
  const chartDialogBody = chartDialog.querySelector(
    "[data-overview-chart-fullscreen]",
  );
  const chartDialogTitle = chartDialog.querySelector(
    "#overview-chart-dialog-title",
  );
  const chartDialogLegend = chartDialog.querySelector(
    "[data-chart-dialog-legend]",
  );
  const chartDialogClose = chartDialog.querySelector(
    '[data-action="overview-fullscreen-close"]',
  );
  const fullscreenFilters = chartDialog.querySelector(
    '[data-action="fullscreen-filters"]',
  );
  const controls = new Map(
    Array.from(document.querySelectorAll("[data-control]")).map((control) => [
      control.dataset.control,
      control,
    ]),
  );
  const timeline = document.querySelector("[data-timeline-control]");
  const timelineStartSlider = timeline?.querySelector(
    "[data-timeline-start-slider]",
  );
  const timelineEndSlider = timeline?.querySelector(
    "[data-timeline-end-slider]",
  );
  const timelineRail = timeline?.querySelector("[data-timeline-rail]");
  const timelineSelection = timeline?.querySelector(
    "[data-timeline-selection]",
  );
  const timelineState = { grain: "month" };
  let timelineWindowDrag = null;
  const toast = document.querySelector(".toast");
  const loading = document.querySelector(".loading");
  const stage = document.querySelector(".stage");
  const chartTooltip = document.createElement("div");
  chartTooltip.className = "chart-tooltip";
  chartTooltip.setAttribute("role", "tooltip");
  chartTooltip.hidden = true;
  document.body.append(chartTooltip);
  const revisionDrilldownPopover = document.createElement("div");
  revisionDrilldownPopover.className = "revision-drilldown-popover";
  revisionDrilldownPopover.setAttribute("role", "dialog");
  revisionDrilldownPopover.setAttribute("aria-modal", "false");
  revisionDrilldownPopover.hidden = true;
  document.body.append(revisionDrilldownPopover);
  const INPUT_DEBOUNCE_MS = 160;
  const OVERVIEW_VOLUME_Y_MIN_KL = 1600;
  const OVERVIEW_VOLUME_Y_MAX_KL = 4500;
  const moduleStates = new Map();
  const moduleRequests = new Map();
  const optionSignatures = new Map();
  let toastTimer;
  let refreshTimer;
  let requestGeneration = 0;
  let compactController = null;
  let compactRequestKey = null;
  let defaults = null;
  let currentPayload = null;
  let currentRequest = null;
  let fullscreenChart = null;
  let fullscreenTrigger = null;
  let revisionQueueSource = null;
  let revisionQueueRows = [];
  let revisionQueueSearch = "";
  let revisionQueueSort = { key: "impact_kl", direction: "desc" };
  let overviewResizeFrame = null;
  let overviewResizeObserver = null;
  let revisionScatterMode = "uniform";
  let revisionScatterDensity = true;
  let revisionScatterFocus = "all";
  let revisionScatterSkuClass = "all";
  let revisionScatterZoom = 1;
  let revisionScatterSelection = new Set();
  let revisionScatterPan = { x: 0, y: 0 };
  let scatterDrag = null;
  let revisionDrilldownBasePayload = null;
  let revisionDrilldownPayload = null;
  let revisionDrilldownBaseKey = null;
  let revisionDrilldownController = null;
  let revisionDrilldownOpenCategory = null;
  let revisionDrilldownTrigger = null;

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
  const signedPct = (value, digits = 1) =>
    finite(value) ? `${value > 0 ? "+" : ""}${number(value, digits)}%` : "—";
  const monthLabel = (value, short = true) => {
    if (!value) return "—";
    const date = new Date(`${value}T00:00:00Z`);
    return new Intl.DateTimeFormat("en-US", {
      month: short ? "short" : "long",
      year: "numeric",
      timeZone: "UTC",
    }).format(date);
  };
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
  const metricValue = (value, metric, digits = 1) => {
    if (!finite(value)) return "—";
    if (metric.includes("pct")) return `${number(value, digits)}%`;
    if (metric.endsWith("_pp")) return `${number(value, digits)} pp`;
    if (metric.includes("kl")) return `${number(value, digits)} KL`;
    return number(value, digits);
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
  const requestKey = (request) => {
    if (Array.isArray(request)) return `[${request.map(requestKey).join(",")}]`;
    if (request && typeof request === "object")
      return `{${Object.keys(request)
        .sort()
        .map((key) => `${JSON.stringify(key)}:${requestKey(request[key])}`)
        .join(",")}}`;
    return JSON.stringify(request);
  };
  const isAbortError = (error) => error?.name === "AbortError";
  const activeTabId = () =>
    tabs.find((tab) => tab.getAttribute("aria-selected") === "true")?.dataset
      .target || "overview";

  function activeSubpanel(group) {
    return document.querySelector(
      `[data-subtabs="${group}"] [data-subtab-target][aria-pressed="true"]`,
    )?.dataset.subtabTarget;
  }

  function modulesForView(tabId = activeTabId()) {
    if (tabId === "trends") return ["trends", "heatmap"];
    if (tabId === "comparison")
      return activeSubpanel("comparison") === "sources"
        ? ["comparison"]
        : ["exceptions"];
    if (tabId === "history")
      return activeSubpanel("history") === "exceptions"
        ? ["exceptions"]
        : ["product"];
    if (tabId === "quality") return ["quality"];
    return [];
  }

  function setHtml(element, markup) {
    const documentFragment = new DOMParser().parseFromString(
      `<body>${markup}</body>`,
      "text/html",
    );
    element.replaceChildren(...documentFragment.body.childNodes);
  }

  function positionChartTooltip(event, point) {
    const pointRect = point.getBoundingClientRect();
    const anchorX = finite(event?.clientX)
      ? event.clientX
      : pointRect.left + pointRect.width / 2;
    const anchorY = finite(event?.clientY)
      ? event.clientY
      : pointRect.top + pointRect.height / 2;
    const gap = 14;
    const margin = 10;
    const tooltipRect = chartTooltip.getBoundingClientRect();
    let left = anchorX + gap;
    let top = anchorY + gap;
    if (left + tooltipRect.width > innerWidth - margin)
      left = anchorX - tooltipRect.width - gap;
    if (top + tooltipRect.height > innerHeight - margin)
      top = anchorY - tooltipRect.height - gap;
    chartTooltip.style.left = `${Math.max(margin, left)}px`;
    chartTooltip.style.top = `${Math.max(margin, top)}px`;
  }

  function showChartTooltip(point, event) {
    const isMonthlySummary = point.classList.contains("chart__month-hit");
    const isVolumeSummary = point.dataset.tooltipKind === "volume";
    const isRevisionPoint = point.dataset.tooltipKind === "revision";
    const isRevisionHistoryPoint =
      point.dataset.tooltipKind === "revision-history";
    const isRevisionHistorySegment =
      point.dataset.tooltipKind === "revision-history-segment";
    const isRevisionActionSparkline =
      point.dataset.tooltipKind === "revision-action-sparkline";
    const monthlyContent = isVolumeSummary
      ? `<div class="chart-tooltip__head"><strong>${escapeHtml(point.dataset.tooltipMonth)}</strong><span>${escapeHtml(point.dataset.tooltipSource)}</span></div><dl><div><dt>Vintage A forecast</dt><dd>${escapeHtml(point.dataset.tooltipVintageA)}</dd></div><div><dt>Vintage B forecast</dt><dd>${escapeHtml(point.dataset.tooltipVintageB)}</dd></div><div><dt>Actual</dt><dd>${escapeHtml(point.dataset.tooltipActual)}</dd></div><div><dt>B − actual</dt><dd>${escapeHtml(point.dataset.tooltipVariance)}</dd></div></dl>`
      : `<div class="chart-tooltip__head"><strong>${escapeHtml(point.dataset.tooltipMonth)}</strong><span>${escapeHtml(point.dataset.tooltipSource)}</span></div><dl><div><dt>Vintage A accuracy</dt><dd>${escapeHtml(point.dataset.tooltipVintageA)}</dd></div><div><dt>Vintage B accuracy</dt><dd>${escapeHtml(point.dataset.tooltipVintageB)}</dd></div><div><dt>Vintage B bias</dt><dd class="${Number(point.dataset.tooltipBiasRaw) >= 0 ? "chart-tooltip__over" : "chart-tooltip__under"}">${escapeHtml(point.dataset.tooltipBias)}</dd></div></dl>`;
    const revisionPairContent = `<div class="chart-tooltip__head"><strong>${escapeHtml(point.dataset.tooltipCode)}</strong><span>${escapeHtml(point.dataset.tooltipSource)}</span></div><p class="chart-tooltip__description">${escapeHtml(point.dataset.tooltipDescription)}</p><div class="chart-tooltip__meta"><span>${escapeHtml(point.dataset.tooltipMonth)}</span><span>${escapeHtml(point.dataset.tooltipBrand)}</span><span>${escapeHtml(point.dataset.tooltipDirection)} · ${escapeHtml(point.dataset.tooltipOutcome)}</span></div><dl><div><dt>Actual volume</dt><dd>${escapeHtml(point.dataset.tooltipActual)}</dd></div><div><dt>Vintage A forecast</dt><dd>${escapeHtml(point.dataset.tooltipVintageA)}<small>${escapeHtml(point.dataset.tooltipVintageAScope)}</small></dd></div><div><dt>Vintage B forecast</dt><dd>${escapeHtml(point.dataset.tooltipVintageB)}<small>${escapeHtml(point.dataset.tooltipVintageBScope)}</small></dd></div><div><dt>Error before revision</dt><dd>${escapeHtml(point.dataset.tooltipErrorA)}</dd></div><div><dt>Error after revision</dt><dd>${escapeHtml(point.dataset.tooltipErrorB)}</dd></div><div><dt>Forecast revision</dt><dd>${escapeHtml(point.dataset.tooltipRevision)}</dd></div><div class="chart-tooltip__result"><dt>Error improvement</dt><dd class="${Number(point.dataset.tooltipImprovementRaw) >= 0 ? "good" : "bad"}">${escapeHtml(point.dataset.tooltipImprovement)}</dd></div></dl>`;
    const revisionScoreContent = `<div class="chart-tooltip__head"><strong>${escapeHtml(point.dataset.tooltipCode)}</strong><span>${escapeHtml(point.dataset.tooltipSource)}</span></div><p class="chart-tooltip__description">${escapeHtml(point.dataset.tooltipDescription)}</p><div class="chart-tooltip__meta"><span>${escapeHtml(point.dataset.tooltipWindow)}</span><span>${escapeHtml(point.dataset.tooltipBrand)}</span><span>SKU class ${escapeHtml(point.dataset.tooltipSkuClass)}</span><span>${escapeHtml(point.dataset.tooltipDirection)} · ${escapeHtml(point.dataset.tooltipOutcome)}</span></div><dl><div><dt>Six-month actual volume</dt><dd>${escapeHtml(point.dataset.tooltipActual)}</dd></div><div><dt>Evidence window</dt><dd>${escapeHtml(point.dataset.tooltipMonths)} target months<small>${escapeHtml(point.dataset.tooltipVintages)} vintages per month · ${escapeHtml(point.dataset.tooltipTransitions)} vintage changes</small></dd></div><div><dt>Improving months</dt><dd>${escapeHtml(point.dataset.tooltipImproving)}<small>${escapeHtml(point.dataset.tooltipDegrading)} degrading · ${escapeHtml(point.dataset.tooltipNeutral)} neutral</small></dd></div><div><dt>Forecast trend</dt><dd>${escapeHtml(point.dataset.tooltipRevision)}<small>median monthly trend · % of actual per vintage</small></dd></div><div class="chart-tooltip__result"><dt>Vintage improvement score</dt><dd class="${Number(point.dataset.tooltipImprovementRaw) >= 0 ? "good" : "bad"}">${escapeHtml(point.dataset.tooltipImprovement)}<small>median monthly FA change · pp per vintage</small></dd></div></dl>`;
    const revisionContent =
      point.dataset.tooltipScoreMode === "vintage-window"
        ? revisionScoreContent
        : revisionPairContent;
    const revisionHistoryContent = `<div class="chart-tooltip__head"><strong>${escapeHtml(point.dataset.tooltipMonth)}</strong><span>${escapeHtml(point.dataset.tooltipSource)}</span></div><p>Oldest → latest forecast version</p><dl><div><dt>Net FA vs oldest</dt><dd class="${Number(point.dataset.tooltipNetFaRaw) >= 0 ? "good" : "bad"}">${escapeHtml(point.dataset.tooltipNetFa)}</dd></div><div><dt>Net error improvement</dt><dd>${escapeHtml(point.dataset.tooltipNetErrorImprovement)}</dd></div><div><dt>Delta vs oldest</dt><dd>${escapeHtml(point.dataset.tooltipDelta)}</dd></div><div><dt>Forecast accuracy</dt><dd>${escapeHtml(point.dataset.tooltipOldestAccuracy)}<small>to ${escapeHtml(point.dataset.tooltipLatestAccuracy)}</small></dd></div><div><dt>Forecast volume</dt><dd>${escapeHtml(point.dataset.tooltipOldestForecast)}<small>to ${escapeHtml(point.dataset.tooltipLatestForecast)}</small></dd></div><div><dt>Forecast versions</dt><dd>${escapeHtml(point.dataset.tooltipVintages)}</dd></div><div><dt>Fixed cohort</dt><dd>${escapeHtml(point.dataset.tooltipProducts)} products</dd></div><div><dt>Version range</dt><dd>${escapeHtml(point.dataset.tooltipOldestVersion)}<small>to ${escapeHtml(point.dataset.tooltipLatestVersion)}</small></dd></div></dl>`;
    const revisionHistorySegmentContent = `<div class="chart-tooltip__head"><strong>${escapeHtml(point.dataset.tooltipMonth)}</strong><span>${escapeHtml(point.dataset.tooltipSource)}</span></div><p>${escapeHtml(point.dataset.tooltipPreviousVersion)} → ${escapeHtml(point.dataset.tooltipVersion)}</p><div class="chart-tooltip__meta"><span>${escapeHtml(point.dataset.tooltipOutcome)} FA</span></div><dl><div><dt>FA change</dt><dd class="${Number(point.dataset.tooltipFaRaw) >= 0 ? "good" : "bad"}">${escapeHtml(point.dataset.tooltipFa)}</dd></div><div><dt>Error improvement</dt><dd>${escapeHtml(point.dataset.tooltipErrorImprovement)}</dd></div><div><dt>Absolute error</dt><dd>${escapeHtml(point.dataset.tooltipPreviousError)}<small>to ${escapeHtml(point.dataset.tooltipError)}</small></dd></div><div><dt>Forecast revision</dt><dd>${escapeHtml(point.dataset.tooltipRevision)}</dd></div><div><dt>Forecast volume</dt><dd>${escapeHtml(point.dataset.tooltipPreviousForecast)}<small>to ${escapeHtml(point.dataset.tooltipForecast)}</small></dd></div></dl>`;
    const revisionActionSparklineContent = `<div class="chart-tooltip__head"><strong>${escapeHtml(point.dataset.tooltipCode)}</strong><span>${escapeHtml(point.dataset.tooltipSource)}</span></div><p>${escapeHtml(point.dataset.tooltipMonth)} · monthly error improvement</p><dl><div><dt>Error improvement</dt><dd class="${Number(point.dataset.tooltipImprovementRaw) >= 0 ? "good" : "bad"}">${escapeHtml(point.dataset.tooltipImprovement)}</dd></div><div><dt>Actual volume</dt><dd>${escapeHtml(point.dataset.tooltipActual)}</dd></div><div><dt>Forecast revision</dt><dd>${escapeHtml(point.dataset.tooltipRevision)}</dd></div><div><dt>Outcome</dt><dd>${escapeHtml(point.dataset.tooltipOutcome)}</dd></div></dl>`;
    const content = isRevisionActionSparkline
      ? revisionActionSparklineContent
      : isRevisionPoint
        ? revisionContent
        : isRevisionHistorySegment
          ? revisionHistorySegmentContent
          : isRevisionHistoryPoint
            ? revisionHistoryContent
            : isMonthlySummary
              ? monthlyContent
              : `<div class="chart-tooltip__head"><strong>${escapeHtml(point.dataset.tooltipMetric)}</strong><span>${escapeHtml(point.dataset.tooltipSource)}</span></div><p>${escapeHtml(point.dataset.tooltipMonth)}</p><dl><div><dt>Value</dt><dd>${escapeHtml(point.dataset.tooltipValue)}</dd></div><div><dt>Actual volume</dt><dd>${escapeHtml(point.dataset.tooltipActual)}</dd></div><div><dt>Forecast volume</dt><dd>${escapeHtml(point.dataset.tooltipForecast)}</dd></div><div><dt>Eligible observations</dt><dd>${escapeHtml(point.dataset.tooltipObservations)}</dd></div></dl>`;
    chartTooltip.classList.toggle(
      "chart-tooltip--revision",
      isRevisionPoint ||
        isRevisionHistoryPoint ||
        isRevisionHistorySegment ||
        isRevisionActionSparkline,
    );
    setHtml(chartTooltip, content);
    chartTooltip.hidden = false;
    point.setAttribute("aria-describedby", "active-chart-tooltip");
    chartTooltip.id = "active-chart-tooltip";
    positionChartTooltip(event, point);
  }

  function hideChartTooltip(point = null) {
    point?.removeAttribute("aria-describedby");
    chartTooltip.hidden = true;
    chartTooltip.removeAttribute("id");
  }

  function activeRevisionPayload() {
    return (
      revisionDrilldownPayload || revisionDrilldownBasePayload || currentPayload
    );
  }

  function closeRevisionDrilldown({ restoreFocus = false } = {}) {
    revisionDrilldownTrigger?.setAttribute("aria-expanded", "false");
    revisionDrilldownPopover.hidden = true;
    revisionDrilldownOpenCategory = null;
    const trigger = revisionDrilldownTrigger;
    revisionDrilldownTrigger = null;
    if (restoreFocus) trigger?.focus();
  }

  function positionRevisionDrilldown(trigger) {
    const triggerRect = trigger.getBoundingClientRect();
    const popoverRect = revisionDrilldownPopover.getBoundingClientRect();
    const margin = 10;
    const gap = 8;
    let left = triggerRect.left;
    let top = triggerRect.bottom + gap;
    if (left + popoverRect.width > innerWidth - margin)
      left = innerWidth - popoverRect.width - margin;
    if (top + popoverRect.height > innerHeight - margin)
      top = triggerRect.top - popoverRect.height - gap;
    revisionDrilldownPopover.style.left = `${Math.max(margin, left)}px`;
    revisionDrilldownPopover.style.top = `${Math.max(margin, top)}px`;
  }

  function revisionDrilldownTable(category, detail) {
    const selected = revisionScatterSelection;
    const rows = detail?.rows || [];
    const body = rows.length
      ? rows
          .map(
            (row) =>
              `<button class="revision-drilldown-row${selected.has(String(row.parent_code)) ? " is-selected" : ""}" type="button" role="row" data-drilldown-parent-code="${escapeHtml(row.parent_code)}" aria-pressed="${selected.has(String(row.parent_code))}"><span role="cell"><b>${escapeHtml(row.parent_code)}</b><small title="${escapeHtml(row.parent_description || "Description unavailable")}">${escapeHtml(row.parent_description || "Description unavailable")}</small></span><span role="cell">${count(row.observations)}</span><span role="cell">${kl(row.actual_kl)}</span><span role="cell">${kl(row.absolute_error_kl)}</span><span role="cell" class="${row.net_error_improvement_kl >= 0 ? "good" : "bad"}">${signedKl(row.net_error_improvement_kl)}</span></button>`,
          )
          .join("")
      : '<p class="revision-drilldown-empty">No parent codes in this outcome.</p>';
    return `<header class="revision-drilldown-popover__head"><div><span>Top ${count(detail?.rows?.length || 0)} of ${count(detail?.total_parents || 0)}</span><strong>${escapeHtml(labelize(category))} parent codes</strong><small>Ranked by error impact · click to focus · Shift-click to add</small></div><button type="button" data-drilldown-close aria-label="Close ${escapeHtml(category)} drill-down">×</button></header><div class="revision-drilldown-table" role="table" aria-label="Top ${escapeHtml(category)} parent codes"><div class="revision-drilldown-head" role="row"><span role="columnheader">Parent</span><span role="columnheader">Obs</span><span role="columnheader">Actual</span><span role="columnheader">Abs error</span><span role="columnheader">Net impact</span></div>${body}</div>`;
  }

  function refreshRevisionDrilldownPopover() {
    if (revisionDrilldownPopover.hidden || !revisionDrilldownOpenCategory)
      return;
    const detail =
      revisionDrilldownBasePayload?.revision_drilldown?.categories?.[
        revisionDrilldownOpenCategory
      ];
    setHtml(
      revisionDrilldownPopover,
      revisionDrilldownTable(revisionDrilldownOpenCategory, detail),
    );
    if (revisionDrilldownTrigger)
      positionRevisionDrilldown(revisionDrilldownTrigger);
  }

  function openRevisionDrilldown(category, trigger) {
    const detail =
      revisionDrilldownBasePayload?.revision_drilldown?.categories?.[category];
    if (!detail) return;
    if (
      revisionDrilldownOpenCategory === category &&
      !revisionDrilldownPopover.hidden
    ) {
      closeRevisionDrilldown({ restoreFocus: true });
      return;
    }
    revisionDrilldownTrigger?.setAttribute("aria-expanded", "false");
    revisionDrilldownOpenCategory = category;
    revisionDrilldownTrigger = trigger;
    trigger.setAttribute("aria-expanded", "true");
    revisionDrilldownPopover.setAttribute(
      "aria-label",
      `${labelize(category)} parent-code drill-down`,
    );
    setHtml(revisionDrilldownPopover, revisionDrilldownTable(category, detail));
    revisionDrilldownPopover.hidden = false;
    positionRevisionDrilldown(trigger);
  }

  function resetRevisionDrilldown(basePayload = null) {
    revisionDrilldownController?.abort();
    revisionDrilldownController = null;
    revisionDrilldownBasePayload = basePayload;
    revisionDrilldownPayload = null;
    revisionScatterSelection = new Set();
    closeRevisionDrilldown();
  }

  async function refreshRevisionDrilldown() {
    if (!revisionDrilldownBasePayload || !currentRequest) return;
    revisionDrilldownController?.abort();
    if (!revisionScatterSelection.size) {
      revisionDrilldownController = null;
      revisionDrilldownPayload = null;
      renderRevisionPanel(revisionDrilldownBasePayload);
      if (
        fullscreenChart === "revision" ||
        fullscreenChart === "revision-history"
      )
        renderFullscreenChart();
      return;
    }
    const controller = new AbortController();
    revisionDrilldownController = controller;
    const parentCodes = [...revisionScatterSelection]
      .map(Number)
      .filter(Number.isFinite);
    const request = {
      ...currentRequest,
      drilldown_parent_codes: parentCodes,
    };
    document
      .querySelector("[data-revision-panel]")
      ?.setAttribute("aria-busy", "true");
    try {
      const response = await jsonRequest("api/module/exceptions", {
        method: "POST",
        body: JSON.stringify(request),
        signal: controller.signal,
      });
      if (controller !== revisionDrilldownController) return;
      if (
        response?.contract?.name !== "dashboard-module" ||
        response.module !== "exceptions" ||
        response.meta?.dataset_version !== currentPayload?.meta?.dataset_version
      )
        throw new Error("Unsupported revision drill-down response");
      revisionDrilldownPayload = {
        ...revisionDrilldownBasePayload,
        ...response.data,
        request: revisionDrilldownBasePayload.request,
        revision_drilldown: revisionDrilldownBasePayload.revision_drilldown,
      };
      renderRevisionPanel(revisionDrilldownPayload);
      if (
        fullscreenChart === "revision" ||
        fullscreenChart === "revision-history"
      )
        renderFullscreenChart();
    } catch (error) {
      if (!isAbortError(error)) showToast(error.message, true);
    } finally {
      if (controller === revisionDrilldownController)
        revisionDrilldownController = null;
      document
        .querySelector("[data-revision-panel]")
        ?.setAttribute("aria-busy", "false");
    }
  }

  function updateRevisionParentSelection(parentCode, additive = false) {
    const key = String(parentCode);
    const wasSelected = revisionScatterSelection.has(key);
    if (!additive) revisionScatterSelection.clear();
    if (!wasSelected || !additive) revisionScatterSelection.add(key);
    else revisionScatterSelection.delete(key);
    refreshRevisionDrilldownPopover();
    void refreshRevisionDrilldown();
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

  function setScopeDrawerOpen(open, trigger = scopeButton) {
    scopeDrawer.hidden = !open;
    scopeButton.setAttribute("aria-expanded", String(open));
    fullscreenFilters.setAttribute("aria-expanded", String(open));
    if (open && !chartDialog.hidden) chartDialog.append(scopeDrawer);
    else if (
      !open &&
      scopeDrawer.parentElement !== document.querySelector(".workspace")
    )
      document.querySelector(".workspace").prepend(scopeDrawer);
    if (!open) trigger?.focus();
  }

  function closeScopeDrawer({ restoreFocus = false } = {}) {
    const trigger = chartDialog.hidden ? scopeButton : fullscreenFilters;
    setScopeDrawerOpen(false, restoreFocus ? trigger : null);
  }

  const chartDialogContent = {
    accuracy: {
      title: "Monthly vintage accuracy and bias",
      legend:
        '<span><i class="key key--vintage-b"></i>Vintage B</span><span><i class="key key--vintage-a"></i>Vintage A</span><span><i class="key key--bias-over"></i>Over bias</span><span><i class="key key--bias-under"></i>Under bias</span>',
      render: overviewPerformanceChart,
    },
    volume: {
      title: "Forecast versus actual volume",
      legend:
        '<span><i class="key key--volume-vintage-b"></i>Vintage B</span><span><i class="key key--volume-vintage-a"></i>Vintage A</span><span><i class="key key--volume-actual"></i>Actual</span>',
      render: overviewVolumeChart,
    },
    revision: {
      title: (payload) =>
        `Parent vintage trend vs improvement score · ${payload.request.source.toUpperCase()}`,
      legend: "",
      renderPayload: (payload) => {
        const source = payload.request.source;
        const rows = scatterRowsForSource(payload, source);
        return scatterChart(
          rows,
          "revision_score_pct",
          "vintage_improvement_score_pp",
          `${source.toUpperCase()} parent vintage trend versus improvement score`,
          {
            source,
            tolerance: payload.request.revision_tolerance_kl,
          },
        );
      },
    },
    "revision-history": {
      title: (payload) =>
        `Forecast revision paths · ${payload.request.source.toUpperCase()}`,
      legend: "",
      renderPayload: (payload) =>
        revisionHistoryChart(payload.revision_history),
    },
  };

  function renderFullscreenChart() {
    if (!fullscreenChart || !currentPayload) return;
    const fullscreenPayload =
      fullscreenChart === "revision" || fullscreenChart === "revision-history"
        ? activeRevisionPayload()
        : currentPayload;
    const config = chartDialogContent[fullscreenChart];
    if (!config) return;
    chartDialog.dataset.chartKind = fullscreenChart;
    chartDialogTitle.textContent =
      typeof config.title === "function"
        ? config.title(fullscreenPayload)
        : config.title;
    const legend =
      typeof config.legend === "function"
        ? config.legend(fullscreenPayload)
        : config.legend;
    setHtml(chartDialogLegend, legend || "");
    const content = config.renderPayload
      ? config.renderPayload(fullscreenPayload)
      : config.render(fullscreenPayload.monthly_performance?.rows || [], {
          height: overviewChartHeight(chartDialogBody),
        });
    setHtml(chartDialogBody, content);
    if (fullscreenChart === "revision") refreshScatterCharts();
  }

  function openChartDialog(kind, trigger) {
    closeScopeDrawer();
    fullscreenChart = kind;
    fullscreenTrigger = trigger;
    chartDialog.hidden = false;
    document.body.classList.add("has-chart-dialog");
    renderFullscreenChart();
    chartDialogClose.focus();
  }

  function closeChartDialog() {
    if (chartDialog.hidden) return;
    closeScopeDrawer();
    chartDialog.hidden = true;
    chartDialog.removeAttribute("data-chart-kind");
    setHtml(chartDialogBody, "");
    setHtml(chartDialogLegend, "");
    document.body.classList.remove("has-chart-dialog");
    fullscreenChart = null;
    fullscreenTrigger?.focus();
    fullscreenTrigger = null;
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
    workspace.classList.toggle("is-overview", id === "overview");
    if (id !== "overview") overviewDetails.open = false;
    if (location.hash !== `#${id}`) {
      if (historyMode === "push") history.pushState(null, "", `#${id}`);
      else if (historyMode === "replace")
        history.replaceState(null, "", `#${id}`);
    }
    closeScopeDrawer();
    const activeModules = new Set(modulesForView(id));
    moduleRequests.forEach(({ controller, key }, moduleName) => {
      if (!activeModules.has(moduleName)) {
        controller.abort();
        moduleRequests.delete(moduleName);
        moduleStates.set(moduleName, { key, status: "stale" });
        setModuleStatus(moduleName);
      }
    });
    if (currentPayload) {
      if (id === "overview") renderOverview(currentPayload);
      void ensureActiveModules(id);
    }
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
    scheduleOverviewChartRender();
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
    const owner = {
      comparison: "comparison",
      history: "history",
      quality: "quality",
    }[group];
    if (owner && activeTabId() === owner && currentPayload)
      void ensureActiveModules(owner);
  }

  function option(value, label, selectedValue) {
    return `<option value="${escapeHtml(value ?? "")}"${String(value ?? "") === String(selectedValue ?? "") ? " selected" : ""}>${escapeHtml(label)}</option>`;
  }

  function populateSelect(name, entries, selected, allLabel = null) {
    const control = controls.get(name);
    if (!control) return;
    const signature = JSON.stringify({ entries, allLabel });
    if (optionSignatures.get(name) !== signature) {
      const values = [];
      if (allLabel !== null) values.push(option("", allLabel, selected));
      entries.forEach((entry) =>
        values.push(option(entry.value, entry.label, selected)),
      );
      setHtml(control, values.join(""));
      optionSignatures.set(name, signature);
    }
    control.value = String(selected ?? "");
  }

  function timelineAxisMarkup(available) {
    if (!available.length) return "";
    const lastIndex = available.length - 1;
    const candidates = available
      .map((value, index) => ({ value, index }))
      .filter(({ value, index }) => {
        if (index === 0 || index === lastIndex) return true;
        const month = Number(value.slice(5, 7));
        return timelineState.grain === "quarter"
          ? [1, 4, 7, 10].includes(month)
          : month === 1;
      });
    const labels =
      candidates.length <= 6
        ? candidates
        : candidates.filter(
            (_, index) =>
              index === 0 ||
              index === candidates.length - 1 ||
              index % Math.ceil(candidates.length / 5) === 0,
          );
    return labels
      .map(({ value, index }) => {
        const quarter = ForecastTimeline.quarterLabel(value).split(" ");
        const label =
          timelineState.grain === "quarter"
            ? `${quarter[0]} ’${quarter[1]?.slice(-2)}`
            : monthLabel(value);
        return `<span style="left:${lastIndex ? (index / lastIndex) * 100 : 0}%">${escapeHtml(label)}</span>`;
      })
      .join("");
  }

  function updateTimelineUi(months, start, end) {
    if (!timeline || !timelineStartSlider || !timelineEndSlider) return;
    const available = ForecastTimeline.normalizeMonths(months);
    const range = ForecastTimeline.clampRange(available, start, end);
    const indices = ForecastTimeline.indexRange(
      available,
      range.start,
      range.end,
    );
    const lastIndex = Math.max(0, available.length - 1);
    for (const slider of [timelineStartSlider, timelineEndSlider]) {
      slider.min = "0";
      slider.max = String(lastIndex);
      slider.disabled = available.length < 2;
    }
    timelineStartSlider.value = String(indices.start);
    timelineStartSlider.setAttribute(
      "aria-valuetext",
      monthLabel(range.start, false),
    );
    timelineEndSlider.value = String(indices.end);
    timelineEndSlider.setAttribute(
      "aria-valuetext",
      monthLabel(range.end, false),
    );
    const startPct = lastIndex ? (indices.start / lastIndex) * 100 : 0;
    const endPct = lastIndex ? (indices.end / lastIndex) * 100 : 100;
    timelineRail?.style.setProperty("--start-pct", `${startPct}%`);
    timelineRail?.style.setProperty("--end-pct", `${endPct}%`);
    timelineRail?.classList.toggle(
      "is-tight",
      indices.end - indices.start <= 1,
    );
    timelineSelection?.setAttribute("aria-valuemin", "0");
    timelineSelection?.setAttribute("aria-valuemax", String(lastIndex));
    timelineSelection?.setAttribute("aria-valuenow", String(indices.start));
    timelineSelection?.setAttribute(
      "aria-valuetext",
      `${monthLabel(range.start, false)} through ${monthLabel(range.end, false)}`,
    );
    timeline.querySelector("[data-timeline-start]").textContent = monthLabel(
      range.start,
      false,
    );
    timeline.querySelector("[data-timeline-end]").textContent = monthLabel(
      range.end,
      false,
    );
    const count = ForecastTimeline.inclusiveMonthCount(range.start, range.end);
    timeline.querySelector("[data-timeline-summary]").textContent =
      `${count} month${count === 1 ? "" : "s"}`;
    timeline.querySelectorAll("[data-timeline-grain]").forEach((button) => {
      const selected = button.dataset.timelineGrain === timelineState.grain;
      button.classList.toggle("is-active", selected);
      button.setAttribute("aria-pressed", String(selected));
    });
    const isAll =
      range.start === available[0] && range.end === available.at(-1);
    const matched = ForecastTimeline.matchingPreset(
      available,
      range.start,
      range.end,
      timelineState.grain,
      [3, 6, 12, 24],
    );
    timeline.querySelectorAll("[data-timeline-months]").forEach((button) => {
      const value = button.dataset.timelineMonths;
      const duration = Number(value);
      const selected = value === "all" ? isAll : matched === duration;
      button.classList.toggle("is-active", selected);
      button.setAttribute("aria-pressed", String(selected));
      button.disabled =
        value !== "all" &&
        ForecastTimeline.inclusiveMonthCount(available[0], available.at(-1)) <
          duration;
      button.textContent =
        value === "all"
          ? "All"
          : timelineState.grain === "quarter"
            ? `${duration / 3}Q`
            : `${duration}M`;
    });
    setHtml(
      timeline.querySelector("[data-timeline-axis]"),
      timelineAxisMarkup(available),
    );
    const startMonth = Number(range.start?.slice(5, 7));
    const endMonth = Number(range.end?.slice(5, 7));
    const partialQuarter =
      timelineState.grain === "quarter" &&
      (![1, 4, 7, 10].includes(startMonth) ||
        ![3, 6, 9, 12].includes(endMonth));
    timeline.querySelector("[data-timeline-hint]").textContent = partialQuarter
      ? `Monthly precision retained · partial ${ForecastTimeline.quarterLabel(range.start)} to partial ${ForecastTimeline.quarterLabel(range.end)}`
      : "Drag either end, or move the highlighted window. Presets reposition both ends.";
  }

  function setTimelineRange(months, start, end) {
    const range = ForecastTimeline.clampRange(months, start, end);
    controls.get("target_start").value = range.start ?? "";
    controls.get("target_end").value = range.end ?? "";
    updateTimelineUi(months, range.start, range.end);
  }

  function syncTimelineFromRequest(options, request) {
    updateTimelineUi(
      options.target_months || [],
      request.target_start,
      request.target_end,
    );
  }

  function applyTimelinePreset(months, value) {
    const available = ForecastTimeline.normalizeMonths(months);
    const range =
      value === "all"
        ? { start: available[0], end: available.at(-1) }
        : ForecastTimeline.rangeForPreset(
            available,
            Number(value),
            timelineState.grain,
            controls.get("target_end").value,
          );
    setTimelineRange(available, range.start, range.end);
  }

  function populateVintageValue(prefix, selectedKind, selectedValue, options) {
    const control = controls.get(`${prefix}_value`);
    if (!control) return;
    let entries = [{ value: "", label: "Not required" }];
    let disabled = true;
    if (selectedKind === "specific_calculation_month") {
      entries = options.calculation_months.map((value) => ({
        value,
        label: monthLabel(value),
      }));
      disabled = false;
    } else if (selectedKind === "specific_horizon") {
      entries = options.horizons.map((value) => ({
        value,
        label: `M−${value}`,
      }));
      disabled = false;
    }
    const name = `${prefix}_value`;
    const signature = JSON.stringify({ selectedKind, entries });
    if (optionSignatures.get(name) !== signature) {
      setHtml(
        control,
        entries
          .map((entry) => option(entry.value, entry.label, selectedValue))
          .join(""),
      );
      optionSignatures.set(name, signature);
    }
    control.disabled = disabled;
    control.value = disabled
      ? ""
      : String(selectedValue ?? entries[0]?.value ?? "");
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
    syncTimelineFromRequest(options, request);
    populateSelect(
      "brand",
      options.brands.map((value) => ({ value, label: value })),
      request.brand,
      "All brands + quality groups",
    );
    populateSelect(
      "sku_class",
      options.sku_classes.map((value) => ({ value, label: value })),
      request.sku_class,
      "All SKU classes",
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
          "sku_class",
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
      sku_class: value("sku_class") || null,
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
    const label = `Filters · ${active}`;
    scopeButton.textContent = label;
    fullscreenFilters.textContent = label;
  }

  function setUpdating(active, message = "Updating active population…") {
    stage.classList.toggle("is-updating", active);
    stage.setAttribute("aria-busy", String(active));
    document.querySelector("[data-filter-note]").textContent = active
      ? message
      : "Changes apply automatically.";
  }

  function abortModuleRequests() {
    moduleRequests.forEach(({ controller }) => controller.abort());
    moduleRequests.clear();
  }

  function markModulesStale() {
    moduleStates.clear();
    panes
      .filter((item) => item.id !== "pane-overview")
      .forEach((item) => item.classList.add("is-stale"));
    tabs
      .filter((tab) => tab.dataset.target !== "overview")
      .forEach((tab) => tab.classList.add("is-stale"));
  }

  function modulePanes(moduleName) {
    return (
      {
        trends: ["trends"],
        heatmap: ["trends"],
        comparison: ["comparison"],
        exceptions: ["comparison", "history"],
        quality: ["quality"],
        product: ["history"],
      }[moduleName] || []
    );
  }

  function setModuleStatus(moduleName) {
    modulePanes(moduleName).forEach((paneId) => {
      const item = pane(paneId);
      const tab = tabs.find((candidate) => candidate.dataset.target === paneId);
      const required = modulesForView(paneId);
      const allFresh = required.every(
        (name) => moduleStates.get(name)?.status === "fresh",
      );
      const isLoading = required.some(
        (name) => moduleStates.get(name)?.status === "loading",
      );
      item?.classList.toggle("is-module-loading", isLoading);
      item?.classList.toggle("is-stale", !allFresh);
      item?.setAttribute("aria-busy", String(isLoading));
      tab?.classList.toggle("is-stale", !allFresh);
    });
  }

  function validateModulePayload(payload, moduleName, request, generation) {
    if (generation !== requestGeneration) return false;
    if (payload?.contract?.name !== "dashboard-module") return false;
    if (payload.contract.version !== 1 || payload.module !== moduleName)
      return false;
    if (payload.meta?.dataset_version !== currentPayload?.meta?.dataset_version)
      return false;
    const expected = requestKey(request);
    return (
      requestKey(payload.request) === expected &&
      (moduleName === "product" || requestKey(currentRequest) === expected)
    );
  }

  function renderModule(moduleName) {
    if (!currentPayload) return;
    if (moduleName === "trends")
      renderTrends(currentPayload, { heatmap: false });
    else if (moduleName === "heatmap") renderTrendHeatmap(currentPayload);
    else if (moduleName === "comparison" && activeTabId() === "comparison")
      renderSourcePanel(currentPayload);
    else if (moduleName === "exceptions") {
      if (activeTabId() === "comparison") {
        const baseKey = requestKey(currentRequest);
        if (revisionDrilldownBaseKey !== baseKey) {
          revisionDrilldownBaseKey = baseKey;
          resetRevisionDrilldown(currentPayload);
        } else if (!revisionDrilldownBasePayload) {
          revisionDrilldownBasePayload = currentPayload;
        }
        renderRevisionPanel(activeRevisionPayload());
      }
      if (activeTabId() === "history") renderExceptions(currentPayload);
    } else if (moduleName === "quality" && activeTabId() === "quality")
      renderQuality(currentPayload.quality);
    else if (moduleName === "product" && activeTabId() === "history")
      renderProduct(currentPayload.product_detail);
    if (!chartDialog.hidden) renderFullscreenChart();
  }

  async function fetchModule(moduleName, request = currentRequest) {
    if (!currentPayload || !request) return;
    const generation = requestGeneration;
    const key = `${generation}:${requestKey(request)}`;
    const state = moduleStates.get(moduleName);
    if (state?.key === key && state.status === "fresh") {
      renderModule(moduleName);
      setModuleStatus(moduleName);
      return;
    }
    const pending = moduleRequests.get(moduleName);
    if (pending?.key === key) return pending.promise;
    pending?.controller.abort();
    const controller = new AbortController();
    moduleStates.set(moduleName, { key, status: "loading" });
    setModuleStatus(moduleName);
    const promise = jsonRequest(`api/module/${moduleName}`, {
      method: "POST",
      body: JSON.stringify(request),
      signal: controller.signal,
    })
      .then((payload) => {
        const latest = moduleStates.get(moduleName);
        if (latest?.key !== key || latest.status !== "loading") return;
        if (!validateModulePayload(payload, moduleName, request, generation)) {
          moduleStates.set(moduleName, { key, status: "stale" });
          setModuleStatus(moduleName);
          return;
        }
        currentPayload = { ...currentPayload, ...payload.data };
        moduleStates.set(moduleName, { key, status: "fresh" });
        renderModule(moduleName);
        setModuleStatus(moduleName);
      })
      .catch((error) => {
        if (isAbortError(error) || generation !== requestGeneration) return;
        moduleStates.set(moduleName, { key, status: "error" });
        setModuleStatus(moduleName);
        showToast(error.message, true);
      })
      .finally(() => {
        if (moduleRequests.get(moduleName)?.controller === controller)
          moduleRequests.delete(moduleName);
      });
    moduleRequests.set(moduleName, { key, controller, promise });
    return promise;
  }

  async function ensureActiveModules(tabId = activeTabId()) {
    if (!currentRequest || compactController) return;
    const required = modulesForView(tabId);
    if (!required.length) {
      pane(tabId)?.classList.remove("is-stale", "is-module-loading");
      tabs
        .find((tab) => tab.dataset.target === tabId)
        ?.classList.remove("is-stale");
      return;
    }
    await Promise.all(required.map((moduleName) => fetchModule(moduleName)));
  }

  async function refreshView({ announce = false } = {}) {
    clearTimeout(refreshTimer);
    const request = buildRequest();
    const key = requestKey(request);
    if (compactController && compactRequestKey === key) return;
    compactController?.abort();
    abortModuleRequests();
    revisionDrilldownBaseKey = null;
    resetRevisionDrilldown();
    const controller = new AbortController();
    compactController = controller;
    compactRequestKey = key;
    const generation = ++requestGeneration;
    markModulesStale();
    setUpdating(true);
    try {
      const payload = await jsonRequest("api/view/compact", {
        method: "POST",
        body: JSON.stringify(request),
        signal: controller.signal,
      });
      if (generation !== requestGeneration) return;
      if (
        payload?.contract?.name !== "dashboard-view" ||
        payload.contract.version !== 2
      )
        throw new Error("Unsupported compact dashboard response");
      currentPayload = payload;
      currentRequest = payload.request;
      syncControls(payload);
      renderCompact(payload);
      if (compactController === controller) {
        compactController = null;
        compactRequestKey = null;
      }
      if (announce) showToast("Shared population updated");
      void ensureActiveModules();
    } catch (error) {
      if (isAbortError(error) || generation !== requestGeneration) return;
      showToast(error.message, true);
      renderError(error.message);
    } finally {
      if (compactController === controller) {
        compactController = null;
        compactRequestKey = null;
      }
      if (generation === requestGeneration) setUpdating(false);
    }
  }

  function scheduleRefresh({ immediate = false, announce = true } = {}) {
    updateFilterCount();
    clearTimeout(refreshTimer);
    if (immediate) void refreshView({ announce });
    else
      refreshTimer = setTimeout(
        () => void refreshView({ announce }),
        INPUT_DEBOUNCE_MS,
      );
  }

  function renderCompact(payload) {
    hideChartTooltip();
    renderMeta(payload);
    renderState(payload.state);
    renderScope(payload);
    if (activeTabId() === "overview") renderOverview(payload);
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

  function kpiHelp(label, paragraphs) {
    const content = (paragraphs || []).filter(Boolean);
    if (!content.length) return "";
    return `<details class="kpi-help"><summary aria-label="Explain ${escapeHtml(label)}">?</summary><div class="kpi-help__popover" role="note"><strong>${escapeHtml(label)}</strong>${content.map((paragraph) => `<p>${escapeHtml(paragraph)}</p>`).join("")}</div></details>`;
  }

  function kpi(label, value, delta, caption, tone = "", help = []) {
    return `<article class="kpi"><div class="kpi__head"><p class="kpi__label">${escapeHtml(label)}</p>${kpiHelp(label, help)}</div><div class="kpi__line"><strong class="kpi__val">${escapeHtml(value)}</strong><span class="delta ${tone}">${escapeHtml(delta)}</span></div><p class="kpi__cap">${escapeHtml(caption)}</p></article>`;
  }

  function boxPlotScale(distributions) {
    const summaries = Object.values(distributions || {}).filter(
      (summary) =>
        finite(summary?.whisker_low) && finite(summary?.whisker_high),
    );
    if (!summaries.length) return [0, 1];
    const min = Math.min(...summaries.map((summary) => summary.whisker_low));
    const max = Math.max(...summaries.map((summary) => summary.whisker_high));
    if (min === max) return [min - 1, max + 1];
    const padding = (max - min) * 0.06;
    return [Math.max(0, min - padding), max + padding];
  }

  function volumeBoxPlotCard(label, summary, scale, tone, help = []) {
    const fields = ["whisker_low", "q1", "median", "q3", "whisker_high"];
    const valid = fields.every((field) => finite(summary?.[field]));
    const header = `<div class="kpi__head"><p class="kpi__label">${escapeHtml(label)}</p>${kpiHelp(label, help)}</div>`;
    if (!valid) {
      return `<article class="kpi kpi--volume">${header}<div class="volume-box__empty" role="img" aria-label="${escapeHtml(`${label} distribution unavailable`)}">—</div></article>`;
    }
    const width = 320;
    const left = 5;
    const right = 315;
    const [min, max] = scale;
    const x = (value) =>
      left + ((value - min) / Math.max(max - min, 1)) * (right - left);
    const lowerWhisker = x(summary.whisker_low);
    const q1 = x(summary.q1);
    const median = x(summary.median);
    const q3 = x(summary.q3);
    const upperWhisker = x(summary.whisker_high);
    const accessibleLabel = `${label} distribution: lower quartile ${kl(summary.q1)}, median ${kl(summary.median)}, upper quartile ${kl(summary.q3)}, whiskers ${kl(summary.whisker_low)} to ${kl(summary.whisker_high)}`;
    return `<article class="kpi kpi--volume">${header}<svg class="volume-box volume-box--${escapeHtml(tone)}" viewBox="0 0 ${width} 52" role="img" aria-label="${escapeHtml(accessibleLabel)}"><title>${escapeHtml(accessibleLabel)}</title><line class="volume-box__whisker" x1="${lowerWhisker}" y1="17" x2="${upperWhisker}" y2="17"/><line class="volume-box__cap" x1="${lowerWhisker}" y1="10" x2="${lowerWhisker}" y2="24"/><line class="volume-box__cap" x1="${upperWhisker}" y1="10" x2="${upperWhisker}" y2="24"/><rect class="volume-box__quartiles" x="${q1}" y="7" width="${Math.max(q3 - q1, 1)}" height="20"/><line class="volume-box__median" x1="${median}" y1="5" x2="${median}" y2="29"/><text class="volume-box__median-label" x="${median}" y="42" text-anchor="middle">${escapeHtml(kl(summary.median))}</text></svg></article>`;
  }

  function overviewChartHeight(container) {
    const bounds = container?.getBoundingClientRect();
    if (!bounds?.width || !bounds.height) return 252;
    return Math.max(
      180,
      Math.min(1200, Math.round((bounds.height / bounds.width) * 1000)),
    );
  }

  function renderOverviewCharts(payload) {
    const monthlyRows = payload.monthly_performance?.rows || [];
    const performanceChart = document.querySelector("[data-overview-chart]");
    const volumeChart = document.querySelector("[data-overview-volume-chart]");
    setHtml(
      performanceChart,
      overviewPerformanceChart(monthlyRows, {
        height: overviewChartHeight(performanceChart),
      }),
    );
    setHtml(
      volumeChart,
      overviewVolumeChart(monthlyRows, {
        height: overviewChartHeight(volumeChart),
      }),
    );
    if (!chartDialog.hidden) renderFullscreenChart();
  }

  function scheduleOverviewChartRender() {
    if (!currentPayload || !["overview", "trends"].includes(activeTabId()))
      return;
    cancelAnimationFrame(overviewResizeFrame);
    overviewResizeFrame = requestAnimationFrame(() => {
      overviewResizeFrame = null;
      if (activeTabId() === "overview") renderOverviewCharts(currentPayload);
      else if (moduleStates.get("trends")?.status === "fresh")
        renderTrendMonthlyChart(currentPayload);
    });
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
        ["Forecast rows", count(summary.forecast_rows)],
        ["Complete pairs", count(metrics.complete_pairs)],
        ["Coverage", pct(summary.coverage_pct)],
        ["Eligible actual", kl(summary.coverage_numerator_actual_kl)],
      ]
        .map(
          ([label, value]) =>
            `<span class="overview-health__fact"><b>${escapeHtml(label)}</b><strong>${escapeHtml(value)}</strong></span>`,
        )
        .join(""),
    );
    setHtml(
      document.querySelector("[data-population-details]"),
      [
        ["Forecast rows", count(summary.forecast_rows)],
        ["Pair rows", count(summary.selected_pair_rows)],
        ["Complete pairs", count(metrics.complete_pairs)],
        ["Missing vintages", count(metrics.missing_vintage_pairs)],
        ["Vintage A", summary.vintage_a_rule || "comparison N/A"],
        ["Vintage B", summary.vintage_b_rule || "comparison N/A"],
        ["Zero actual", count(metrics.zero_actual_observations)],
        ["Missing actual", count(metrics.missing_actual_observations)],
        ["Comparable", count(summary.comparable_pairs)],
        ["Coverage", pct(summary.coverage_pct)],
      ]
        .map(
          ([label, value]) =>
            `<span class="overview-details__item"><b>${escapeHtml(label)}</b><strong>${escapeHtml(value)}</strong></span>`,
        )
        .join(""),
    );
    const accuracyDelta = metrics.accuracy_delta_pp;
    const volumeDistributions = payload.volume_distributions || {};
    const volumeScale = boxPlotScale(volumeDistributions);
    const wape = finite(metrics.wape_pct)
      ? metrics.wape_pct
      : finite(metrics.accuracy_numerator_kl) &&
          finite(metrics.accuracy_denominator_actual_kl) &&
          metrics.accuracy_denominator_actual_kl !== 0
        ? (metrics.accuracy_numerator_kl /
            metrics.accuracy_denominator_actual_kl) *
          100
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
          [
            "How close the selected forecast is to actual demand across the active population. Higher is better.",
            "It is calculated as 100% minus total absolute error divided by total actual volume. The observation count shows how many valid rows contributed.",
            payload.request.horizon === null
              ? "All available horizons allowed by the current vintage rules are included; this is not a single fixed forecast horizon."
              : `The active population is restricted to forecasts made M−${payload.request.horizon}, or ${payload.request.horizon} months before each target month.`,
          ],
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
          [
            "Shows whether forecasts are systematically above or below actual demand.",
            "A positive value means over-forecasting; a negative value means under-forecasting. A value near zero means the over- and under-forecast errors largely balance out.",
          ],
        ),
        volumeBoxPlotCard(
          "Actual volume",
          volumeDistributions.actual,
          volumeScale,
          "actual",
          [
            "Shows how actual demand volume is distributed across the active observations, rather than showing one total.",
            "The middle line is the median, the box contains the middle 50% of observations, and the whiskers show the broader typical range.",
          ],
        ),
        volumeBoxPlotCard(
          "Forecast volume",
          volumeDistributions.forecast,
          volumeScale,
          "forecast",
          [
            "Shows the distribution of selected forecast volumes across the same active observations as the actual-volume card.",
            "Compare its median and spread with actual volume to see whether forecasts are generally shifted higher, lower, or are more variable.",
          ],
        ),
        kpi(
          "WAPE",
          pct(wape),
          `${count(metrics.eligible_observations)} obs`,
          `${kl(metrics.accuracy_numerator_kl)} / ${kl(metrics.accuracy_denominator_actual_kl)} actual`,
          "",
          [
            "Weighted absolute percentage error: total absolute forecast error divided by total actual volume. Lower is better.",
            "Large-volume observations carry more influence than small-volume observations. Forecast accuracy on this dashboard is approximately 100% minus WAPE.",
          ],
        ),
        kpi(
          "Revision effectiveness",
          pct(metrics.revision_effectiveness_pct),
          `${count(metrics.effectiveness_numerator)} / ${count(metrics.effectiveness_denominator)}`,
          "improved / materially revised",
          "",
          [
            "Of the product-target-month pairs that were meaningfully revised, this is the share whose latest forecast moved closer to actual demand.",
            "The first count is improved revisions; the second is all materially revised pairs. Unchanged forecasts are excluded from the denominator.",
            "With oldest-versus-latest vintage rules, each pair can use different available horizons. This is not automatically a six-month-horizon measure.",
          ],
        ),
      ].join(""),
    );
    renderOverviewCharts(payload);
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

  function overviewVolumeExtent() {
    return [OVERVIEW_VOLUME_Y_MIN_KL, OVERVIEW_VOLUME_Y_MAX_KL];
  }

  function smoothLinePath(points) {
    if (!points.length) return "";
    return points.slice(1).reduce((path, point, index) => {
      const previous = points[index];
      const midpoint = (previous.x + point.x) / 2;
      return `${path} C ${midpoint},${previous.y} ${midpoint},${point.y} ${point.x},${point.y}`;
    }, `M ${points[0].x},${points[0].y}`);
  }

  function overviewPerformanceChart(rows, { height = 252 } = {}) {
    if (!rows.length) return emptyVisual("No monthly metric rows");
    const source = rows[0].source;
    const sourceRows = rows
      .filter((row) => row.source === source)
      .sort((a, b) => a.snop_month.localeCompare(b.snop_month));
    const months = sourceRows.map((row) => row.snop_month);
    const width = 1000;
    const scaleY = (value) => Math.round((value / 252) * height);
    const left = 22;
    const right = 982;
    const accuracyTop = scaleY(18);
    const accuracyBottom = scaleY(158);
    const biasTop = scaleY(178);
    const biasBottom = scaleY(224);
    const x = (month) =>
      left +
      (months.indexOf(month) / Math.max(1, months.length - 1)) * (right - left);
    const accuracyValues = sourceRows.flatMap((row) => [
      row.vintage_a_accuracy_pct,
      row.vintage_b_accuracy_pct,
    ]);
    const [accuracyMin, accuracyMax] = chartExtent(accuracyValues);
    const accuracyY = (value) =>
      accuracyBottom -
      ((value - accuracyMin) / (accuracyMax - accuracyMin)) *
        (accuracyBottom - accuracyTop);
    const maxBias = Math.max(
      ...sourceRows.map((row) => Math.abs(row.bias_pct || 0)),
      1,
    );
    const biasZero = (biasTop + biasBottom) / 2;
    const biasY = (value) =>
      biasZero - (value / maxBias) * ((biasBottom - biasTop) / 2);
    const accuracyGrid = [0, 0.25, 0.5, 0.75, 1]
      .map((ratio) => {
        const y = accuracyTop + ratio * (accuracyBottom - accuracyTop);
        return `<line x1="${left}" y1="${y}" x2="${right}" y2="${y}"/>`;
      })
      .join("");
    const line = (metric, className, labelOffset) => {
      const metricRows = sourceRows.filter((row) => finite(row[metric]));
      const points = metricRows.map((row) => ({
        x: x(row.snop_month),
        y: accuracyY(row[metric]),
      }));
      const labels = metricRows
        .map(
          (row) =>
            `<text x="${x(row.snop_month)}" y="${accuracyY(row[metric]) + labelOffset}">${escapeHtml(metricValue(row[metric], metric, 0))}</text>`,
        )
        .join("");
      return `<path class="chart__smooth-line ${className}" data-interpolation="smooth" d="${smoothLinePath(points)}"/><g class="chart__data-labels ${className}">${labels}</g>`;
    };
    const biasBars = sourceRows
      .filter((row) => finite(row.bias_pct))
      .map((row) => {
        const y = biasY(row.bias_pct);
        const height = Math.abs(biasZero - y);
        const barY = Math.min(y, biasZero);
        const tone = row.bias_pct >= 0 ? "over" : "under";
        const labelY = row.bias_pct >= 0 ? barY - 5 : barY + height + 12;
        return `<g class="bias-strip__bar bias-strip__bar--${tone}"><rect x="${x(row.snop_month) - 11}" y="${barY}" width="22" height="${height}"/><text x="${x(row.snop_month)}" y="${labelY}">${escapeHtml(metricValue(row.bias_pct, "bias_pct", 0))}</text></g>`;
      })
      .join("");
    const monthLabels = months
      .map((month) => {
        const [monthName, year] = monthLabel(month).split(" ");
        return `<text x="${x(month)}" y="${scaleY(234)}"><tspan x="${x(month)}">${escapeHtml(monthName)}</tspan><tspan class="chart__axis-year" x="${x(month)}" dy="16">${escapeHtml(year)}</tspan></text>`;
      })
      .join("");
    const hitWidth = (right - left) / Math.max(1, months.length - 1);
    const monthHits = sourceRows
      .map((row) => {
        const accessibleLabel = `${monthLabel(row.snop_month)}: Vintage A accuracy ${metricValue(row.vintage_a_accuracy_pct, "vintage_a_accuracy_pct")}, Vintage B accuracy ${metricValue(row.vintage_b_accuracy_pct, "vintage_b_accuracy_pct")}, Vintage B bias ${metricValue(row.bias_pct, "bias_pct")}`;
        return `<rect class="chart__month-hit chart__point" x="${Math.max(left, x(row.snop_month) - hitWidth / 2)}" y="${accuracyTop}" width="${Math.min(hitWidth, right - Math.max(left, x(row.snop_month) - hitWidth / 2))}" height="${biasBottom - accuracyTop}" tabindex="0" role="img" aria-label="${escapeHtml(accessibleLabel)}" data-tooltip-source="${escapeHtml(source.toUpperCase())}" data-tooltip-month="${escapeHtml(monthLabel(row.snop_month))}" data-tooltip-vintage-a="${escapeHtml(metricValue(row.vintage_a_accuracy_pct, "vintage_a_accuracy_pct"))}" data-tooltip-vintage-b="${escapeHtml(metricValue(row.vintage_b_accuracy_pct, "vintage_b_accuracy_pct"))}" data-tooltip-bias="${escapeHtml(metricValue(row.bias_pct, "bias_pct"))}" data-tooltip-bias-raw="${escapeHtml(row.bias_pct)}"/>`;
      })
      .join("");
    return `<svg class="chart chart--overview" viewBox="0 0 ${width} ${height}" role="img" aria-label="Monthly Vintage A and Vintage B accuracy with Vintage B bias"><g class="chart__grid">${accuracyGrid}</g>${line("vintage_a_accuracy_pct", "chart__series--vintage-a", 14)}${line("vintage_b_accuracy_pct", "chart__series--vintage-b", -7)}<g class="bias-strip"><line class="bias-strip__zero" x1="${left}" y1="${biasZero}" x2="${right}" y2="${biasZero}"/>${biasBars}</g><line class="chart__x-divider" x1="${left}" y1="${scaleY(228)}" x2="${right}" y2="${scaleY(228)}"/><g class="chart__month-hits">${monthHits}</g><g class="chart__labels">${monthLabels}</g></svg>`;
  }

  function overviewVolumeChart(rows, { height = 252 } = {}) {
    if (!rows.length) return emptyVisual("No monthly volume rows");
    const source = rows[0].source;
    const sourceRows = rows
      .filter((row) => row.source === source)
      .sort((a, b) => a.snop_month.localeCompare(b.snop_month));
    const months = sourceRows.map((row) => row.snop_month);
    const width = 1000;
    const scaleY = (value) => Math.round((value / 252) * height);
    const left = 60;
    const right = 982;
    const top = scaleY(18);
    const bottom = scaleY(220);
    const x = (month) =>
      left +
      (months.indexOf(month) / Math.max(1, months.length - 1)) * (right - left);
    const volumeValues = sourceRows.flatMap((row) => [
      row.vintage_a_forecast_kl,
      row.vintage_b_forecast_kl,
      row.actual_kl,
    ]);
    const [min, max] = overviewVolumeExtent(volumeValues);
    const y = (value) =>
      bottom - ((value - min) / (max - min)) * (bottom - top);
    const grid = [0, 0.25, 0.5, 0.75, 1]
      .map((ratio) => {
        const gridY = top + ratio * (bottom - top);
        const value = max - ratio * (max - min);
        return `<line x1="${left}" y1="${gridY}" x2="${right}" y2="${gridY}"/><text x="51" y="${gridY + 4}">${escapeHtml(number(value, 0))}</text>`;
      })
      .join("");
    const series = (metric, className) => {
      const points = sourceRows
        .filter((row) => finite(row[metric]))
        .map((row) => ({ x: x(row.snop_month), y: y(row[metric]) }));
      return `<path class="chart__smooth-line ${className}" d="${smoothLinePath(points)}"/>`;
    };
    const monthLabels = months
      .map((month) => {
        const [monthName, year] = monthLabel(month).split(" ");
        return `<text x="${x(month)}" y="${scaleY(234)}"><tspan x="${x(month)}">${escapeHtml(monthName)}</tspan><tspan class="chart__axis-year" x="${x(month)}" dy="16">${escapeHtml(year)}</tspan></text>`;
      })
      .join("");
    const hitWidth = (right - left) / Math.max(1, months.length - 1);
    const monthHits = sourceRows
      .map((row) => {
        const variance = signedKl(row.vintage_b_forecast_kl - row.actual_kl);
        const accessibleLabel = `${monthLabel(row.snop_month)}: Vintage A forecast ${kl(row.vintage_a_forecast_kl)}, Vintage B forecast ${kl(row.vintage_b_forecast_kl)}, actual ${kl(row.actual_kl)}, variance ${variance}`;
        return `<rect class="chart__month-hit chart__point chart__volume-hit" x="${Math.max(left, x(row.snop_month) - hitWidth / 2)}" y="${top}" width="${Math.min(hitWidth, right - Math.max(left, x(row.snop_month) - hitWidth / 2))}" height="${bottom - top}" tabindex="0" role="img" aria-label="${escapeHtml(accessibleLabel)}" data-tooltip-kind="volume" data-tooltip-source="${escapeHtml(source.toUpperCase())}" data-tooltip-month="${escapeHtml(monthLabel(row.snop_month))}" data-tooltip-vintage-a="${escapeHtml(kl(row.vintage_a_forecast_kl))}" data-tooltip-vintage-b="${escapeHtml(kl(row.vintage_b_forecast_kl))}" data-tooltip-actual="${escapeHtml(kl(row.actual_kl))}" data-tooltip-variance="${escapeHtml(variance)}"/>`;
      })
      .join("");
    return `<svg class="chart chart--overview-volume" viewBox="0 0 ${width} ${height}" data-domain-min="${min}" data-domain-max="${max}" data-data-min="${Math.min(...volumeValues.filter(finite))}" data-data-max="${Math.max(...volumeValues.filter(finite))}" role="img" aria-label="Monthly Vintage A and Vintage B forecast volume versus actual volume"><text class="chart__axis-unit" x="${left}" y="${scaleY(13)}">KL</text><g class="chart__grid chart__grid--volume">${grid}</g>${series("vintage_a_forecast_kl", "chart__series--vintage-a")}${series("vintage_b_forecast_kl", "chart__series--vintage-b")}${series("actual_kl", "chart__series--actual")}<g class="chart__month-hits">${monthHits}</g><g class="chart__labels">${monthLabels}</g></svg>`;
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
    const height = 244;
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
      .map((source, sourceIndex) => {
        const sourceRows = rows.filter(
          (row) => row.source === source && finite(row[metric]),
        );
        const points = sourceRows.map((row) => ({
          x: x(row.snop_month),
          y: y(row[metric]),
        }));
        const color = colors[source] || "var(--blue)";
        const labelOffset = sources.length === 1 ? -10 : sourceIndex ? 15 : -10;
        const dataLabels = sourceRows
          .map(
            (row) =>
              `<text x="${x(row.snop_month)}" y="${y(row[metric]) + labelOffset}">${escapeHtml(metricValue(row[metric], metric))}</text>`,
          )
          .join("");
        const circles = sourceRows
          .map((row) => {
            const accessibleLabel = `${source.toUpperCase()}, ${monthLabel(row.snop_month)}, ${metricLabels[metric] || label} ${metricValue(row[metric], metric)}`;
            return `<circle class="chart__point" cx="${x(row.snop_month)}" cy="${y(row[metric])}" r="4" tabindex="0" role="img" aria-label="${escapeHtml(accessibleLabel)}" data-tooltip-source="${escapeHtml(source.toUpperCase())}" data-tooltip-month="${escapeHtml(monthLabel(row.snop_month))}" data-tooltip-metric="${escapeHtml(metricLabels[metric] || label)}" data-tooltip-value="${escapeHtml(metricValue(row[metric], metric, 2))}" data-tooltip-actual="${escapeHtml(kl(row.actual_kl))}" data-tooltip-forecast="${escapeHtml(kl(row.forecast_kl))}" data-tooltip-observations="${escapeHtml(count(row.eligible_observations))}"><title>${escapeHtml(accessibleLabel)} · actual ${kl(row.actual_kl)} · forecast ${kl(row.forecast_kl)} · n ${count(row.eligible_observations)}</title></circle>`;
          })
          .join("");
        return `<path class="chart__smooth-line" data-interpolation="smooth" d="${smoothLinePath(points)}" stroke="${color}"/><g class="chart__data-labels" style="--series:${color}">${dataLabels}</g><g class="chart__points" style="--series:${color}">${circles}</g>`;
      })
      .join("");
    const labels = months
      .map((month) => {
        const [monthName, year] = monthLabel(month).split(" ");
        return `<text x="${x(month)}" y="211"><tspan x="${x(month)}">${escapeHtml(monthName)}</tspan><tspan class="chart__axis-year" x="${x(month)}" dy="12">${escapeHtml(year)}</tspan></text>`;
      })
      .join("");
    return `<svg class="chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(label)}"><title>${escapeHtml(label)}</title><g class="chart__grid">${grid}</g><g class="volume-bars">${bars}</g>${series}<g class="chart__labels">${labels}</g></svg>`;
  }

  function renderTrendMonthlyChart(payload) {
    const monthlyMetric = document.querySelector(
      '[data-metric-selector="monthly"]',
    ).value;
    const monthly = payload.monthly_performance || { rows: [], total: 0 };
    const chartContainer = document.querySelector("[data-trend-chart]");
    const title = document.querySelector("[data-trend-title]");
    const subtitle = document.querySelector("[data-trend-subtitle]");
    const legend = document.querySelector("[data-trend-legend]");

    if (monthlyMetric === "forecast_accuracy_pct") {
      title.textContent = chartDialogContent.accuracy.title;
      subtitle.textContent = `Compare accuracy; bias is for Vintage B · ${payload.request.comparison_mode ? "Aligned TM and ML" : payload.request.source.toUpperCase()} · ${monthly.total} monthly rows`;
      setHtml(legend, chartDialogContent.accuracy.legend);
      setHtml(
        chartContainer,
        overviewPerformanceChart(monthly.rows, {
          height: overviewChartHeight(chartContainer),
        }),
      );
      return;
    }

    title.textContent = `${metricLabels[monthlyMetric]} by target month`;
    subtitle.textContent = `${payload.request.comparison_mode ? "Aligned TM and ML" : payload.request.source.toUpperCase()} · ${monthly.total} monthly rows`;
    const sources = [...new Set(monthly.rows.map((row) => row.source))];
    setHtml(
      legend,
      sources
        .map(
          (source) =>
            `<span><i class="key key--${source === "tm" ? "amber" : "teal"}"></i>${source.toUpperCase()}</span>`,
        )
        .join(""),
    );
    setHtml(
      chartContainer,
      lineChart(monthly.rows, monthlyMetric, {
        label: `${metricLabels[monthlyMetric]} by month`,
      }),
    );
  }

  function renderTrends(payload, { heatmap = true } = {}) {
    const horizonMetric = document.querySelector(
      '[data-metric-selector="horizon"]',
    ).value;
    const horizon = payload.horizon_performance || { rows: [] };

    renderTrendMonthlyChart(payload);
    renderHorizonBars(horizon.rows, horizonMetric);
    if (heatmap) renderTrendHeatmap(payload);
  }

  function renderTrendHeatmap(payload) {
    const heatmapMetric = document.querySelector(
      '[data-metric-selector="heatmap"]',
    ).value;
    renderHeatmap(
      payload.brand_target_month_performance?.rows || [],
      heatmapMetric,
    );
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

  function revisionHistoryChart(history) {
    const months = (history?.months || []).slice(-6);
    if (!months.length) return emptyVisual("No forecast revision history");
    const source = String(history.source || "selected");
    const width = 720;
    const height = 300;
    const left = 64;
    const right = 708;
    const top = 24;
    const bottom = 224;
    const labelY = 248;
    const deltas = months.flatMap((month) =>
      (month.points || []).map((point) => point.delta_pct).filter(finite),
    );
    const maxMagnitude = Math.max(...deltas.map(Math.abs), 0);
    const domain = Math.max(5, Math.ceil((maxMagnitude * 1.08) / 10) * 10);
    const y = (value) =>
      bottom - ((value + domain) / (domain * 2)) * (bottom - top);
    const ticks = [domain, domain / 2, 0, -domain / 2, -domain];
    const grid = ticks
      .map((value) => {
        const gridY = y(value);
        return `<line class="${value === 0 ? "revision-history__zero" : ""}" x1="${left}" y1="${gridY}" x2="${right}" y2="${gridY}"/><text x="${left - 9}" y="${gridY + 3}" text-anchor="end">${escapeHtml(`${value > 0 ? "+" : ""}${number(value, domain <= 10 ? 1 : 0)}%`)}</text>`;
      })
      .join("");
    const bandWidth = (right - left) / months.length;
    const bands = months
      .map((month, monthIndex) => {
        const bandLeft = left + bandWidth * monthIndex;
        const bandRight = bandLeft + bandWidth;
        const innerLeft = bandLeft + 12;
        const innerRight = bandRight - 12;
        const points = (month.points || []).filter((point) =>
          finite(point.delta_pct),
        );
        const coordinates = points.map((point, pointIndex) => ({
          x:
            points.length === 1
              ? innerRight
              : innerLeft +
                (pointIndex / (points.length - 1)) * (innerRight - innerLeft),
          y: y(point.delta_pct),
          point,
        }));
        const segments = coordinates
          .slice(1)
          .map((current, index) => {
            const previous = coordinates[index];
            const outcome = ["improved", "worsened", "neutral"].includes(
              current.point.revision_outcome,
            )
              ? current.point.revision_outcome
              : "neutral";
            const accessibleLabel = `${monthLabel(month.snop_month)}, ${monthLabel(current.point.previous_calculation_month)} to ${monthLabel(current.point.calculation_month)}, forecast revision ${signedKl(current.point.revision_kl)}, forecast accuracy ${outcome} by ${pp(current.point.fa_improvement_pp)}`;
            return `<line class="chart__point revision-history__segment-hit" x1="${previous.x}" y1="${previous.y}" x2="${current.x}" y2="${current.y}" tabindex="0" role="img" aria-label="${escapeHtml(accessibleLabel)}" data-tooltip-kind="revision-history-segment" data-tooltip-source="${escapeHtml(source.toUpperCase())}" data-tooltip-month="${escapeHtml(monthLabel(month.snop_month))}" data-tooltip-outcome="${escapeHtml(labelize(outcome))}" data-tooltip-previous-version="${escapeHtml(monthLabel(current.point.previous_calculation_month))}" data-tooltip-version="${escapeHtml(monthLabel(current.point.calculation_month))}" data-tooltip-fa="${escapeHtml(pp(current.point.fa_improvement_pp))}" data-tooltip-fa-raw="${escapeHtml(current.point.fa_improvement_pp)}" data-tooltip-error-improvement="${escapeHtml(signedKl(current.point.error_improvement_kl))}" data-tooltip-previous-error="${escapeHtml(kl(current.point.previous_absolute_error_kl))}" data-tooltip-error="${escapeHtml(kl(current.point.absolute_error_kl))}" data-tooltip-revision="${escapeHtml(signedKl(current.point.revision_kl))}" data-tooltip-previous-forecast="${escapeHtml(kl(current.point.previous_forecast_kl))}" data-tooltip-forecast="${escapeHtml(kl(current.point.forecast_kl))}"/><line class="revision-history__path revision-history__segment revision-history__segment--${escapeHtml(outcome)}" data-interpolation="linear" x1="${previous.x}" y1="${previous.y}" x2="${current.x}" y2="${current.y}"/>`;
          })
          .join("");
        const pointOutcome = (point) =>
          ["improved", "worsened", "neutral"].includes(point?.revision_outcome)
            ? point.revision_outcome
            : "neutral";
        const nodes = coordinates
          .slice(0, -1)
          .map(
            ({ x, y: pointY, point }) =>
              `<circle class="revision-history__node revision-history__node--${escapeHtml(pointOutcome(point))}" cx="${x}" cy="${pointY}" r="4.4" aria-hidden="true"/>`,
          )
          .join("");
        const endpoint = coordinates.at(-1);
        const marker = endpoint
          ? `<circle class="chart__point revision-history__endpoint revision-history__node--${escapeHtml(pointOutcome(endpoint.point))}" cx="${endpoint.x}" cy="${endpoint.y}" r="4.8" tabindex="0" role="img" aria-label="${escapeHtml(`${monthLabel(month.snop_month)} latest forecast delta ${pct(month.latest_delta_pct)} and net forecast accuracy change ${pp(month.net_fa_improvement_pp)} from its oldest version`)}" data-tooltip-kind="revision-history" data-tooltip-source="${escapeHtml(source.toUpperCase())}" data-tooltip-month="${escapeHtml(monthLabel(month.snop_month))}" data-tooltip-delta="${escapeHtml(pct(month.latest_delta_pct))}" data-tooltip-net-fa="${escapeHtml(pp(month.net_fa_improvement_pp))}" data-tooltip-net-fa-raw="${escapeHtml(month.net_fa_improvement_pp)}" data-tooltip-net-error-improvement="${escapeHtml(signedKl(month.net_error_improvement_kl))}" data-tooltip-oldest-accuracy="${escapeHtml(pct(month.oldest_forecast_accuracy_pct))}" data-tooltip-latest-accuracy="${escapeHtml(pct(month.latest_forecast_accuracy_pct))}" data-tooltip-oldest-forecast="${escapeHtml(kl(month.oldest_forecast_kl))}" data-tooltip-latest-forecast="${escapeHtml(kl(month.latest_forecast_kl))}" data-tooltip-vintages="${escapeHtml(count(month.vintage_count))}" data-tooltip-products="${escapeHtml(count(month.product_count))}" data-tooltip-oldest-version="${escapeHtml(monthLabel(month.oldest_calculation_month))}" data-tooltip-latest-version="${escapeHtml(monthLabel(month.latest_calculation_month))}"/>`
          : "";
        const [monthName, year] = monthLabel(month.snop_month).split(" ");
        return `<g class="revision-history__band" data-target-month="${escapeHtml(month.snop_month)}"><rect class="revision-history__band-bg" x="${bandLeft}" y="${top}" width="${bandWidth}" height="${bottom - top}"/><line class="revision-history__separator" x1="${bandLeft}" y1="${top}" x2="${bandLeft}" y2="${bottom}"/>${segments}${nodes}${marker}<text class="revision-history__month" x="${bandLeft + bandWidth / 2}" y="${labelY}"><tspan x="${bandLeft + bandWidth / 2}">${escapeHtml(monthName)}</tspan><tspan class="chart__axis-year" x="${bandLeft + bandWidth / 2}" dy="14">${escapeHtml(year)}</tspan></text></g>`;
      })
      .join("");
    return `<div class="revision-history-chart"><svg class="chart chart--revision-history" viewBox="0 0 ${width} ${height}" role="img" aria-label="Forecast revision paths for the latest ${months.length} target months"><title>Forecast revision paths by target month, indexed to each month’s oldest forecast</title><text class="revision-history__axis-title" x="15" y="${(top + bottom) / 2}" transform="rotate(-90 15 ${(top + bottom) / 2})">Delta vs oldest forecast (%)</text><g class="chart__grid revision-history__grid">${grid}</g>${bands}<line class="revision-history__separator" x1="${right}" y1="${top}" x2="${right}" y2="${bottom}"/></svg><div class="revision-history__legend"><span>Within each month band: oldest → latest forecast version</span><span class="revision-history__legend-outcome"><i class="revision-history__legend-improved"></i>Green improved FA</span><span class="revision-history__legend-outcome"><i class="revision-history__legend-worsened"></i>Red worsened FA</span><span class="revision-history__legend-outcome"><i class="revision-history__legend-neutral"></i>Gray neutral</span><span><i></i>Latest version</span><span>Shared y-axis · fixed product cohort per month</span></div></div>`;
  }

  function revisionOutcomeInstructions(category, actions) {
    if (category === "improved") {
      return `<span class="severity severity--good" title="${escapeHtml(`${count(actions.improved)} revisions improved accuracy · ${pct(actions.effectiveness_pct)} effectiveness`)}">Keep</span>`;
    }
    if (category !== "worsened") return "";
    const direction =
      actions.harmful_up?.error_kl >= actions.harmful_down?.error_kl
        ? "upward"
        : "downward";
    const directionCount =
      direction === "upward"
        ? actions.harmful_up?.count
        : actions.harmful_down?.count;
    const directionError =
      direction === "upward"
        ? actions.harmful_up?.error_kl
        : actions.harmful_down?.error_kl;
    return `<span class="outcome__instructions"><span class="severity severity--bad" title="${escapeHtml(`${count(actions.worsened)} harmful revisions · ${signedKl(actions.harmful_error_kl)} avoidable error`)}">Review now</span><span class="severity severity--warn" title="${escapeHtml(`${count(directionCount)} harmful ${direction} revisions · ${signedKl(directionError)} error`)}">Pattern</span></span>`;
  }

  function renderRevisionPanel(payload) {
    const panel = document.querySelector("[data-revision-panel]");
    if (payload.request.comparison_mode) {
      setHtml(
        panel,
        messagePanel(
          "Vintage revisions use single-source mode",
          "Switch to TM or ML single-source scope to review revisions for one source at a time.",
          "Use single-source mode",
          "single",
        ),
      );
      return;
    }
    const metrics = payload.metrics;
    const diagnostics = rowMap(payload.revision_diagnostics?.rows, "category");
    const source = payload.request.source;
    const actions = payload.revision_actions || {
      source,
      complete: 0,
      material: 0,
      improved: 0,
      worsened: 0,
      neutral: 0,
      effectiveness_pct: null,
      total_error_improvement_kl: 0,
      harmful_error_kl: 0,
      top_action_error_kl: 0,
      top_action_share_pct: null,
      harmful_up: { count: 0, error_kl: 0 },
      harmful_down: { count: 0, error_kl: 0 },
      rows: [],
      sku_rows: [],
    };
    const scatterPayload =
      revisionScatterSelection.size && revisionDrilldownBasePayload
        ? revisionDrilldownBasePayload
        : payload;
    const scatterPopulation = scatterRowsForSource(scatterPayload, source);
    const scatterRows = filterScatterRows(scatterPopulation);
    const latestActualMonth = payload.revision_history?.latest_actual_month;
    const revisionWindowLabel = latestActualMonth
      ? `6 target months through ${monthLabel(latestActualMonth)} · latest actual`
      : "No actualized target months available";
    if (revisionQueueSource !== source) {
      revisionQueueSource = source;
      revisionQueueSearch = "";
      revisionQueueSort = { key: "impact_kl", direction: "desc" };
    }
    revisionQueueRows = actions.sku_rows || [];
    setHtml(
      panel,
      `
      <div class="kpis kpis--row comparison-kpis">
        ${kpi(
          "Vintage accuracy delta",
          pp(metrics.accuracy_delta_pp),
          metrics.accuracy_delta_pp >= 0 ? "B improved" : "B worsened",
          `${signedKl(metrics.accuracy_delta_numerator_kl)} / ${kl(metrics.accuracy_delta_denominator_actual_kl)}`,
          metrics.accuracy_delta_pp >= 0 ? "delta--up" : "delta--down",
          [
            "The net accuracy change from Vintage A to Vintage B across all complete product-target-month pairs in the active filters. Positive means Vintage B is more accurate.",
            `It divides ${signedKl(metrics.accuracy_delta_numerator_kl)} of net error reduction by ${kl(metrics.accuracy_delta_denominator_actual_kl)} of actual volume.`,
            "Oldest-versus-latest rules do not imply one fixed horizon: each product-month pair uses its own oldest and latest available forecasts. The six months in the revision-path chart are six target months, not a six-month forecast horizon.",
          ],
        )}
        ${kpi(
          "Revision effectiveness",
          pct(actions.effectiveness_pct ?? metrics.revision_effectiveness_pct),
          `${count(actions.improved)} / ${count(actions.material)}`,
          "improved / materially revised",
          "",
          [
            `Of ${count(actions.material)} meaningfully revised ${source.toUpperCase()} product-target-month pairs, ${count(actions.improved)} moved closer to actual demand.`,
            "Unchanged pairs are excluded. A revised pair that moved farther from actual is counted as worsened; a negligible accuracy change is neutral.",
            "These pairs follow the active Vintage A and B rules and can span different horizons unless exact horizons are selected.",
          ],
        )}
        ${kpi(
          "Total error improvement",
          signedKl(
            actions.total_error_improvement_kl ??
              metrics.total_error_improvement_kl,
          ),
          (actions.total_error_improvement_kl ??
            metrics.total_error_improvement_kl) >= 0
            ? "positive improves"
            : "negative worsens",
          `Σ(|error A| − |error B|) · ${count(actions.complete)} ${source.toUpperCase()} pairs`,
          (actions.total_error_improvement_kl ??
            metrics.total_error_improvement_kl) >= 0
            ? "delta--up"
            : "delta--down",
          [
            `This adds the error reduction from all ${count(actions.complete)} complete ${source.toUpperCase()} product-target-month pairs. One pair needs Vintage A, Vintage B, and a valid actual for the same product and target month.`,
            "For each pair: absolute error of A minus absolute error of B. Positive contributions improved; negative contributions worsened. The card shows the net sum after both are combined.",
            "The KPI population follows the active target-month filters and may be wider than the six latest actualized target months displayed in the revision-path chart.",
          ],
        )}
      </div>
      <div class="revision-selection-bar"${revisionScatterSelection.size ? "" : " hidden"}><span class="revision-selection-bar__copy"><span><b>${count(revisionScatterSelection.size)}</b> parent${revisionScatterSelection.size === 1 ? "" : "s"} selected</span><small>Scatter keeps all parents visible for context; KPIs and revision evidence follow this selection.</small></span><button class="btn btn--quiet" type="button" data-drilldown-clear>Clear selection</button></div>
      <div class="revision-layout">
        <section class="frame"><header class="frame__head"><div><h3 class="frame__title">Forecast revision paths · ${source.toUpperCase()}</h3><p class="frame__sub">${escapeHtml(revisionWindowLabel)} · each path is indexed to its oldest forecast</p></div><div class="frame__actions"><span class="frame__metric">up ${pct(metrics.revised_up_pct)} · down ${pct(metrics.revised_down_pct)}</span><button class="chart-expand" data-chart-fullscreen="revision-history" type="button" aria-label="Open ${source.toUpperCase()} forecast revision paths full screen" aria-haspopup="dialog" aria-controls="overview-chart-dialog"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="M7 3H3v4M13 3h4v4M17 13v4h-4M7 17H3v-4" /></svg>Full screen</button></div></header><div class="outcome-body"><div class="outcome-strip">${["improved", "worsened", "neutral", "unchanged"].map((category) => `<span class="outcome outcome--${category === "improved" ? "good" : category === "worsened" ? "bad" : category === "neutral" ? "neutral" : "idle"}"><b>${labelize(category)}</b><button class="outcome__drilldown" type="button" data-drilldown-category="${category}" aria-label="Open ${category} parent-code drill-down" aria-haspopup="dialog" aria-expanded="false"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 4h12v12H4zM7 10h6M10 7v6"/></svg></button><span class="outcome__content">${revisionOutcomeInstructions(category, actions)}<strong>${count(diagnostics.get(category)?.observations || 0)}</strong></span></span>`).join("")}</div><div class="revision-history-body">${revisionHistoryChart(payload.revision_history)}</div></div></section>
        <section class="frame"><header class="frame__head"><div><h3 class="frame__title">Parent vintage trend vs improvement score</h3><p class="frame__sub">One bubble per parent · six target months through the selected end month · five vintages per month</p><p class="frame__scope-note"><b>Out of scope · super seasonal:</b> PA Bodylot · JFB Powder · RK Cooling · Saff Honey · SP Petroleum Jelly (all SKUs) · PCNO EJ (all matching SKUs)</p></div><div class="frame__actions"><span class="frame__metric">${count(scatterRows.length)} ${source.toUpperCase()} parent bubbles</span><button class="chart-expand" data-chart-fullscreen="revision" type="button" aria-label="Open ${source.toUpperCase()} parent vintage score chart full screen" aria-haspopup="dialog" aria-controls="overview-chart-dialog"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="M7 3H3v4M13 3h4v4M17 13v4h-4M7 17H3v-4" /></svg>Full screen</button></div></header><div class="frame__body">${scatterChart(scatterPopulation, "revision_score_pct", "vintage_improvement_score_pp", `${source.toUpperCase()} parent vintage trend versus improvement score`, { source, tolerance: 0.01 })}</div></section>
      </div>
      <section class="frame revision-queue"><header class="frame__head"><div><h3 class="frame__title">${source.toUpperCase()} action queue</h3><p class="frame__sub">Ranked by avoidable error added by harmful revisions</p></div><div class="frame__actions"><span class="frame__metric" data-revision-queue-count></span><button class="btn" type="button" data-export-kind="revision_actions">Download action evidence · CSV</button></div></header><div class="revision-queue__toolbar"><label><span>Filter actions</span><input type="search" data-revision-action-search placeholder="SKU, material, month, or action" value="${escapeHtml(revisionQueueSearch)}" /></label><span>One row per SKU · click a column to sort</span></div><div class="revision-queue__body" data-revision-queue-table></div></section>`,
    );
    renderRevisionActionQueue();
    refreshScatterCharts();
    if (!revisionDrilldownPopover.hidden && revisionDrilldownOpenCategory) {
      const nextTrigger = panel.querySelector(
        `[data-drilldown-category="${revisionDrilldownOpenCategory}"]`,
      );
      if (nextTrigger) {
        revisionDrilldownTrigger = nextTrigger;
        nextTrigger.setAttribute("aria-expanded", "true");
        refreshRevisionDrilldownPopover();
      }
    }
  }

  const revisionSortColumns = [
    ["priority_rank", "Priority"],
    ["parent_description", "Material"],
    ["net_error_improvement_kl", "Revision performance"],
    ["latest_snop_month", "Latest target"],
    ["impact_kl", "Added error"],
    ["planner_action", "Planner action"],
  ];

  function revisionActionName(row) {
    return (
      row.planner_action ||
      (row.revision_direction === "up"
        ? "Validate uplift"
        : "Check demand reduction")
    );
  }

  function revisionActionSkuRows() {
    const query = revisionQueueSearch.trim().toLowerCase();
    const filtered = revisionQueueRows.filter((row) => {
      if (!query) return true;
      const months = (row.monthly_performance || []).map((point) =>
        monthLabel(point.snop_month),
      );
      return [
        row.parent_code,
        row.parent_description,
        row.brand,
        row.latest_snop_month,
        revisionActionName(row),
        row.revision_direction,
        ...months,
      ].some((value) =>
        String(value ?? "")
          .toLowerCase()
          .includes(query),
      );
    });
    const direction = revisionQueueSort.direction === "asc" ? 1 : -1;
    return filtered.sort((left, right) => {
      const leftValue = left[revisionQueueSort.key];
      const rightValue = right[revisionQueueSort.key];
      if (finite(leftValue) && finite(rightValue))
        return (leftValue - rightValue) * direction;
      return (
        String(leftValue ?? "").localeCompare(
          String(rightValue ?? ""),
          undefined,
          {
            numeric: true,
            sensitivity: "base",
          },
        ) * direction
      );
    });
  }

  function revisionSortButton(key, label) {
    const active = revisionQueueSort.key === key;
    const arrow = active
      ? revisionQueueSort.direction === "asc"
        ? " ↑"
        : " ↓"
      : "";
    return `<button type="button" data-revision-sort="${escapeHtml(key)}" aria-label="Sort action queue by ${escapeHtml(label)}" aria-pressed="${active}">${escapeHtml(label + arrow)}</button>`;
  }

  function revisionActionSparkline(row) {
    const points = (row.monthly_performance || []).filter((point) =>
      finite(point.error_improvement_kl),
    );
    if (!points.length)
      return '<span class="revision-queue__sparkline-empty">No monthly performance</span>';
    const width = 150;
    const height = 38;
    const left = 5;
    const right = width - 5;
    const zeroY = 18;
    const amplitude = 13;
    const maxAbsolute = Math.max(
      ...points.map((point) => Math.abs(point.error_improvement_kl)),
      0.01,
    );
    const x = (index) =>
      points.length === 1
        ? width / 2
        : left + (index / (points.length - 1)) * (right - left);
    const y = (value) => zeroY - (value / maxAbsolute) * amplitude;
    const line = points
      .map(
        (point, index) =>
          `${index ? "L" : "M"}${x(index).toFixed(1)} ${y(point.error_improvement_kl).toFixed(1)}`,
      )
      .join(" ");
    const dots = points
      .map((point, index) => {
        const outcome = point.revision_outcome || "neutral";
        const accessibleLabel = `${row.parent_code}, ${monthLabel(point.snop_month)}, error improvement ${signedKl(point.error_improvement_kl)}, ${labelize(outcome)}`;
        return `<circle class="chart__point revision-queue__sparkline-point revision-queue__sparkline-point--${escapeHtml(outcome)}" cx="${x(index).toFixed(1)}" cy="${y(point.error_improvement_kl).toFixed(1)}" r="3" tabindex="0" role="img" aria-label="${escapeHtml(accessibleLabel)}" data-tooltip-kind="revision-action-sparkline" data-tooltip-source="${escapeHtml((revisionQueueSource || "").toUpperCase())}" data-tooltip-code="${escapeHtml(row.parent_code)}" data-tooltip-month="${escapeHtml(monthLabel(point.snop_month))}" data-tooltip-improvement="${escapeHtml(signedKl(point.error_improvement_kl))}" data-tooltip-improvement-raw="${escapeHtml(point.error_improvement_kl)}" data-tooltip-actual="${escapeHtml(kl(point.actual_kl))}" data-tooltip-revision="${escapeHtml(signedKl(point.revision_kl))}" data-tooltip-outcome="${escapeHtml(labelize(outcome))}"></circle>`;
      })
      .join("");
    const firstMonth = monthLabel(points[0].snop_month);
    const lastMonth = monthLabel(points[points.length - 1].snop_month);
    return `<span class="revision-queue__sparkline"><svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Monthly error improvement for ${escapeHtml(row.parent_code)}"><line class="revision-queue__sparkline-zero" x1="${left}" y1="${zeroY}" x2="${right}" y2="${zeroY}"></line><path class="revision-queue__sparkline-line" d="${line}"></path>${dots}</svg><span class="revision-queue__sparkline-range"><i>${escapeHtml(firstMonth)}</i><i>${escapeHtml(lastMonth)}</i></span><small>Error improvement · zero baseline · ${count(row.month_count)} months</small></span>`;
  }

  function revisionActionTable(rows) {
    const header = `<div class="revision-queue__head">${revisionSortColumns
      .map(([key, label]) => revisionSortButton(key, label))
      .join("")}</div>`;
    if (!rows.length)
      return `${header}<div class="empty-row">No harmful revision SKUs match this filter.</div>`;
    const body = rows
      .map((row) => {
        const action = revisionActionName(row);
        const reviewNow = row.priority_rank <= 3;
        const priority = reviewNow ? "Review now" : `#${row.priority_rank}`;
        return `<div class="revision-queue__row" data-impact-kl="${escapeHtml(row.impact_kl)}"><span><b class="severity ${reviewNow ? "severity--bad" : "severity--warn"}">${priority}</b></span><span class="revision-queue__material"><strong>${escapeHtml(row.parent_code)}</strong><em title="${escapeHtml(row.parent_description || "Description unavailable")}">${escapeHtml(row.parent_description || "Description unavailable")}</em></span>${revisionActionSparkline(row)}<span>${escapeHtml(monthLabel(row.latest_snop_month))}</span><span class="bad"><b>${signedKl(row.impact_kl)}</b><small>${count(row.harmful_month_count)} harmful months</small></span><span>${escapeHtml(action)}</span></div>`;
      })
      .join("");
    return header + body;
  }

  function renderRevisionActionQueue() {
    const table = document.querySelector("[data-revision-queue-table]");
    const counter = document.querySelector("[data-revision-queue-count]");
    if (!table || !counter) return;
    const rows = revisionActionSkuRows();
    setHtml(table, revisionActionTable(rows));
    const harmfulMonths = revisionQueueRows.reduce(
      (total, row) => total + Number(row.harmful_month_count || 0),
      0,
    );
    counter.textContent = `${count(rows.length)} of ${count(revisionQueueRows.length)} SKUs · ${count(harmfulMonths)} harmful months`;
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
    const label = `${source.toUpperCase()} comparison metrics`;
    return `<article class="source-card source-card--${source}"><header>${sourceBadge(source)}<span>common population</span>${kpiHelp(
      label,
      [
        `These ${source.toUpperCase()} metrics use only product-target-month observations shared by TM and ML at the exact comparison horizon shown above.`,
        "Accuracy measures closeness to actual demand; bias shows over- or under-forecasting; absolute error is the total miss in KL; coverage shows how much eligible actual volume is represented.",
        "Source-only observations affect coverage evidence but are excluded from the like-for-like performance comparison.",
      ],
    )}</header><div><b>Accuracy</b><strong>${pct(metrics.forecast_accuracy_pct)}</strong></div><div><b>Bias</b><strong>${pct(metrics.bias_pct)}</strong></div><div><b>Absolute error</b><strong>${kl(metrics.absolute_error_kl)}</strong></div><div><b>Coverage</b><strong>${pct(metrics.coverage_pct)}</strong></div></article>`;
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

  function scatterActual(row) {
    return Math.max(0, Number(row.actual_kl) || 0);
  }

  function scatterQuantile(values, percentile) {
    return values[Math.floor((values.length - 1) * percentile)] || 0;
  }

  function scatterDensity(valid, x, y, left, right, top, bottom) {
    const columns = 14;
    const rows = 8;
    const bins = Array.from({ length: columns * rows }, () => 0);
    valid.forEach((row) => {
      const column = Math.max(
        0,
        Math.min(
          columns - 1,
          Math.floor(((x(row.__scatterX) - left) / (right - left)) * columns),
        ),
      );
      const rowIndex = Math.max(
        0,
        Math.min(
          rows - 1,
          Math.floor(((bottom - y(row.__scatterY)) / (bottom - top)) * rows),
        ),
      );
      bins[rowIndex * columns + column] += 1;
    });
    const peak = Math.max(...bins, 1);
    const cellWidth = (right - left) / columns;
    const cellHeight = (bottom - top) / rows;
    return `<g class="scatter__density" aria-hidden="true">${bins
      .map((value, index) => {
        if (!value) return "";
        const column = index % columns;
        const row = Math.floor(index / columns);
        const opacity = 0.07 + (value / peak) * 0.18;
        return `<rect x="${left + column * cellWidth + 1}" y="${top + row * cellHeight + 1}" width="${Math.max(1, cellWidth - 2)}" height="${Math.max(1, cellHeight - 2)}" rx="2" style="opacity:${opacity}" data-density-count="${value}"/>`;
      })
      .join("")}</g>`;
  }

  function scatterControl(action, label, pressed = false, attribute = "") {
    return `<button class="scatter-control" type="button" data-scatter-action="${escapeHtml(action)}" ${attribute} aria-pressed="${pressed}">${escapeHtml(label)}</button>`;
  }

  const scatterSkuClassOrder = ["A", "B", "C", "Unclassified"];

  function scatterRowsForSource(payload, source = payload.request.source) {
    return (payload.revision_scatter?.rows || []).filter(
      (row) => !row.source || row.source === source,
    );
  }

  function scatterSkuClasses(rows) {
    const available = new Set(
      rows.map((row) => row.sku_class || "Unclassified"),
    );
    return scatterSkuClassOrder.filter((skuClass) => available.has(skuClass));
  }

  function filterScatterRows(rows) {
    const available = scatterSkuClasses(rows);
    if (
      revisionScatterSkuClass !== "all" &&
      !available.includes(revisionScatterSkuClass)
    ) {
      revisionScatterSkuClass = "all";
    }
    return revisionScatterSkuClass === "all"
      ? rows
      : rows.filter(
          (row) =>
            (row.sku_class || "Unclassified") === revisionScatterSkuClass,
        );
  }

  function scatterSkuClassSelect(rows) {
    const available = scatterSkuClasses(rows);
    const options = [
      `<option value="all"${revisionScatterSkuClass === "all" ? " selected" : ""}>All visible</option>`,
      ...available.map(
        (skuClass) =>
          `<option value="${escapeHtml(skuClass)}"${revisionScatterSkuClass === skuClass ? " selected" : ""}>${escapeHtml(skuClass)}</option>`,
      ),
    ].join("");
    return `<label class="scatter-toolbar__filter"><span>SKU class</span><select data-scatter-sku-class aria-label="Filter scatter chart by SKU class">${options}</select></label>`;
  }

  function syncScatterChart(chart) {
    chart.dataset.scatterMode = revisionScatterMode;
    chart.dataset.scatterDensity = revisionScatterDensity ? "on" : "off";
    chart.dataset.scatterFocus = revisionScatterFocus;
    chart.querySelectorAll("[data-scatter-mode]").forEach((button) => {
      button.setAttribute(
        "aria-pressed",
        String(button.dataset.scatterMode === revisionScatterMode),
      );
    });
    chart.querySelectorAll("[data-scatter-density]").forEach((button) => {
      button.setAttribute("aria-pressed", String(revisionScatterDensity));
    });
    chart.querySelectorAll("[data-scatter-focus]").forEach((button) => {
      button.setAttribute(
        "aria-pressed",
        String(button.dataset.scatterFocus === revisionScatterFocus),
      );
    });
    chart.querySelectorAll("[data-scatter-zoom-value]").forEach((value) => {
      value.textContent = `${revisionScatterZoom}×`;
    });
    chart.querySelectorAll("[data-scatter-size-label]").forEach((label) => {
      label.textContent =
        revisionScatterMode === "volume"
          ? "Size = actual volume (capped √ scaled)"
          : "Top-volume points outlined; size off";
    });
    chart.querySelectorAll(".scatter__point").forEach((point) => {
      point.setAttribute(
        "r",
        revisionScatterMode === "volume"
          ? point.dataset.radiusVolume
          : point.dataset.radiusUniform,
      );
      point.hidden =
        (revisionScatterSkuClass !== "all" &&
          point.dataset.tooltipSkuClass !== revisionScatterSkuClass) ||
        (revisionScatterFocus === "top-volume" &&
          point.dataset.topVolume !== "true") ||
        (revisionScatterFocus === "outliers" &&
          point.dataset.outlier !== "true");
      const isSelected = revisionScatterSelection.has(point.dataset.scatterKey);
      point.classList.toggle("scatter__point--selected", isSelected);
      point.classList.toggle(
        "scatter__point--context",
        revisionScatterSelection.size > 0 && !isSelected,
      );
    });
    chart
      .querySelectorAll(".scatter__point--selected")
      .forEach((point) => point.parentNode?.append(point));
    const svg = chart.querySelector(".chart--revision-scatter");
    if (svg) {
      const baseWidth = Number(svg.dataset.baseWidth);
      const baseHeight = Number(svg.dataset.baseHeight);
      const centerX = baseWidth / 2 + revisionScatterPan.x;
      const centerY = baseHeight / 2 + revisionScatterPan.y;
      const width = baseWidth / revisionScatterZoom;
      const height = baseHeight / revisionScatterZoom;
      svg.setAttribute(
        "viewBox",
        `${centerX - width / 2} ${centerY - height / 2} ${width} ${height}`,
      );
      svg
        .querySelectorAll(".scatter__selection-label")
        .forEach((label) => label.remove());
      svg
        .querySelectorAll(".scatter__point--selected:not([hidden])")
        .forEach((selected, index) => {
          if (index >= 6) return;
          const selectionLabel = document.createElementNS(
            "http://www.w3.org/2000/svg",
            "text",
          );
          selectionLabel.classList.add("scatter__selection-label");
          const labelOffset = Number(selected.getAttribute("r")) + 4;
          selectionLabel.setAttribute(
            "x",
            Number(selected.getAttribute("cx")) + labelOffset,
          );
          selectionLabel.setAttribute(
            "y",
            Number(selected.getAttribute("cy")) - labelOffset,
          );
          selectionLabel.textContent = selected.dataset.tooltipCode;
          svg.append(selectionLabel);
        });
    }
  }

  function refreshScatterCharts() {
    document
      .querySelectorAll("[data-revision-scatter]")
      .forEach(syncScatterChart);
  }

  function setScatterCrosshair(point, visible) {
    const svg = point.ownerSVGElement;
    const crosshair = svg?.querySelector(".scatter__crosshair");
    if (!crosshair) return;
    crosshair.classList.toggle("is-visible", visible);
    if (visible) {
      const x = point.getAttribute("cx");
      const y = point.getAttribute("cy");
      crosshair.querySelector(".scatter__crosshair-x").setAttribute("x1", x);
      crosshair.querySelector(".scatter__crosshair-x").setAttribute("x2", x);
      crosshair.querySelector(".scatter__crosshair-y").setAttribute("y1", y);
      crosshair.querySelector(".scatter__crosshair-y").setAttribute("y2", y);
    }
  }

  function updateScatterSelection(point, additive = false) {
    updateRevisionParentSelection(point.dataset.scatterKey, additive);
  }

  function scatterSvgPoint(svg, event) {
    const rect = svg.getBoundingClientRect();
    const viewBox = svg.viewBox.baseVal;
    return {
      x: viewBox.x + ((event.clientX - rect.left) / rect.width) * viewBox.width,
      y:
        viewBox.y + ((event.clientY - rect.top) / rect.height) * viewBox.height,
    };
  }

  function beginScatterDrag(svg, event) {
    if (event.button !== 0 || event.target.closest?.(".scatter__point")) return;
    event.preventDefault();
    svg.setPointerCapture(event.pointerId);
    const start = scatterSvgPoint(svg, event);
    scatterDrag = {
      svg,
      pointerId: event.pointerId,
      mode: event.shiftKey ? "select" : "pan",
      start,
      last: start,
      additive: event.ctrlKey || event.metaKey,
    };
    svg.classList.add("is-dragging");
    if (scatterDrag.mode === "select") {
      const rectangle = document.createElementNS(
        "http://www.w3.org/2000/svg",
        "rect",
      );
      rectangle.classList.add("scatter__selection-box");
      rectangle.setAttribute("x", start.x);
      rectangle.setAttribute("y", start.y);
      rectangle.setAttribute("width", 0);
      rectangle.setAttribute("height", 0);
      svg.append(rectangle);
    }
  }

  function moveScatterDrag(event) {
    if (!scatterDrag || event.pointerId !== scatterDrag.pointerId) return;
    const current = scatterSvgPoint(scatterDrag.svg, event);
    if (scatterDrag.mode === "pan") {
      revisionScatterPan.x -= current.x - scatterDrag.last.x;
      revisionScatterPan.y -= current.y - scatterDrag.last.y;
      scatterDrag.last = current;
      refreshScatterCharts();
      return;
    }
    const rectangle = scatterDrag.svg.querySelector(".scatter__selection-box");
    rectangle?.setAttribute("x", Math.min(scatterDrag.start.x, current.x));
    rectangle?.setAttribute("y", Math.min(scatterDrag.start.y, current.y));
    rectangle?.setAttribute("width", Math.abs(current.x - scatterDrag.start.x));
    rectangle?.setAttribute(
      "height",
      Math.abs(current.y - scatterDrag.start.y),
    );
    scatterDrag.last = current;
  }

  function endScatterDrag(event) {
    if (!scatterDrag || event.pointerId !== scatterDrag.pointerId) return;
    const { svg, mode, start, last, additive } = scatterDrag;
    if (mode === "select") {
      const xMin = Math.min(start.x, last.x);
      const xMax = Math.max(start.x, last.x);
      const yMin = Math.min(start.y, last.y);
      const yMax = Math.max(start.y, last.y);
      if (!additive) revisionScatterSelection.clear();
      svg.querySelectorAll(".scatter__point:not([hidden])").forEach((point) => {
        const x = Number(point.getAttribute("cx"));
        const y = Number(point.getAttribute("cy"));
        if (x >= xMin && x <= xMax && y >= yMin && y <= yMax) {
          revisionScatterSelection.add(point.dataset.scatterKey);
        }
      });
      svg.querySelector(".scatter__selection-box")?.remove();
      void refreshRevisionDrilldown();
    }
    svg.classList.remove("is-dragging");
    svg.releasePointerCapture(event.pointerId);
    scatterDrag = null;
  }

  function scatterChart(
    rows,
    xKey,
    yKey,
    label,
    { source = "", tolerance = 0 } = {},
  ) {
    const filteredRows = filterScatterRows(rows);
    const valid = filteredRows
      .filter((row) => finite(row[xKey]) && finite(row[yKey]))
      .map((row) => ({ ...row, __scatterX: row[xKey], __scatterY: row[yKey] }));
    if (!valid.length) return emptyVisual("No comparable scatter points");
    const scoreMode = valid.some((row) =>
      finite(row.vintage_improvement_score_pp),
    );
    const tickDigits = scoreMode ? 1 : 0;
    const width = 720;
    const height = 390;
    const left = 88;
    const right = 692;
    const top = 38;
    const bottom = 324;
    const [xMin, xMax] = chartExtent(
      valid.map((row) => row.__scatterX),
      true,
    );
    const [yMin, yMax] = chartExtent(
      valid.map((row) => row.__scatterY),
      true,
    );
    const x = (value) =>
      left + ((value - xMin) / (xMax - xMin)) * (right - left);
    const y = (value) =>
      bottom - ((value - yMin) / (yMax - yMin)) * (bottom - top);
    const xZero = x(0);
    const yZero = y(0);
    const ticks = (min, max) =>
      Array.from({ length: 5 }, (_, index) => min + ((max - min) * index) / 4);
    const xTicks = ticks(xMin, xMax)
      .map(
        (value) =>
          `<line x1="${x(value)}" y1="${top}" x2="${x(value)}" y2="${bottom}"/><text x="${x(value)}" y="${bottom + 20}">${escapeHtml(number(value, tickDigits))}</text>`,
      )
      .join("");
    const yTicks = ticks(yMin, yMax)
      .map(
        (value) =>
          `<line x1="${left}" y1="${y(value)}" x2="${right}" y2="${y(value)}"/><text x="${left - 12}" y="${y(value) + 3}" text-anchor="end">${escapeHtml(number(value, tickDigits))}</text>`,
      )
      .join("");
    const toleranceWidth = Math.max(5, Math.abs(x(tolerance) - x(-tolerance)));
    const toleranceHeight = Math.max(5, Math.abs(y(tolerance) - y(-tolerance)));
    const downLabel = scoreMode ? "Trending down" : "Revised down";
    const upLabel = scoreMode ? "Trending up" : "Revised up";
    const quadrants = [
      [left + (xZero - left) / 2, top + 16, downLabel, "Improved"],
      [xZero + (right - xZero) / 2, top + 16, upLabel, "Improved"],
      [left + (xZero - left) / 2, bottom - 24, downLabel, "Worsened"],
      [xZero + (right - xZero) / 2, bottom - 24, upLabel, "Worsened"],
    ]
      .map(
        ([labelX, labelY, direction, outcome]) =>
          `<text class="scatter__quadrant" x="${labelX}" y="${labelY}"><tspan x="${labelX}">${direction}</tspan><tspan x="${labelX}" dy="11">${outcome}</tspan></text>`,
      )
      .join("");
    const actualVolumes = valid
      .map(scatterActual)
      .sort((leftValue, rightValue) => leftValue - rightValue);
    const lowerActual = scatterQuantile(actualVolumes, 0.05);
    const upperActual = Math.max(
      scatterQuantile(actualVolumes, 0.95),
      lowerActual + 1,
    );
    const volumeRange = upperActual - lowerActual;
    const uniformRadius = 7.2;
    const volumeRadius = (actual) => {
      const normalized = Math.max(
        0,
        Math.min(
          1,
          (scatterActual({ actual_kl: actual }) - lowerActual) / volumeRange,
        ),
      );
      return uniformRadius + Math.sqrt(normalized) * 18.45;
    };
    const topVolumeThreshold = scatterQuantile(actualVolumes, 0.9);
    const absoluteRevisions = valid
      .map((row) => Math.abs(row.__scatterX))
      .sort((leftValue, rightValue) => leftValue - rightValue);
    const absoluteImprovements = valid
      .map((row) => Math.abs(row.__scatterY))
      .sort((leftValue, rightValue) => leftValue - rightValue);
    const revisionOutlierThreshold = scatterQuantile(absoluteRevisions, 0.9);
    const improvementOutlierThreshold = scatterQuantile(
      absoluteImprovements,
      0.9,
    );
    const circles = [...valid]
      .sort(
        (leftRow, rightRow) => scatterActual(rightRow) - scatterActual(leftRow),
      )
      .map((row) => {
        const outcome = row.revision_outcome || "neutral";
        const direction = row.revision_direction || "unchanged";
        const actual = scatterActual(row);
        const isTopVolume =
          actual >= topVolumeThreshold && actual > lowerActual;
        const isOutlier =
          Math.abs(row.__scatterX) >= revisionOutlierThreshold ||
          Math.abs(row.__scatterY) >= improvementOutlierThreshold;
        const scoreMode = finite(row.vintage_improvement_score_pp);
        const scatterKey = `${row.parent_code ?? ""}`;
        const accessibleLabel = scoreMode
          ? `${source.toUpperCase()} product ${row.parent_code}, ${monthLabel(row.window_start_month)} through ${monthLabel(row.window_end_month)}, forecast trend ${signedPct(row[xKey])} of actual per vintage, vintage improvement score ${pp(row[yKey])}, ${outcome}`
          : `${source.toUpperCase()} product ${row.parent_code}, ${monthLabel(row.snop_month)}, actual ${kl(row.actual_kl)}, Vintage A ${kl(row.vintage_a_forecast_kl)}, Vintage B ${kl(row.vintage_b_forecast_kl)}, revision ${signedKl(row[xKey])}, error improvement ${signedKl(row[yKey])}, ${outcome}`;
        return `<circle class="chart__point scatter__point scatter--${escapeHtml(outcome)}${isTopVolume ? " scatter__point--top-volume" : ""}" cx="${x(row.__scatterX)}" cy="${y(row.__scatterY)}" r="${uniformRadius}" tabindex="0" role="img" aria-label="${escapeHtml(accessibleLabel)}" data-scatter-key="${escapeHtml(scatterKey)}" data-top-volume="${isTopVolume}" data-outlier="${isOutlier}" data-radius-uniform="${uniformRadius}" data-radius-volume="${volumeRadius(row.actual_kl)}" data-tooltip-kind="revision" data-tooltip-score-mode="${scoreMode ? "vintage-window" : "pair"}" data-tooltip-source="${escapeHtml(source.toUpperCase())}" data-tooltip-code="${escapeHtml(row.parent_code)}" data-tooltip-description="${escapeHtml(row.parent_description || "Description unavailable")}" data-tooltip-brand="${escapeHtml(row.brand || "Unmapped brand")}" data-tooltip-sku-class="${escapeHtml(row.sku_class || "Unclassified")}" data-tooltip-month="${escapeHtml(monthLabel(row.snop_month))}" data-tooltip-window="${escapeHtml(`${monthLabel(row.window_start_month)}–${monthLabel(row.window_end_month)}`)}" data-tooltip-months="${escapeHtml(row.target_months_used)}" data-tooltip-vintages="${escapeHtml(row.vintages_per_month)}" data-tooltip-transitions="${escapeHtml(row.transitions_used)}" data-tooltip-winsorized="${escapeHtml(row.winsorized_months)}" data-tooltip-improving="${escapeHtml(row.improving_months)}" data-tooltip-degrading="${escapeHtml(row.degrading_months)}" data-tooltip-neutral="${escapeHtml(row.neutral_months)}" data-tooltip-direction="${escapeHtml(labelize(direction))}" data-tooltip-revision="${escapeHtml(scoreMode ? signedPct(row[xKey]) : signedKl(row[xKey]))}" data-tooltip-raw-revision="${escapeHtml(scoreMode ? signedPct(row.raw_revision_score_pct) : signedKl(row[xKey]))}" data-tooltip-improvement="${escapeHtml(scoreMode ? pp(row[yKey]) : signedKl(row[yKey]))}" data-tooltip-raw-improvement="${escapeHtml(scoreMode ? pp(row.raw_vintage_improvement_score_pp) : signedKl(row[yKey]))}" data-tooltip-improvement-raw="${escapeHtml(row[yKey])}" data-tooltip-actual="${escapeHtml(kl(row.actual_kl))}" data-tooltip-vintage-a="${escapeHtml(kl(row.vintage_a_forecast_kl))}" data-tooltip-vintage-a-scope="${escapeHtml(`M−${row.vintage_a_horizon_months ?? "—"} · ${monthLabel(row.vintage_a_calculation_month)}`)}" data-tooltip-vintage-b="${escapeHtml(kl(row.vintage_b_forecast_kl))}" data-tooltip-vintage-b-scope="${escapeHtml(`M−${row.vintage_b_horizon_months ?? "—"} · ${monthLabel(row.vintage_b_calculation_month)}`)}" data-tooltip-error-a="${escapeHtml(kl(row.vintage_a_absolute_error_kl))}" data-tooltip-error-b="${escapeHtml(kl(row.vintage_b_absolute_error_kl))}" data-tooltip-outcome="${escapeHtml(labelize(outcome))}"></circle>`;
      })
      .join("");
    const density = scatterDensity(valid, x, y, left, right, top, bottom);
    const xAxisTitle = scoreMode
      ? "Median forecast trend · % of actual per vintage"
      : "Forecast revision · Vintage B − Vintage A (KL)";
    const yAxisTitle = scoreMode
      ? "Vintage improvement score · FA pp per vintage"
      : "Error improvement · |A − actual| − |B − actual| (KL)";
    const scoreEvidence = scoreMode
      ? `<span>One parent · 6 target months × 5 vintages</span><span>Seasonal extremes retained · six-month median</span>`
      : `<span>Tolerance ±${escapeHtml(number(tolerance, 2))} KL</span>`;
    return `<div class="revision-scatter" data-revision-scatter data-scatter-mode="${revisionScatterMode}" data-scatter-density="${revisionScatterDensity ? "on" : "off"}" data-scatter-focus="${revisionScatterFocus}"><div class="scatter-toolbar" role="toolbar" aria-label="Scatter chart display controls"><span class="scatter-toolbar__label">View</span>${scatterControl("mode-uniform", "Uniform dots", revisionScatterMode === "uniform", 'data-scatter-mode="uniform"')}${scatterControl("mode-volume", "Size by volume", revisionScatterMode === "volume", 'data-scatter-mode="volume"')}${scatterControl("density", "Density", revisionScatterDensity, "data-scatter-density")}${scatterControl("focus-top", "Top volume", revisionScatterFocus === "top-volume", 'data-scatter-focus="top-volume"')}${scatterControl("focus-outliers", "Outliers", revisionScatterFocus === "outliers", 'data-scatter-focus="outliers"')}${scatterSkuClassSelect(rows)}<span class="scatter-toolbar__spacer"></span><button class="scatter-control" type="button" data-scatter-action="zoom-out" aria-label="Zoom out">−</button><span class="scatter-toolbar__zoom" data-scatter-zoom-value>${revisionScatterZoom}×</span><button class="scatter-control" type="button" data-scatter-action="zoom-in" aria-label="Zoom in">+</button><button class="scatter-control" type="button" data-scatter-action="zoom-reset">Reset view</button><button class="scatter-control" type="button" data-scatter-action="clear-selection">Clear selection</button></div><svg class="chart chart--revision-scatter" viewBox="0 0 ${width} ${height}" data-base-width="${width}" data-base-height="${height}" data-zoom-center-x="${xZero}" data-zoom-center-y="${yZero}" role="img" aria-label="${escapeHtml(label)}"><rect class="scatter__tolerance" x="${xZero - toleranceWidth / 2}" y="${top}" width="${toleranceWidth}" height="${bottom - top}"/><rect class="scatter__tolerance" x="${left}" y="${yZero - toleranceHeight / 2}" width="${right - left}" height="${toleranceHeight}"/><g class="chart__grid scatter__grid">${xTicks}${yTicks}</g>${density}${quadrants}<line class="zero-line" x1="${xZero}" y1="${top}" x2="${xZero}" y2="${bottom}"/><line class="zero-line" x1="${left}" y1="${yZero}" x2="${right}" y2="${yZero}"/><g class="scatter__crosshair" aria-hidden="true"><line class="scatter__crosshair-x" x1="${xZero}" y1="${top}" x2="${xZero}" y2="${bottom}"/><line class="scatter__crosshair-y" x1="${left}" y1="${yZero}" x2="${right}" y2="${yZero}"/></g><g class="scatter">${circles}</g><text class="scatter__axis-title" x="${(left + right) / 2}" y="${height - 17}">${escapeHtml(xAxisTitle)}</text><text class="scatter__axis-title" x="18" y="${(top + bottom) / 2}" transform="rotate(-90 18 ${(top + bottom) / 2})">${escapeHtml(yAxisTitle)}</text></svg><div class="revision-scatter__legend"><span><i class="scatter-key scatter-key--improved"></i>Improved</span><span><i class="scatter-key scatter-key--worsened"></i>Worsened</span><span><i class="scatter-key scatter-key--neutral"></i>Neutral</span><span><i class="scatter-key scatter-key--density"></i>Density</span><span><i class="scatter-key scatter-key--size"></i><span data-scatter-size-label>${revisionScatterMode === "volume" ? "Size = actual volume (capped √ scaled)" : "Top-volume points outlined; size off"}</span></span>${scoreEvidence}<span>Wheel / + − zoom · drag pan · Shift-drag select</span>${revisionScatterSelection.size ? "<span>Selected parents highlighted · others stay pale for context</span>" : ""}</div></div>`;
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
    const request = buildProductRequest();
    await fetchModule("product", request);
  }

  function buildProductRequest() {
    return {
      ...currentRequest,
      product_parent_code:
        Number(
          document.querySelector('[data-product-control="parent"]').value,
        ) || null,
      product_target_month:
        document.querySelector('[data-product-control="month"]').value || null,
    };
  }

  function renderExceptions(payload) {
    const exceptions = payload.exceptions || { rows: [], total: 0 };
    const rows = exceptions.rows || [];
    setHtml(
      document.querySelector("[data-exception-summary]"),
      [
        populationItem("Active rows", count(exceptions.total)),
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
    const rows = (currentPayload.exceptions?.rows || [])
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
    if (!quality) return;
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
          const help = {
            hierarchy: [
              "Shows how many observations have a valid product hierarchy mapping out of all observations checked.",
              "Unmapped or ambiguous products can be excluded from grouped analysis or appear under fallback labels, so review exceptions before using brand or parent-level conclusions.",
            ],
            actual: [
              "Shows how many observations have matched, positive actual demand available for accuracy calculations.",
              "Missing or zero actuals remain visible as quality evidence but cannot contribute to ratio-based forecast accuracy and revision metrics.",
            ],
            pairs: [
              "Shows how many product-target-month observations have both selected forecast vintages and a valid actual.",
              "A complete pair is the basic comparison unit used by vintage accuracy, revision effectiveness, and total error improvement.",
            ],
            source_availability: [
              "Shows how many product-target-month observations are available from both TM and ML sources.",
              "Only both-source observations can enter a like-for-like source comparison; source-only rows remain coverage evidence.",
            ],
          }[category];
          return `<article class="qcard"><div class="qcard__top"><p class="qcard__k">${labels[category]}</p><span class="severity ${detail.has_attention ? "severity--warn" : "severity--good"}">${detail.has_attention ? "Review" : "Ready"}</span>${kpiHelp(labels[category], help)}</div><strong class="qcard__v">${count(good?.observations || 0)} / ${count(total)}</strong><p class="qcard__cap">${count(bad)} observations outside the good status</p></article>`;
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
    revisionQueueSearch = "";
    revisionQueueSort = { key: "impact_kl", direction: "desc" };
    revisionScatterMode = "uniform";
    revisionScatterDensity = true;
    revisionScatterFocus = "all";
    revisionScatterSkuClass = "all";
    revisionScatterZoom = 1;
    revisionScatterSelection = new Set();
    revisionScatterPan = { x: 0, y: 0 };
    applyRequestToControls(defaults);
    document.querySelectorAll("[data-metric-selector]").forEach((select) => {
      select.selectedIndex = 0;
    });
    document.querySelector("[data-exception-search]").value = "";
    document.querySelector("[data-exception-limit]").value = "10";
    document.querySelector(".baseline").open = false;
    activate("overview");
    activateSubpanel("comparison", "revision");
    activateSubpanel("history", "product");
    activateSubpanel("quality", "hierarchy");
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
    setScopeDrawerOpen(scopeDrawer.hidden, scopeButton);
  });
  chartDialogClose.addEventListener("click", closeChartDialog);
  fullscreenFilters.addEventListener("click", () => {
    setScopeDrawerOpen(scopeDrawer.hidden, fullscreenFilters);
  });
  document
    .querySelector('[data-action="reset"]')
    .addEventListener("click", resetDashboard);
  timeline?.querySelectorAll("[data-timeline-grain]").forEach((button) => {
    button.addEventListener("click", () => {
      timelineState.grain = button.dataset.timelineGrain;
      updateTimelineUi(
        currentPayload?.options.target_months || [],
        controls.get("target_start").value,
        controls.get("target_end").value,
      );
    });
  });
  timeline?.querySelectorAll("[data-timeline-months]").forEach((button) => {
    button.addEventListener("click", () => {
      applyTimelinePreset(
        currentPayload?.options.target_months || [],
        button.dataset.timelineMonths,
      );
      scheduleRefresh({ immediate: true });
    });
  });
  function applyTimelineHandle(kind) {
    const months = currentPayload?.options.target_months || [];
    let startIndex = Number(timelineStartSlider.value);
    let endIndex = Number(timelineEndSlider.value);
    if (kind === "start" && startIndex > endIndex) endIndex = startIndex;
    if (kind === "end" && endIndex < startIndex) startIndex = endIndex;
    const range = ForecastTimeline.rangeFromIndices(
      months,
      startIndex,
      endIndex,
    );
    setTimelineRange(months, range.start, range.end);
  }
  timelineStartSlider?.addEventListener("input", () =>
    applyTimelineHandle("start"),
  );
  timelineEndSlider?.addEventListener("input", () =>
    applyTimelineHandle("end"),
  );
  timelineStartSlider?.addEventListener("change", () =>
    scheduleRefresh({ immediate: true }),
  );
  timelineEndSlider?.addEventListener("change", () =>
    scheduleRefresh({ immediate: true }),
  );

  function moveTimelineWindow(delta) {
    const months = currentPayload?.options.target_months || [];
    const moved = ForecastTimeline.moveWindow(
      months,
      Number(timelineStartSlider.value),
      Number(timelineEndSlider.value),
      delta,
    );
    const range = ForecastTimeline.rangeFromIndices(
      months,
      moved.start,
      moved.end,
    );
    setTimelineRange(months, range.start, range.end);
  }
  timelineSelection?.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
    event.preventDefault();
    moveTimelineWindow(event.key === "ArrowLeft" ? -1 : 1);
    scheduleRefresh({ immediate: true });
  });
  timelineSelection?.addEventListener("pointerdown", (event) => {
    timelineWindowDrag = {
      pointerId: event.pointerId,
      originX: event.clientX,
      start: Number(timelineStartSlider.value),
      end: Number(timelineEndSlider.value),
    };
    timelineSelection.setPointerCapture(event.pointerId);
  });
  timelineSelection?.addEventListener("pointermove", (event) => {
    if (!timelineWindowDrag || event.pointerId !== timelineWindowDrag.pointerId)
      return;
    const width = timelineRail.getBoundingClientRect().width;
    const steps = Number(timelineEndSlider.max) || 1;
    const delta = Math.round(
      ((event.clientX - timelineWindowDrag.originX) / width) * steps,
    );
    const moved = ForecastTimeline.moveWindow(
      currentPayload?.options.target_months || [],
      timelineWindowDrag.start,
      timelineWindowDrag.end,
      delta,
    );
    const range = ForecastTimeline.rangeFromIndices(
      currentPayload?.options.target_months || [],
      moved.start,
      moved.end,
    );
    setTimelineRange(
      currentPayload?.options.target_months || [],
      range.start,
      range.end,
    );
  });
  const endTimelineWindowDrag = (event) => {
    if (!timelineWindowDrag || event.pointerId !== timelineWindowDrag.pointerId)
      return;
    timelineWindowDrag = null;
    scheduleRefresh({ immediate: true });
  };
  timelineSelection?.addEventListener("pointerup", endTimelineWindowDrag);
  timelineSelection?.addEventListener("pointercancel", endTimelineWindowDrag);

  controls.forEach((control, name) => {
    const applyControlChange = () => {
      if (["source", "comparison_mode"].includes(name))
        controls.get("horizon").value = "";
      if (name === "target_start") {
        const end = controls.get("target_end");
        if (control.value > end.value) end.value = control.value;
        updateTimelineUi(
          currentPayload?.options.target_months || [],
          control.value,
          end.value,
        );
      } else if (name === "target_end") {
        const start = controls.get("target_start");
        if (control.value < start.value) start.value = control.value;
        updateTimelineUi(
          currentPayload?.options.target_months || [],
          start.value,
          control.value,
        );
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
    };
    control.addEventListener("change", () => {
      applyControlChange();
      scheduleRefresh({
        immediate: !control.matches('input[type="number"], input[type="text"]'),
      });
    });
    if (control.matches('input[type="number"], input[type="text"]')) {
      control.addEventListener("input", () => {
        applyControlChange();
        scheduleRefresh();
      });
    }
  });
  document.querySelectorAll("[data-metric-selector]").forEach((select) => {
    select.addEventListener("change", () => {
      if (!currentPayload) return;
      if (select.dataset.metricSelector === "heatmap") {
        if (moduleStates.get("heatmap")?.status === "fresh")
          renderTrendHeatmap(currentPayload);
      } else if (moduleStates.get("trends")?.status === "fresh") {
        renderTrends(currentPayload, { heatmap: false });
      }
    });
  });
  document
    .querySelector("[data-exception-search]")
    .addEventListener("input", renderExceptionRows);
  document.addEventListener("input", (event) => {
    if (!event.target.matches?.("[data-revision-action-search]")) return;
    revisionQueueSearch = event.target.value;
    renderRevisionActionQueue();
  });
  document.addEventListener("change", (event) => {
    if (!event.target.matches?.("[data-scatter-sku-class]")) return;
    revisionScatterSkuClass = event.target.value || "all";
    revisionScatterZoom = 1;
    revisionScatterPan = { x: 0, y: 0 };
    revisionScatterSelection = new Set();
    revisionDrilldownPayload = null;
    if (revisionDrilldownBasePayload)
      renderRevisionPanel(revisionDrilldownBasePayload);
    if (fullscreenChart === "revision") renderFullscreenChart();
  });
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
  document.addEventListener("pointerdown", (event) => {
    const svg = event.target.closest?.(".chart--revision-scatter");
    if (svg) beginScatterDrag(svg, event);
  });
  document.addEventListener("pointermove", (event) => {
    moveScatterDrag(event);
    const point = event.target.closest?.(".chart__point");
    if (point && !chartTooltip.hidden) positionChartTooltip(event, point);
  });
  document.addEventListener("pointerup", endScatterDrag);
  document.addEventListener("pointercancel", endScatterDrag);
  document.addEventListener(
    "wheel",
    (event) => {
      const svg = event.target.closest?.(".chart--revision-scatter");
      if (!svg) return;
      event.preventDefault();
      revisionScatterZoom = Math.max(
        1,
        Math.min(3, revisionScatterZoom + (event.deltaY < 0 ? 1 : -1)),
      );
      refreshScatterCharts();
    },
    { passive: false },
  );
  document.addEventListener("pointerover", (event) => {
    const point = event.target.closest?.(".chart__point");
    if (point) {
      showChartTooltip(point, event);
      if (point.closest(".chart--revision-scatter"))
        setScatterCrosshair(point, true);
    }
  });
  document.addEventListener("pointerout", (event) => {
    const point = event.target.closest?.(".chart__point");
    if (point && event.relatedTarget !== point) {
      hideChartTooltip(point);
      if (point.closest(".chart--revision-scatter"))
        setScatterCrosshair(point, false);
    }
  });
  document.addEventListener("focusin", (event) => {
    const point = event.target.closest?.(".chart__point");
    if (point) {
      showChartTooltip(point, event);
      if (point.closest(".chart--revision-scatter"))
        setScatterCrosshair(point, true);
    }
  });
  document.addEventListener("focusout", (event) => {
    const point = event.target.closest?.(".chart__point");
    if (point) {
      hideChartTooltip(point);
      if (point.closest(".chart--revision-scatter"))
        setScatterCrosshair(point, false);
    }
  });
  document.addEventListener("click", (event) => {
    const drilldownCategory = event.target.closest?.(
      "[data-drilldown-category]",
    );
    if (drilldownCategory) {
      openRevisionDrilldown(
        drilldownCategory.dataset.drilldownCategory,
        drilldownCategory,
      );
      return;
    }
    const drilldownRow = event.target.closest?.("[data-drilldown-parent-code]");
    if (drilldownRow) {
      updateRevisionParentSelection(
        drilldownRow.dataset.drilldownParentCode,
        event.shiftKey || event.ctrlKey || event.metaKey,
      );
      return;
    }
    if (event.target.closest?.("[data-drilldown-close]")) {
      closeRevisionDrilldown({ restoreFocus: true });
      return;
    }
    if (event.target.closest?.("[data-drilldown-clear]")) {
      revisionScatterSelection = new Set();
      refreshRevisionDrilldownPopover();
      void refreshRevisionDrilldown();
      return;
    }
    if (
      !revisionDrilldownPopover.hidden &&
      !event.target.closest?.(".revision-drilldown-popover")
    ) {
      closeRevisionDrilldown();
    }
    const scatterPoint = event.target.closest?.(".scatter__point");
    if (scatterPoint) {
      updateScatterSelection(
        scatterPoint,
        event.shiftKey || event.ctrlKey || event.metaKey,
      );
      return;
    }
    const scatterAction = event.target.closest?.("[data-scatter-action]");
    if (scatterAction) {
      const action = scatterAction.dataset.scatterAction;
      if (action === "mode-uniform") revisionScatterMode = "uniform";
      else if (action === "mode-volume") revisionScatterMode = "volume";
      else if (action === "density")
        revisionScatterDensity = !revisionScatterDensity;
      else if (action === "focus-top")
        revisionScatterFocus =
          revisionScatterFocus === "top-volume" ? "all" : "top-volume";
      else if (action === "focus-outliers")
        revisionScatterFocus =
          revisionScatterFocus === "outliers" ? "all" : "outliers";
      else if (action === "zoom-in")
        revisionScatterZoom = Math.min(3, revisionScatterZoom + 1);
      else if (action === "zoom-out")
        revisionScatterZoom = Math.max(1, revisionScatterZoom - 1);
      else if (action === "zoom-reset") {
        revisionScatterZoom = 1;
        revisionScatterPan = { x: 0, y: 0 };
      } else if (action === "clear-selection") {
        revisionScatterSelection = new Set();
        refreshRevisionDrilldownPopover();
        void refreshRevisionDrilldown();
        return;
      }
      refreshScatterCharts();
      return;
    }
    const fullscreenButton = event.target.closest("[data-chart-fullscreen]");
    if (fullscreenButton) {
      openChartDialog(
        fullscreenButton.dataset.chartFullscreen,
        fullscreenButton,
      );
      return;
    }
    const revisionSortButton = event.target.closest("[data-revision-sort]");
    if (revisionSortButton) {
      const key = revisionSortButton.dataset.revisionSort;
      revisionQueueSort = {
        key,
        direction:
          revisionQueueSort.key === key &&
          revisionQueueSort.direction === "desc"
            ? "asc"
            : "desc",
      };
      renderRevisionActionQueue();
      return;
    }
    const exportButton = event.target.closest("[data-export-kind]");
    if (exportButton) exportCsv(exportButton);
    const modeButton = event.target.closest("[data-mode-action]");
    if (modeButton?.dataset.modeAction === "comparison") {
      controls.get("comparison_mode").value = "true";
      controls.get("horizon").value = "";
      scheduleRefresh({ immediate: true });
    } else if (modeButton?.dataset.modeAction === "single") {
      controls.get("comparison_mode").value = "false";
      controls.get("horizon").value = "";
      scheduleRefresh({ immediate: true });
    } else if (modeButton?.dataset.modeAction === "filters") {
      setScopeDrawerOpen(true, scopeButton);
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (!chartTooltip.hidden) hideChartTooltip(document.activeElement);
    if (!revisionDrilldownPopover.hidden) {
      closeRevisionDrilldown({ restoreFocus: true });
      return;
    }
    if (!scopeDrawer.hidden) {
      closeScopeDrawer({ restoreFocus: true });
      return;
    }
    if (!chartDialog.hidden) closeChartDialog();
  });
  window.addEventListener("resize", () => {
    if (!revisionDrilldownPopover.hidden && revisionDrilldownTrigger)
      positionRevisionDrilldown(revisionDrilldownTrigger);
  });
  window.addEventListener("hashchange", () => {
    const id = location.hash.slice(1);
    if (validTabs.has(id)) activate(id, { historyMode: "none" });
  });

  if ("ResizeObserver" in window) {
    overviewResizeObserver = new ResizeObserver(scheduleOverviewChartRender);
    document
      .querySelectorAll(
        "[data-overview-chart], [data-overview-volume-chart], [data-overview-chart-fullscreen], [data-trend-chart]",
      )
      .forEach((container) => overviewResizeObserver.observe(container));
  } else {
    window.addEventListener("resize", scheduleOverviewChartRender);
  }

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
      markModulesStale();
      syncControls(payload);
      renderCompact(payload);
      void ensureActiveModules();
    } catch (error) {
      showToast(error.message, true);
      renderError(error.message);
    } finally {
      setLoading(false);
    }
  }

  start();
})();
