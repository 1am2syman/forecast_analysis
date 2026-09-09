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
  const scopeButtons = Array.from(
    document.querySelectorAll('[data-action="scope"]'),
  );
  const scopeButton = scopeButtons[0];
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
  const vintageGapDialog = document.querySelector("#vintage-gap-dialog");
  const vintageGapBody = vintageGapDialog.querySelector(
    "[data-vintage-gap-body]",
  );
  const vintageGapClose = vintageGapDialog.querySelector(
    '[data-action="vintage-gap-close"]',
  );
  const vintageSelectorTriggers = Array.from(
    document.querySelectorAll("[data-vintage-selector-trigger]"),
  );
  const vintageSelectorPopover = document.createElement("div");
  vintageSelectorPopover.className = "vintage-selector";
  vintageSelectorPopover.setAttribute("role", "dialog");
  vintageSelectorPopover.setAttribute(
    "aria-label",
    "Forecast vintage comparison",
  );
  vintageSelectorPopover.hidden = true;
  document.body.append(vintageSelectorPopover);
  const fullscreenFilters = chartDialog.querySelector(
    '[data-action="fullscreen-filters"]',
  );
  const controls = new Map(
    Array.from(document.querySelectorAll("[data-control]")).map((control) => [
      control.dataset.control,
      control,
    ]),
  );
  const productFilters = new Map();
  for (const root of document.querySelectorAll("[data-product-filter]")) {
    const name = root.dataset.productFilter;
    let filter = null;
    filter = FilterMultiSelect.create(root, {
      onChange: (selected) => {
        for (const candidate of productFilters.get(name)) {
          if (candidate !== filter) candidate.setValue(selected);
        }
        scheduleRefresh({ immediate: true });
      },
    });
    if (!productFilters.has(name)) productFilters.set(name, []);
    productFilters.get(name).push(filter);
  }
  const timelines = Array.from(
    document.querySelectorAll("[data-timeline-control]"),
  ).map((root) => ({
    root,
    startSlider: root.querySelector("[data-timeline-start-slider]"),
    endSlider: root.querySelector("[data-timeline-end-slider]"),
    rail: root.querySelector("[data-timeline-rail]"),
    selection: root.querySelector("[data-timeline-selection]"),
    startSelect: root.querySelector("[data-timeline-start-select]"),
    endSelect: root.querySelector("[data-timeline-end-select]"),
  }));
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
  let fullscreenChartMode = "single";
  let fullscreenTrigger = null;
  let vintageSelectorTrigger = null;
  let revisionQueueSource = null;
  let revisionQueueRows = [];
  let revisionQueueSearch = "";
  let revisionQueueSort = { key: "impact_kl", direction: "desc" };
  let overviewResizeFrame = null;
  let overviewResizeObserver = null;
  let revisionScatterMode = "error";
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
  let revisionEffectivenessTrigger = null;
  let revisionEffectivenessGuideTrigger = null;
  let revisionScatterGuideTrigger = null;
  let comparisonKpiGuideTrigger = null;
  let overviewGuideTrigger = null;
  let vintageGapPayload = null;
  let yearOverlayVisible = new Set();
  let yearOverlayKey = "";
  let yearOverlayMode = "fy";
  let yearOverlayClickTimer = null;
  let vintageGapMode = "fixes";
  let vintageGapSelectedBrand = null;
  let vintageGapSelectedParent = null;
  let vintageGapShowAll = false;
  let vintageGapBrandSearch = "";
  let vintageGapParentSearch = "";
  let vintageGapTrigger = null;
  let vintageGapController = null;

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
  const ACCURACY_VINTAGE_COLORS = [
    "#9a5e00",
    "#2e79a5",
    "#7c4d9e",
    "#b63b35",
    "#667b24",
  ];
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
    forecast_kl: "Forecast compared with actual demand",
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
    const isRevisionEffectivenessPoint =
      point.dataset.tooltipKind === "revision-effectiveness";
    const isRevisionEffectivenessSegment =
      point.dataset.tooltipKind === "revision-effectiveness-segment";
    const isRevisionActionSparkline =
      point.dataset.tooltipKind === "revision-action-sparkline";
    const isYearOverlay = point.dataset.tooltipKind === "year-overlay";
    const yearOverlaySeriesRows = (() => {
      try {
        return JSON.parse(point.dataset.tooltipYearSeries || "[]");
      } catch {
        return [];
      }
    })();
    const vintageAccuracyRows = (() => {
      try {
        return JSON.parse(point.dataset.tooltipVintageSeries || "[]");
      } catch {
        return [];
      }
    })();
    const vintageAccuracyContent = vintageAccuracyRows.length
      ? vintageAccuracyRows
          .map(
            (series) =>
              `<div><dt>${escapeHtml(series.label)}${series.fixed ? " · fixed" : ""}</dt><dd>${escapeHtml(series.value)}</dd></div>`,
          )
          .join("")
      : `<div><dt>Vintage A accuracy</dt><dd>${escapeHtml(point.dataset.tooltipVintageA)}</dd></div><div><dt>Vintage B accuracy</dt><dd>${escapeHtml(point.dataset.tooltipVintageB)}</dd></div>`;
    const vintageAccuracyEvidence = vintageAccuracyRows.length
      ? `<div><dt>Common cohort</dt><dd>${escapeHtml(point.dataset.tooltipCommonCohort)} parents</dd></div><div><dt>Actual denominator</dt><dd>${escapeHtml(point.dataset.tooltipActualDenominator)}</dd></div>`
      : "";
    const volumeVintageRows = (() => {
      try {
        return JSON.parse(point.dataset.tooltipVolumeSeries || "[]");
      } catch {
        return [];
      }
    })();
    const volumeVintageContent = volumeVintageRows
      .map(
        (series) =>
          `<div><dt>${escapeHtml(series.label)}${series.fixed ? " · fixed" : ""}</dt><dd>${escapeHtml(series.value)}</dd></div>`,
      )
      .join("");
    const monthlyContent = isVolumeSummary
      ? `<div class="chart-tooltip__head"><strong>${escapeHtml(point.dataset.tooltipMonth)}</strong><span>${escapeHtml(point.dataset.tooltipSource)}</span></div><dl>${volumeVintageContent}<div><dt>Actual</dt><dd>${escapeHtml(point.dataset.tooltipActual)}</dd></div><div><dt>Latest − actual</dt><dd>${escapeHtml(point.dataset.tooltipVariance)}</dd></div></dl>`
      : `<div class="chart-tooltip__head"><strong>${escapeHtml(point.dataset.tooltipMonth)}</strong><span>${escapeHtml(point.dataset.tooltipSource)}</span></div><dl>${vintageAccuracyContent}${vintageAccuracyEvidence}<div><dt>${escapeHtml(point.dataset.tooltipBiasLabel || "Latest forecast bias")}</dt><dd class="${Number(point.dataset.tooltipBiasRaw) >= 0 ? "chart-tooltip__over" : "chart-tooltip__under"}">${escapeHtml(point.dataset.tooltipBias)}</dd></div></dl><p class="chart-tooltip__action">${point.dataset.vintageGapEnabled === "true" ? "Click for WAPE gap drivers" : "Select a historical vintage for gap drivers"}</p>`;
    const revisionPairContent = `<div class="chart-tooltip__head"><strong>${escapeHtml(point.dataset.tooltipCode)}</strong><span>${escapeHtml(point.dataset.tooltipSource)}</span></div><p class="chart-tooltip__description">${escapeHtml(point.dataset.tooltipDescription)}</p><div class="chart-tooltip__meta"><span>${escapeHtml(point.dataset.tooltipMonth)}</span><span>${escapeHtml(point.dataset.tooltipBrand)}</span><span>${escapeHtml(point.dataset.tooltipDirection)} · ${escapeHtml(point.dataset.tooltipOutcome)}</span></div><dl><div><dt>Actual volume</dt><dd>${escapeHtml(point.dataset.tooltipActual)}</dd></div><div><dt>Vintage A forecast</dt><dd>${escapeHtml(point.dataset.tooltipVintageA)}<small>${escapeHtml(point.dataset.tooltipVintageAScope)}</small></dd></div><div><dt>Vintage B forecast</dt><dd>${escapeHtml(point.dataset.tooltipVintageB)}<small>${escapeHtml(point.dataset.tooltipVintageBScope)}</small></dd></div><div><dt>Error before revision</dt><dd>${escapeHtml(point.dataset.tooltipErrorA)}</dd></div><div><dt>Error after revision</dt><dd>${escapeHtml(point.dataset.tooltipErrorB)}</dd></div><div><dt>Forecast revision</dt><dd>${escapeHtml(point.dataset.tooltipRevision)}</dd></div><div class="chart-tooltip__result"><dt>Error improvement</dt><dd class="${Number(point.dataset.tooltipImprovementRaw) >= 0 ? "good" : "bad"}">${escapeHtml(point.dataset.tooltipImprovement)}</dd></div></dl>`;
    const revisionScoreContent = `<div class="chart-tooltip__head"><strong>${escapeHtml(point.dataset.tooltipCode)}</strong><span>${escapeHtml(point.dataset.tooltipSource)}</span></div><p class="chart-tooltip__description">${escapeHtml(point.dataset.tooltipDescription)}</p><div class="chart-tooltip__meta"><span>${escapeHtml(point.dataset.tooltipWindow)}</span><span>${escapeHtml(point.dataset.tooltipBrand)}</span><span>SKU class ${escapeHtml(point.dataset.tooltipSkuClass)}</span><span>${escapeHtml(point.dataset.tooltipDirection)} · ${escapeHtml(point.dataset.tooltipOutcome)}</span></div><dl><div><dt>Latest-vintage absolute error</dt><dd>${escapeHtml(point.dataset.tooltipAbsoluteError)}<small>summed across six target months</small></dd></div><div><dt>Six-month actual volume</dt><dd>${escapeHtml(point.dataset.tooltipActual)}</dd></div><div><dt>Evidence window</dt><dd>${escapeHtml(point.dataset.tooltipMonths)} target months<small>${escapeHtml(point.dataset.tooltipVintages)} vintages per month · ${escapeHtml(point.dataset.tooltipTransitions)} vintage changes</small></dd></div><div><dt>Improving months</dt><dd>${escapeHtml(point.dataset.tooltipImproving)}<small>${escapeHtml(point.dataset.tooltipDegrading)} degrading · ${escapeHtml(point.dataset.tooltipNeutral)} neutral</small></dd></div><div><dt>Forecast trend</dt><dd>${escapeHtml(point.dataset.tooltipRevision)}<small>median monthly trend · % of actual per vintage</small></dd></div><div class="chart-tooltip__result"><dt>Vintage improvement score</dt><dd class="${Number(point.dataset.tooltipImprovementRaw) >= 0 ? "good" : "bad"}">${escapeHtml(point.dataset.tooltipImprovement)}<small>median monthly FA change · pp per vintage</small></dd></div></dl>`;
    const revisionContent =
      point.dataset.tooltipScoreMode === "vintage-window"
        ? revisionScoreContent
        : revisionPairContent;
    const revisionHistoryContent = `<div class="chart-tooltip__head"><strong>${escapeHtml(point.dataset.tooltipMonth)}</strong><span>${escapeHtml(point.dataset.tooltipSource)}</span></div><p>Oldest → latest forecast version</p><dl><div><dt>Net FA vs oldest</dt><dd class="${Number(point.dataset.tooltipNetFaRaw) >= 0 ? "good" : "bad"}">${escapeHtml(point.dataset.tooltipNetFa)}</dd></div><div><dt>Net error improvement</dt><dd>${escapeHtml(point.dataset.tooltipNetErrorImprovement)}</dd></div><div><dt>Delta vs oldest</dt><dd>${escapeHtml(point.dataset.tooltipDelta)}</dd></div><div><dt>Forecast accuracy</dt><dd>${escapeHtml(point.dataset.tooltipOldestAccuracy)}<small>to ${escapeHtml(point.dataset.tooltipLatestAccuracy)}</small></dd></div><div><dt>Forecast volume</dt><dd>${escapeHtml(point.dataset.tooltipOldestForecast)}<small>to ${escapeHtml(point.dataset.tooltipLatestForecast)}</small></dd></div><div><dt>Forecast versions</dt><dd>${escapeHtml(point.dataset.tooltipVintages)}</dd></div><div><dt>Fixed cohort</dt><dd>${escapeHtml(point.dataset.tooltipProducts)} products</dd></div><div><dt>Version range</dt><dd>${escapeHtml(point.dataset.tooltipOldestVersion)}<small>to ${escapeHtml(point.dataset.tooltipLatestVersion)}</small></dd></div></dl>`;
    const revisionHistorySegmentContent = `<div class="chart-tooltip__head"><strong>${escapeHtml(point.dataset.tooltipMonth)}</strong><span>${escapeHtml(point.dataset.tooltipSource)}</span></div><p>${escapeHtml(point.dataset.tooltipPreviousVersion)} → ${escapeHtml(point.dataset.tooltipVersion)}</p><div class="chart-tooltip__meta"><span>${escapeHtml(point.dataset.tooltipOutcome)} FA</span></div><dl><div><dt>FA change</dt><dd class="${Number(point.dataset.tooltipFaRaw) >= 0 ? "good" : "bad"}">${escapeHtml(point.dataset.tooltipFa)}</dd></div><div><dt>Error improvement</dt><dd>${escapeHtml(point.dataset.tooltipErrorImprovement)}</dd></div><div><dt>Absolute error</dt><dd>${escapeHtml(point.dataset.tooltipPreviousError)}<small>to ${escapeHtml(point.dataset.tooltipError)}</small></dd></div><div><dt>Forecast revision</dt><dd>${escapeHtml(point.dataset.tooltipRevision)}</dd></div><div><dt>Forecast volume</dt><dd>${escapeHtml(point.dataset.tooltipPreviousForecast)}<small>to ${escapeHtml(point.dataset.tooltipForecast)}</small></dd></div></dl>`;
    const revisionEffectivenessContent = `<div class="chart-tooltip__head"><strong>${escapeHtml(point.dataset.tooltipMonth)} · V${escapeHtml(point.dataset.tooltipVintage)}</strong><span>${escapeHtml(point.dataset.tooltipSource)}</span></div><p>Click to open the detailed breakdown.</p><dl><div><dt>Balanced score</dt><dd>${escapeHtml(point.dataset.tooltipScore)}</dd></div><div><dt>Change from prior vintage</dt><dd>${escapeHtml(point.dataset.tooltipScoreChange)}</dd></div><div><dt>Accuracy gain</dt><dd>${escapeHtml(point.dataset.tooltipAccuracyScore)}</dd></div><div><dt>Revision efficiency</dt><dd>${escapeHtml(point.dataset.tooltipEfficiencyScore)}</dd></div><div><dt>Consistency</dt><dd>${escapeHtml(point.dataset.tooltipConsistencyScore)}</dd></div><div><dt>Cumulative error change</dt><dd>${escapeHtml(point.dataset.tooltipErrorRemoved)}</dd></div><div><dt>Cumulative movement</dt><dd>${escapeHtml(point.dataset.tooltipMovement)}</dd></div></dl>`;
    const revisionActionSparklineContent = `<div class="chart-tooltip__head"><strong>${escapeHtml(point.dataset.tooltipCode)}</strong><span>${escapeHtml(point.dataset.tooltipSource)}</span></div><p>${escapeHtml(point.dataset.tooltipMonth)} · monthly error improvement</p><dl><div><dt>Error improvement</dt><dd class="${Number(point.dataset.tooltipImprovementRaw) >= 0 ? "good" : "bad"}">${escapeHtml(point.dataset.tooltipImprovement)}</dd></div><div><dt>Actual volume</dt><dd>${escapeHtml(point.dataset.tooltipActual)}</dd></div><div><dt>Forecast revision</dt><dd>${escapeHtml(point.dataset.tooltipRevision)}</dd></div><div><dt>Outcome</dt><dd>${escapeHtml(point.dataset.tooltipOutcome)}</dd></div></dl>`;
    const overlayMonth = [
      "Jan",
      "Feb",
      "Mar",
      "Apr",
      "May",
      "Jun",
      "Jul",
      "Aug",
      "Sep",
      "Oct",
      "Nov",
      "Dec",
    ][Number(point.dataset.tooltipMonth) - 1];
    const yearOverlayContent = `<div class="chart-tooltip__head"><strong>${escapeHtml(point.dataset.tooltipMonth || `${overlayMonth || "Month"} ${point.dataset.tooltipYear || ""}`)}</strong><span>${escapeHtml(point.dataset.tooltipSource || "")}</span></div><dl>${yearOverlaySeriesRows.map((series) => `<div><dt>${escapeHtml(series.label)}</dt><dd>${escapeHtml(series.value)}</dd></div>`).join("")}</dl>`;
    const content = isYearOverlay
      ? yearOverlayContent
      : isRevisionActionSparkline
        ? revisionActionSparklineContent
        : isRevisionPoint
          ? revisionContent
          : isRevisionEffectivenessPoint || isRevisionEffectivenessSegment
            ? revisionEffectivenessContent
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
        isRevisionEffectivenessPoint ||
        isRevisionEffectivenessSegment ||
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
    closeRevisionEffectiveness();
    closeRevisionEffectivenessGuide();
    closeRevisionScatterGuide();
    closeComparisonKpiGuide();
    closeOverviewGuide();
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
    for (const filters of productFilters.values()) {
      for (const filter of filters) filter.close();
    }
    scopeDrawer.hidden = !open;
    for (const button of scopeButtons) {
      button.setAttribute("aria-expanded", String(open));
    }
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

  function accuracyVintageOptions(payload = currentPayload) {
    return payload?.accuracy_vintages?.options || [];
  }

  function requestedAccuracyVintageIds(payload = currentPayload) {
    const options = accuracyVintageOptions(payload);
    const supportedIds = new Set(options.map((option) => option.id));
    const visibleInputs = vintageSelectorPopover.hidden
      ? []
      : Array.from(
          vintageSelectorPopover.querySelectorAll("[data-vintage-option]"),
        );
    if (visibleInputs.length) {
      return visibleInputs
        .filter((input) => input.checked && supportedIds.has(input.value))
        .map((input) => input.value);
    }
    return options
      .filter((option) => option.selected)
      .map((option) => option.id);
  }

  function overviewApplicableMonths(vintagePayload) {
    const primaryId = vintagePayload?.overview?.primary?.id;
    if (!primaryId) return [];
    const primary = [
      ...(vintagePayload.options || []),
      vintagePayload.latest,
    ].find((series) => series?.id === primaryId);
    return (primary?.rows || [])
      .filter((row) => row.eligible_parents > 0)
      .map((row) => row.snop_month);
  }

  function overviewVolumeVintageSeries(payload = currentPayload) {
    return accuracyVintageSeries(payload);
  }

  function overviewVolumeLegend(payload = currentPayload) {
    const vintages = overviewVolumeVintageSeries(payload);
    return vintages
      .map((series) => {
        const isLatest = series.id === payload?.accuracy_vintages?.latest?.id;
        const color = accuracyVintageSeriesColor(
          series,
          payload.accuracy_vintages,
        );
        return `<span><i class="key" style="background:${color}"></i>${escapeHtml(series.label)}${isLatest ? " · fixed" : ""}</span>`;
      })
      .concat('<span><i class="key key--volume-actual"></i>Actual</span>')
      .join("");
  }

  function syncAccuracyVintageSelection(payload) {
    const selectedCount = accuracyVintageOptions(payload).filter(
      (option) => option.selected,
    ).length;
    document
      .querySelectorAll("[data-vintage-selector-count]")
      .forEach((node) => (node.textContent = String(selectedCount)));
    const subtitle = document.querySelector("[data-accuracy-chart-subtitle]");
    if (subtitle)
      subtitle.textContent = `Latest forecast fixed · ${selectedCount} vintage${selectedCount === 1 ? "" : "s"} selected`;
    const volumeSubtitle = document.querySelector(
      "[data-volume-chart-subtitle]",
    );
    const primaryLabel = payload?.accuracy_vintages?.overview?.primary?.label;
    if (volumeSubtitle && primaryLabel)
      volumeSubtitle.textContent = `${selectedCount} historical vintage${selectedCount === 1 ? "" : "s"} · Latest fixed · common cohort`;
    setHtml(
      document.querySelector("[data-volume-chart-legend]"),
      overviewVolumeLegend(payload),
    );
    if (!vintageSelectorPopover.hidden) {
      renderVintageSelector();
      if (vintageSelectorTrigger)
        positionVintageSelector(vintageSelectorTrigger);
    }
  }

  function accuracyVintageSeries(payload = currentPayload) {
    const vintages = payload?.accuracy_vintages;
    if (!vintages?.latest) return [];
    return [
      ...vintages.options.filter((option) => option.selected),
      vintages.latest,
    ];
  }

  function accuracyVintageColor(index, isLatest = false) {
    return isLatest
      ? "#087f75"
      : ACCURACY_VINTAGE_COLORS[index % ACCURACY_VINTAGE_COLORS.length];
  }

  function accuracyVintageSeriesColor(series, vintagePayload) {
    return accuracyVintageColor(
      vintagePayload.options.findIndex((option) => option.id === series.id),
      series.id === vintagePayload.latest.id,
    );
  }

  function accuracyVintageLegend(payload = currentPayload) {
    const latestId = payload?.accuracy_vintages?.latest?.id;
    return accuracyVintageSeries(payload)
      .map((series) => {
        const isLatest = series.id === latestId;
        const color = accuracyVintageSeriesColor(
          series,
          payload.accuracy_vintages,
        );
        return `<span><i class="key" style="background:${color}"></i>${escapeHtml(series.label)}${isLatest ? " · fixed" : ""}</span>`;
      })
      .concat(
        '<span><i class="key key--bias-over"></i>Over bias</span>',
        '<span><i class="key key--bias-under"></i>Under bias</span>',
      )
      .join("");
  }

  function renderVintageSelector() {
    const vintages = currentPayload?.accuracy_vintages;
    if (!vintages) return;
    const latest = vintages.latest;
    const options = vintages.options
      .map((option, index) => {
        const isDefault = option.rule?.kind === "oldest_available";
        return `<label class="vintage-selector__option"><input type="checkbox" value="${escapeHtml(option.id)}" data-vintage-option${option.selected ? " checked" : ""}/><i style="--series-color:${accuracyVintageColor(index)}"></i><span>${escapeHtml(option.label)}${isDefault ? " <small>Default</small>" : ""}</span></label>`;
      })
      .join("");
    setHtml(
      vintageSelectorPopover,
      `<header class="vintage-selector__head"><strong>Compare forecast vintages</strong><span>Select one or more historical vintages. Latest remains fixed.</span></header><div class="vintage-selector__fixed"><i style="--series-color:${accuracyVintageColor(0, true)}"></i><span>${escapeHtml(latest.label)}</span><small>Fixed</small></div>${options}`,
    );
  }

  function positionVintageSelector(trigger) {
    const triggerRect = trigger.getBoundingClientRect();
    const popoverRect = vintageSelectorPopover.getBoundingClientRect();
    const margin = 10;
    const gap = 7;
    let left = triggerRect.right - popoverRect.width;
    let top = triggerRect.bottom + gap;
    if (left < margin) left = margin;
    if (left + popoverRect.width > innerWidth - margin)
      left = innerWidth - popoverRect.width - margin;
    if (top + popoverRect.height > innerHeight - margin)
      top = triggerRect.top - popoverRect.height - gap;
    vintageSelectorPopover.style.left = `${Math.max(margin, left)}px`;
    vintageSelectorPopover.style.top = `${Math.max(margin, top)}px`;
  }

  function setVintageSelectorOpen(open, trigger = vintageSelectorTrigger) {
    vintageSelectorTriggers.forEach((button) =>
      button.setAttribute("aria-expanded", String(open && button === trigger)),
    );
    vintageSelectorPopover.hidden = !open;
    if (open && trigger) {
      vintageSelectorTrigger = trigger;
      renderVintageSelector();
      positionVintageSelector(trigger);
    }
  }

  function closeVintageSelector({ restoreFocus = false } = {}) {
    const trigger = vintageSelectorTrigger;
    setVintageSelectorOpen(false);
    vintageSelectorTrigger = null;
    if (restoreFocus) trigger?.focus();
  }

  const chartDialogContent = {
    accuracy: {
      title: "Monthly vintage accuracy and bias",
      legend: (payload) => accuracyVintageLegend(payload),
      render: (rows, options) =>
        overviewPerformanceChart(rows, {
          ...options,
          primaryBias: true,
          hideUnavailableMonths: true,
        }),
    },
    volume: {
      title: "Forecast compared with actual demand",
      legend: (payload) => overviewVolumeLegend(payload),
      render: (rows, options) =>
        overviewVolumeChart(rows, {
          ...options,
          hideUnavailableMonths: true,
        }),
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
        `Revision effectiveness evolution · ${payload.request.source.toUpperCase()}`,
      legend: "",
      renderPayload: (payload) =>
        revisionHistoryChart(payload.revision_history),
    },
    "postmortem-performance": {
      title: (payload) =>
        `Actual demand + forward outlook · ${payload.product_detail?.parent_code || "SKU"}`,
      legend: (payload) =>
        yearOverlayLegend(payload.product_detail?.year_overlay),
      renderPayload: (payload) =>
        productYearOverlayChart(payload.product_detail?.year_overlay),
    },
    "postmortem-revision": {
      title: (payload) =>
        `Revision outcome · ${payload.product_detail?.parent_code || "SKU"}`,
      legend:
        '<span><i class="scatter-key scatter-key--improved"></i>Improved</span><span><i class="scatter-key scatter-key--worsened"></i>Worsened</span><span><i class="scatter-key scatter-key--neutral"></i>Neutral</span>',
      renderPayload: (payload) =>
        productRevisionOutcomeChart(payload.product_detail?.postmortem),
    },
    "product-history": {
      title: (payload) =>
        `Selected target forecast development · ${payload.product_detail?.parent_code || "SKU"}`,
      legend:
        '<span><i class="key key--amber"></i>TM</span><span><i class="key key--teal"></i>ML</span><span><i class="key key--blue"></i>Actual</span>',
      renderPayload: (payload) => historyChart(payload.product_detail || {}),
    },
  };

  function setChartDialogTitle(title, guideButton = "") {
    setHtml(
      chartDialogTitle,
      `<span>${escapeHtml(title)}</span>${guideButton}`,
    );
  }

  function fullscreenChartContent(kind, payload) {
    const config = chartDialogContent[kind];
    if (!config) return "";
    return config.renderPayload
      ? config.renderPayload(payload)
      : config.render(payload.monthly_performance?.rows || [], {
          height: overviewChartHeight(chartDialogBody),
          vintagePayload: ["accuracy", "volume"].includes(kind)
            ? payload.accuracy_vintages
            : null,
        });
  }

  function renderFullscreenChart() {
    if (!fullscreenChart || !currentPayload) return;
    const fullscreenPayload =
      fullscreenChart === "revision" || fullscreenChart === "revision-history"
        ? activeRevisionPayload()
        : currentPayload;
    const config = chartDialogContent[fullscreenChart];
    if (!config) return;
    const pairedRevisionView =
      fullscreenChartMode === "paired" &&
      (fullscreenChart === "revision" ||
        fullscreenChart === "revision-history");
    if (pairedRevisionView) {
      chartDialog.dataset.chartKind = "revision-paired";
      setChartDialogTitle(
        "Revision effectiveness with parent vintage scatter",
        revisionEffectivenessGuideButton("chart-guide-trigger--dialog"),
      );
      setHtml(chartDialogLegend, "");
      setHtml(
        chartDialogBody,
        `<div class="chart-dialog-pair"><section class="chart-dialog-pair__panel"><h3>Revision effectiveness evolution</h3><div class="chart-dialog-pair__chart">${fullscreenChartContent("revision-history", fullscreenPayload)}</div></section><section class="chart-dialog-pair__panel"><div class="chart-dialog-pair__title-row"><h3>Parent vintage trend vs improvement score</h3>${revisionScatterGuideButton("chart-guide-trigger--dialog")}</div><div class="chart-dialog-pair__chart">${fullscreenChartContent("revision", fullscreenPayload)}</div></section></div>`,
      );
      refreshScatterCharts();
      return;
    }
    chartDialog.dataset.chartKind = fullscreenChart;
    const fullscreenTitle =
      typeof config.title === "function"
        ? config.title(fullscreenPayload)
        : config.title;
    setChartDialogTitle(
      fullscreenTitle,
      fullscreenChart === "revision-history"
        ? revisionEffectivenessGuideButton("chart-guide-trigger--dialog")
        : fullscreenChart === "revision"
          ? revisionScatterGuideButton("chart-guide-trigger--dialog")
          : fullscreenChart === "accuracy" || fullscreenChart === "volume"
            ? overviewGuideButton(
                fullscreenTitle,
                fullscreenChart === "accuracy"
                  ? "accuracy-chart"
                  : "volume-chart",
                "chart-guide-trigger chart-guide-trigger--dialog",
              )
            : "",
    );
    const legend =
      typeof config.legend === "function"
        ? config.legend(fullscreenPayload)
        : config.legend;
    setHtml(chartDialogLegend, legend || "");
    setHtml(
      chartDialogBody,
      fullscreenChartContent(fullscreenChart, fullscreenPayload),
    );
    if (fullscreenChart === "revision") refreshScatterCharts();
  }

  function openChartDialog(kind, trigger, mode = "single") {
    closeScopeDrawer();
    fullscreenChart = kind;
    fullscreenChartMode = mode;
    fullscreenTrigger = trigger;
    chartDialog.hidden = false;
    document.body.classList.add("has-chart-dialog");
    chartDialog
      .querySelector("[data-vintage-selector-trigger]")
      .toggleAttribute("hidden", kind !== "accuracy");
    renderFullscreenChart();
    chartDialogClose.focus();
  }

  function closeChartDialog() {
    if (chartDialog.hidden) return;
    closeScopeDrawer();
    closeVintageSelector();
    chartDialog.hidden = true;
    chartDialog.removeAttribute("data-chart-kind");
    setHtml(chartDialogBody, "");
    setHtml(chartDialogLegend, "");
    document.body.classList.remove("has-chart-dialog");
    fullscreenChart = null;
    fullscreenChartMode = "single";
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

  function productFilterValue(name) {
    return productFilters.get(name)?.[0]?.value() || [];
  }

  function setProductFilterOptions(name, options, selected) {
    for (const filter of productFilters.get(name) || []) {
      filter.setOptions(options, selected);
    }
  }

  function setProductFilterValue(name, selected) {
    for (const filter of productFilters.get(name) || []) {
      filter.setValue(selected);
    }
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
    if (!timelines.length) return;
    const available = ForecastTimeline.normalizeMonths(months);
    const range = ForecastTimeline.clampRange(available, start, end);
    const indices = ForecastTimeline.indexRange(
      available,
      range.start,
      range.end,
    );
    const lastIndex = Math.max(0, available.length - 1);
    const startPct = lastIndex ? (indices.start / lastIndex) * 100 : 0;
    const endPct = lastIndex ? (indices.end / lastIndex) * 100 : 100;
    const monthCount = ForecastTimeline.inclusiveMonthCount(
      range.start,
      range.end,
    );
    const latestCompletedMonth =
      currentPayload?.options?.latest_completed_target_month ||
      available.at(-1);
    const isAll =
      range.start === available[0] && range.end === latestCompletedMonth;
    const matched = ForecastTimeline.matchingPreset(
      available,
      range.start,
      range.end,
      timelineState.grain,
      [3, 6, 12, 24],
    );
    const startMonth = Number(range.start?.slice(5, 7));
    const endMonth = Number(range.end?.slice(5, 7));
    const partialQuarter =
      timelineState.grain === "quarter" &&
      (![1, 4, 7, 10].includes(startMonth) ||
        ![3, 6, 9, 12].includes(endMonth));
    const selectMarkup = available
      .map((value) => option(value, monthLabel(value), null))
      .join("");

    timelines.forEach(
      ({
        root,
        startSlider,
        endSlider,
        rail,
        selection,
        startSelect,
        endSelect,
      }) => {
        if (!startSlider || !endSlider) return;
        for (const slider of [startSlider, endSlider]) {
          slider.min = "0";
          slider.max = String(lastIndex);
          slider.disabled = available.length < 2;
        }
        startSlider.value = String(indices.start);
        startSlider.setAttribute(
          "aria-valuetext",
          monthLabel(range.start, false),
        );
        endSlider.value = String(indices.end);
        endSlider.setAttribute("aria-valuetext", monthLabel(range.end, false));
        rail?.style.setProperty("--start-pct", `${startPct}%`);
        rail?.style.setProperty("--end-pct", `${endPct}%`);
        rail?.classList.toggle("is-tight", indices.end - indices.start <= 1);
        selection?.setAttribute("aria-valuemin", "0");
        selection?.setAttribute("aria-valuemax", String(lastIndex));
        selection?.setAttribute("aria-valuenow", String(indices.start));
        selection?.setAttribute(
          "aria-valuetext",
          `${monthLabel(range.start, false)} through ${monthLabel(range.end, false)}`,
        );
        root.querySelector("[data-timeline-start]").textContent = monthLabel(
          range.start,
          false,
        );
        root.querySelector("[data-timeline-end]").textContent = monthLabel(
          range.end,
          false,
        );
        root.querySelector("[data-timeline-summary]").textContent =
          `${monthCount} month${monthCount === 1 ? "" : "s"}`;
        root.querySelectorAll("[data-timeline-grain]").forEach((button) => {
          const selected = button.dataset.timelineGrain === timelineState.grain;
          button.classList.toggle("is-active", selected);
          button.setAttribute("aria-pressed", String(selected));
        });
        root.querySelectorAll("[data-timeline-months]").forEach((button) => {
          const value = button.dataset.timelineMonths;
          const duration = Number(value);
          const selected = value === "all" ? isAll : matched === duration;
          button.classList.toggle("is-active", selected);
          button.setAttribute("aria-pressed", String(selected));
          button.disabled =
            value !== "all" &&
            ForecastTimeline.inclusiveMonthCount(
              available[0],
              available.at(-1),
            ) < duration;
          button.textContent =
            value === "all"
              ? "All"
              : timelineState.grain === "quarter"
                ? `${duration / 3}Q`
                : `${duration}M`;
        });
        const axis = root.querySelector("[data-timeline-axis]");
        if (axis) setHtml(axis, timelineAxisMarkup(available));
        root.querySelector("[data-timeline-hint]").textContent = partialQuarter
          ? `Monthly precision retained · partial ${ForecastTimeline.quarterLabel(range.start)} to partial ${ForecastTimeline.quarterLabel(range.end)}`
          : "Drag either end, or move the highlighted window. Presets reposition both ends.";
        if (startSelect && endSelect) {
          const signature = available.join("|");
          if (startSelect.dataset.options !== signature) {
            setHtml(startSelect, selectMarkup);
            setHtml(endSelect, selectMarkup);
            startSelect.dataset.options = signature;
            endSelect.dataset.options = signature;
          }
          startSelect.value = range.start ?? "";
          endSelect.value = range.end ?? "";
        }
      },
    );
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
    const latestCompletedMonth =
      currentPayload?.options?.latest_completed_target_month ||
      available.at(-1);
    const range =
      value === "all"
        ? ForecastTimeline.clampRange(
            available,
            available[0],
            latestCompletedMonth,
          )
        : ForecastTimeline.rangeForPreset(
            available,
            Number(value),
            timelineState.grain,
            controls.get("target_end").value,
          );
    setTimelineRange(available, range.start, range.end);
  }

  function syncControls(payload) {
    const { request, options } = payload;
    controls.get("comparison_mode").value = String(request.comparison_mode);
    controls.get("source").value = request.source;
    controls.get("source").disabled = request.comparison_mode;
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
    const productAvailability = options.product_availability || {};
    const availableBrands = new Set(
      productAvailability.brands || options.brands,
    );
    const availableSkuClasses = new Set(
      productAvailability.sku_classes || options.sku_classes,
    );
    setProductFilterOptions(
      "brands",
      options.brands.map((value) => ({
        value,
        label: value,
        disabled: !availableBrands.has(value),
      })),
      request.brands,
    );
    setProductFilterOptions(
      "sku_classes",
      options.sku_classes.map((value) => ({
        value,
        label: value,
        disabled: !availableSkuClasses.has(value),
      })),
      request.sku_classes,
    );
    setProductFilterOptions(
      "parent_codes",
      options.parent_products.map((row) => ({
        value: row.parent_code,
        label: `${row.parent_code} · ${row.parent_description}`,
        searchText: `${row.parent_code} ${row.parent_description}`,
      })),
      request.parent_codes,
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
          "brands",
          "sku_classes",
          "parent_codes",
          "horizon",
        ].includes(name)
      )
        continue;
      if (control.type === "checkbox") control.checked = Boolean(value);
      else if (value !== null && typeof value !== "object")
        control.value = String(value);
      else if (value === null) control.value = "";
    }
    updateFilterCount();
  }

  function buildRequest() {
    const value = (name) => controls.get(name)?.value ?? "";
    const numeric = (name) => (value(name) === "" ? null : Number(value(name)));
    return {
      source: value("source"),
      comparison_mode: value("comparison_mode") === "true",
      target_start: value("target_start") || null,
      target_end: value("target_end") || null,
      brands: productFilterValue("brands"),
      sku_classes: productFilterValue("sku_classes"),
      parent_codes: productFilterValue("parent_codes"),
      horizon: numeric("horizon"),
      minimum_actual_volume: numeric("minimum_actual_volume") ?? 0,
      accuracy_vintage_ids: requestedAccuracyVintageIds(),
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
    const ignored = new Set([
      "accuracy_vintage_ids",
      "product_parent_code",
      "product_target_month",
    ]);
    const active = Object.keys(defaults).filter((key) => {
      if (ignored.has(key) || !(key in request)) return false;
      return JSON.stringify(request[key]) !== JSON.stringify(defaults[key]);
    }).length;
    const label = `Filters · ${active}`;
    scopeButtons.forEach((button) => {
      button.textContent = label;
    });
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

  function productFilterAdjustmentMessage(filter_adjustments) {
    const removed = filter_adjustments?.removed_product_selections || {};
    const fields = [
      ["brands", "Brand"],
      ["sku_classes", "SKU Class"],
      ["parent_codes", "Parent product"],
    ];
    const parts = fields
      .filter(([field]) => Number(removed[field]) > 0)
      .map(([field, label]) => {
        const amount = Number(removed[field]);
        const suffix = amount === 1 ? "selection" : "selections";
        return `${amount} removed ${label} ${suffix}`;
      });
    return parts.length ? parts.join(" · ") : null;
  }

  async function refreshView({ announce = false, closeSelector = true } = {}) {
    clearTimeout(refreshTimer);
    const request = buildRequest();
    const key = requestKey(request);
    if (compactController && compactRequestKey === key) return;
    if (closeSelector) closeVintageSelector();
    closeVintageGapDrilldown();
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
      const adjustmentMessage = productFilterAdjustmentMessage(
        payload.filter_adjustments,
      );
      if (adjustmentMessage) showToast(adjustmentMessage);
      else if (announce) showToast("Shared population updated");
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

  function scheduleRefresh({
    immediate = false,
    announce = true,
    closeSelector = true,
  } = {}) {
    updateFilterCount();
    clearTimeout(refreshTimer);
    if (immediate) void refreshView({ announce, closeSelector });
    else
      refreshTimer = setTimeout(
        () => void refreshView({ announce, closeSelector }),
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

  function comparisonKpiGuideButton(label, guideKey) {
    return `<button class="kpi-guide-trigger" type="button" data-action="comparison-kpi-guide-open" data-kpi-guide="${escapeHtml(guideKey)}" aria-label="Explain ${escapeHtml(label)}" aria-haspopup="dialog" aria-controls="comparison-kpi-guide-dialog">?</button>`;
  }

  function overviewGuideButton(
    label,
    guideKey,
    className = "kpi-guide-trigger",
  ) {
    return `<button class="${escapeHtml(className)}" type="button" data-action="overview-guide-open" data-overview-guide="${escapeHtml(guideKey)}" aria-label="Explain ${escapeHtml(label)}" aria-haspopup="dialog" aria-controls="overview-guide-dialog">?</button>`;
  }

  function kpi(
    label,
    value,
    delta,
    caption,
    tone = "",
    help = [],
    guideKey = "",
    guideScope = "comparison",
  ) {
    const helpControl = guideKey
      ? guideScope === "overview"
        ? overviewGuideButton(label, guideKey)
        : comparisonKpiGuideButton(label, guideKey)
      : kpiHelp(label, help);
    return `<article class="kpi"><div class="kpi__head"><p class="kpi__label">${escapeHtml(label)}</p>${helpControl}</div><div class="kpi__line"><strong class="kpi__val">${escapeHtml(value)}</strong><span class="delta ${tone}">${escapeHtml(delta)}</span></div><p class="kpi__cap">${escapeHtml(caption)}</p></article>`;
  }

  function overviewPrimaryRows(payload) {
    const vintages = payload?.accuracy_vintages;
    const primaryId = vintages?.overview?.primary?.id;
    if (!primaryId) return [];
    return (
      [...(vintages.options || []), vintages.latest].find(
        (series) => series?.id === primaryId,
      )?.rows || []
    );
  }

  function kpiMicroBars(
    label,
    rows,
    field,
    { tone = "teal", signed = false, formatValue = number } = {},
  ) {
    const points = (rows || [])
      .filter((row) => row.actual_denominator_kl > 0)
      .map((row) => ({ month: row.snop_month, value: row[field] }))
      .filter((point) => finite(point.value));
    if (!points.length) {
      return `<div class="kpi-microchart kpi-microchart--empty" role="img" aria-label="${escapeHtml(`${label} monthly data unavailable`)}"></div>`;
    }

    const width = 120;
    const height = 28;
    const left = 2;
    const right = 118;
    const gap = 1;
    const barWidth = Math.max(
      1,
      (right - left - gap * (points.length - 1)) / points.length,
    );
    const maxValue = signed
      ? Math.max(...points.map((point) => Math.abs(point.value)), 1)
      : Math.max(...points.map((point) => point.value), 1);
    const zeroY = signed ? 14 : 26;
    const range = signed ? 11 : 24;
    const bars = points
      .map((point, index) => {
        const magnitude = (Math.abs(point.value) / maxValue) * range;
        const x = left + index * (barWidth + gap);
        const y = signed
          ? point.value >= 0
            ? zeroY - magnitude
            : zeroY
          : zeroY - magnitude;
        const pointHeight = Math.max(magnitude, 0.8);
        const signClass = signed
          ? point.value >= 0
            ? " kpi-microchart__bar--positive"
            : " kpi-microchart__bar--negative"
          : "";
        const latestClass = index === points.length - 1 ? " is-latest" : "";
        return `<rect class="kpi-microchart__bar${signClass}${latestClass}" x="${x}" y="${y}" width="${barWidth}" height="${pointHeight}"><title>${escapeHtml(`${monthLabel(point.month)} · ${formatValue(point.value)}`)}</title></rect>`;
      })
      .join("");
    const accessibleLabel = `${label} monthly data points: ${points
      .map((point) => `${monthLabel(point.month)} ${formatValue(point.value)}`)
      .join(", ")}`;
    return `<svg class="kpi-microchart kpi-microchart--${escapeHtml(tone)}${signed ? " kpi-microchart--signed" : ""}" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="${escapeHtml(accessibleLabel)}"><title>${escapeHtml(accessibleLabel)}</title>${signed ? `<line class="kpi-microchart__zero" x1="${left}" y1="${zeroY}" x2="${right}" y2="${zeroY}"/>` : ""}${bars}</svg>`;
  }

  function overviewKpiBarCard({
    label,
    displayLabel = label,
    shortLabel = displayLabel,
    value,
    delta,
    caption,
    tone = "",
    help = [],
    guideKey,
    rows,
    field,
    chartTone,
    signed = false,
    formatValue,
  }) {
    const helpControl = guideKey
      ? overviewGuideButton(label, guideKey)
      : kpiHelp(label, help);
    return `<article class="kpi kpi--micro"><div class="kpi-micro__summary"><div class="kpi-micro__label"><p class="kpi__label"><span class="kpi__label-long">${escapeHtml(displayLabel)}</span><span class="kpi__label-short">${escapeHtml(shortLabel)}</span></p>${helpControl}</div><div class="kpi-micro__metric"><strong class="kpi__val">${escapeHtml(value)}</strong><span class="delta ${tone}">${escapeHtml(delta)}</span></div></div>${kpiMicroBars(label, rows, field, { tone: chartTone, signed, formatValue })}<p class="sr-only">${escapeHtml(caption)}</p></article>`;
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

  function volumeBoxPlotCard(
    label,
    summary,
    scale,
    tone,
    help = [],
    guideKey = "",
  ) {
    const fields = ["whisker_low", "q1", "median", "q3", "whisker_high"];
    const valid = fields.every((field) => finite(summary?.[field]));
    const header = `<div class="kpi__head"><p class="kpi__label">${escapeHtml(label)}</p>${guideKey ? overviewGuideButton(label, guideKey) : kpiHelp(label, help)}</div>`;
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
    syncAccuracyVintageSelection(payload);
    const monthlyRows = payload.monthly_performance?.rows || [];
    const performanceChart = document.querySelector("[data-overview-chart]");
    const volumeChart = document.querySelector("[data-overview-volume-chart]");
    setHtml(
      performanceChart,
      overviewPerformanceChart(monthlyRows, {
        primaryBias: true,
        height: overviewChartHeight(performanceChart),
        vintagePayload: payload.accuracy_vintages,
        hideUnavailableMonths: true,
      }),
    );
    setHtml(
      volumeChart,
      overviewVolumeChart(monthlyRows, {
        height: overviewChartHeight(volumeChart),
        vintagePayload: payload.accuracy_vintages,
        hideUnavailableMonths: true,
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

  function overviewPrimaryShortLabel(primary) {
    if (primary?.rule?.kind === "oldest_available") return "M−5";
    if (primary?.rule?.kind === "latest_available") return "M−1";
    if (primary?.rule?.kind === "specific_horizon")
      return `M−${primary.rule.value}`;
    return primary?.label || "selected";
  }

  function errorAccumulatedSeries(payload) {
    const overview = payload.accuracy_vintages?.overview;
    const metrics = overview?.metrics;
    if (
      !overview?.primary ||
      !metrics ||
      !(metrics.accuracy_denominator_actual_kl > 0)
    )
      return null;
    return {
      primary: overview.primary,
      errorKl: metrics.primary_error_kl,
      actualKl: metrics.accuracy_denominator_actual_kl,
      months: overview.cohort_months,
      latestErrorKl: metrics.latest_error_kl,
    };
  }

  function errorAccumulatedCard(payload, rows) {
    const series = errorAccumulatedSeries(payload);
    const help = [
      "Totals the KPI vintage’s monthly absolute error over the same common cohort as the accuracy chart. The delta compares that total with the fixed latest forecast over the same months.",
    ];
    if (!series) {
      return overviewKpiBarCard({
        label: "Error accumulated",
        shortLabel: "Error",
        value: "—",
        delta: "—",
        caption: "no common cohort months",
        help,
        guideKey: "error-accumulated",
        rows: [],
        field: "absolute_error_numerator_kl",
        chartTone: "amber",
        formatValue: (value) => `${number(value, 0)} KL`,
      });
    }
    const extraKl = series.errorKl - series.latestErrorKl;
    return overviewKpiBarCard({
      label: "Error accumulated",
      shortLabel: "Error",
      value: number(series.errorKl, 0),
      delta: `${extraKl > 0 ? "+" : ""}${number(extraKl, 0)}`,
      caption:
        series.primary.rule?.kind === "latest_available"
          ? "M−1 error"
          : `${overviewPrimaryShortLabel(series.primary)} vs M−1`,
      tone: extraKl > 0 ? "delta--down" : extraKl < 0 ? "delta--up" : "",
      help,
      guideKey: "error-accumulated",
      rows,
      field: "absolute_error_numerator_kl",
      chartTone: "amber",
      formatValue: (value) => `${number(value, 0)} KL`,
    });
  }

  function renderOverview(payload) {
    const summary = payload.population_summary;
    const globalMetrics = payload.metrics;
    const cohortOverview = payload.accuracy_vintages?.overview;
    const metrics = cohortOverview?.metrics || payload.metrics;
    const primaryLabel =
      cohortOverview?.primary?.label ||
      summary.vintage_b_rule ||
      "selected forecast";
    const primaryShortLabel = overviewPrimaryShortLabel(
      cohortOverview?.primary,
    );
    document.querySelector("[data-overview-stamp]").textContent = payload
      .request.comparison_mode
      ? `canonical · exact M−${payload.request.horizon ?? "—"}`
      : `canonical · ${summary.vintage_a_rule || "—"} → ${summary.vintage_b_rule || "—"}`;
    setHtml(
      document.querySelector("[data-population-details]"),
      [
        ["Forecast rows", count(summary.forecast_rows)],
        ["Pair rows", count(summary.selected_pair_rows)],
        ["Complete pairs", count(globalMetrics.complete_pairs)],
        ["Missing vintages", count(globalMetrics.missing_vintage_pairs)],
        ["Vintage A", summary.vintage_a_rule || "comparison N/A"],
        ["Vintage B", summary.vintage_b_rule || "comparison N/A"],
        ["Zero actual", count(globalMetrics.zero_actual_observations)],
        ["Missing actual", count(globalMetrics.missing_actual_observations)],
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
    const volumeDistributions =
      cohortOverview?.volume_distributions ||
      payload.volume_distributions ||
      {};
    const volumeScale = boxPlotScale(volumeDistributions);
    const wape = finite(metrics.wape_pct) ? metrics.wape_pct : null;
    const kpiRows = overviewPrimaryRows(payload);
    setHtml(
      document.querySelector("[data-kpis]"),
      [
        kpi(
          "Forecast accuracy",
          pct(metrics.forecast_accuracy_pct),
          pp(accuracyDelta),
          `${primaryShortLabel} · n ${count(metrics.eligible_observations)}`,
          accuracyDelta >= 0 ? "delta--up" : "delta--down",
          [
            `How close ${primaryLabel} is to actual demand across the accuracy chart’s common cohort. Higher is better.`,
            "It is calculated as 100% minus total absolute error divided by total actual volume. The observation count shows how many common-cohort product-months contributed.",
            "With multiple historical vintages selected, the oldest displayed vintage drives the KPI cards. A single selection drives them directly; with no historical selection, the fixed latest forecast drives them.",
          ],
          "accuracy",
          "overview",
        ),
        overviewKpiBarCard({
          label: "Bias",
          value: pct(metrics.bias_pct),
          delta: finite(metrics.bias_pct)
            ? metrics.bias_pct >= 0
              ? "over"
              : "under"
            : "undefined",
          caption: `${primaryShortLabel} · ${metrics.bias_numerator_kl >= 0 ? "+" : "−"}${number(Math.abs(metrics.bias_numerator_kl), 0)} KL`,
          tone:
            Math.abs(metrics.bias_pct || 0) < 5 ? "delta--up" : "delta--down",
          help: [
            `Shows whether ${primaryLabel} is systematically above or below actual demand on the chart’s common cohort.`,
            "A positive value means over-forecasting; a negative value means under-forecasting. A value near zero means the over- and under-forecast errors largely balance out.",
          ],
          guideKey: "bias",
          rows: kpiRows,
          field: "bias_pct",
          chartTone: "bias",
          signed: true,
          formatValue: signedPct,
        }),
        volumeBoxPlotCard(
          "Actual volume",
          volumeDistributions.actual,
          volumeScale,
          "actual",
          [
            "Shows how monthly actual demand is distributed across the accuracy chart’s common cohort, rather than showing one total.",
            "The middle line is the median, the box contains the middle 50% of observations, and the whiskers show the broader typical range.",
          ],
          "actual-volume",
        ),
        volumeBoxPlotCard(
          "Forecast volume",
          volumeDistributions.forecast,
          volumeScale,
          "forecast",
          [
            `Shows the monthly ${primaryLabel} forecast distribution across the same common cohort as the actual-volume card.`,
            "Compare its median and spread with actual volume to see whether forecasts are generally shifted higher, lower, or are more variable.",
          ],
          "forecast-volume",
        ),
        overviewKpiBarCard({
          label: "WAPE",
          value: pct(wape),
          delta: `${count(metrics.eligible_observations)} obs`,
          caption: `${primaryShortLabel} · ${number(metrics.accuracy_denominator_actual_kl, 0)} KL`,
          help: [
            `Weighted absolute percentage error for ${primaryLabel} on the chart’s common cohort: total absolute forecast error divided by total actual volume. Lower is better.`,
            "Large-volume observations carry more influence than small-volume observations. Forecast accuracy on this dashboard is approximately 100% minus WAPE.",
          ],
          guideKey: "wape",
          rows: kpiRows,
          field: "wape_pct",
          chartTone: "teal",
          formatValue: pct,
        }),
        overviewKpiBarCard({
          label: "Revision effectiveness",
          displayLabel: "Revision eff.",
          shortLabel: "Rev.",
          value: pct(metrics.revision_effectiveness_pct),
          delta: `${count(metrics.effectiveness_numerator)} / ${count(metrics.effectiveness_denominator)}`,
          caption:
            cohortOverview?.primary?.rule?.kind === "latest_available"
              ? `${primaryShortLabel} · n/a`
              : `${primaryShortLabel}→M−1 cohort`,
          help: [
            `Of the common-cohort product-months meaningfully revised from ${primaryLabel} to the fixed latest forecast, this is the share that moved closer to actual demand.`,
            "The first count is improved revisions; the second is all materially revised common-cohort pairs. Unchanged forecasts are excluded from the denominator.",
            "The comparison uses the same parent-month cohort as every displayed accuracy series and every other overview KPI card.",
          ],
          guideKey: "effectiveness",
          rows: kpiRows,
          field: "revision_effectiveness_pct",
          chartTone: "blue",
          formatValue: pct,
        }),
        errorAccumulatedCard(payload, kpiRows),
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

  function overviewPerformanceChart(
    rows,
    {
      height = 252,
      vintagePayload = null,
      hideUnavailableMonths = false,
      primaryBias = false,
    } = {},
  ) {
    if (!rows.length) return emptyVisual("No monthly metric rows");
    const source = rows[0].source;
    const applicableMonthSet = hideUnavailableMonths
      ? new Set(overviewApplicableMonths(vintagePayload))
      : null;
    const sourceRows = rows
      .filter(
        (row) =>
          row.source === source &&
          (!applicableMonthSet || applicableMonthSet.has(row.snop_month)),
      )
      .sort((a, b) => a.snop_month.localeCompare(b.snop_month));
    if (!sourceRows.length)
      return emptyVisual("No applicable common-cohort months");
    const months = sourceRows.map((row) => row.snop_month);
    if (!vintagePayload?.latest)
      return emptyVisual("No common-cohort vintage accuracy rows");
    const activePayload = vintagePayload;
    const activeSeries = accuracyVintageSeries({
      accuracy_vintages: activePayload,
    }).map((series) => ({
      ...series,
      rows: series.rows.filter(
        (row) => !applicableMonthSet || applicableMonthSet.has(row.snop_month),
      ),
    }));
    const latestId = activePayload.latest.id;
    // Overview shares the KPI's vintage and cohort; Trends retains its existing bias source.
    const primaryRows = new Map(
      overviewPrimaryRows({ accuracy_vintages: activePayload }).map((row) => [
        row.snop_month,
        row,
      ]),
    );
    const biasRows = primaryBias
      ? sourceRows.map((row) => ({
          ...row,
          bias_pct: primaryRows.get(row.snop_month)?.bias_pct,
        }))
      : sourceRows;
    const biasLabel = primaryBias
      ? `${activePayload.overview.primary.label} bias`
      : "Latest forecast bias";
    const width = 1000;
    const scaleY = (value) => Math.round((value / 252) * height);
    const left = 22;
    const right = 982;
    const accuracyTop = scaleY(18);
    const accuracyBottom = scaleY(158);
    const biasTop = scaleY(178);
    // Leave room for negative-value labels above the two-line month axis.
    const biasBottom = scaleY(primaryBias ? 210 : 224);
    const x = (month) =>
      left +
      (months.indexOf(month) / Math.max(1, months.length - 1)) * (right - left);
    const accuracyValues = activeSeries.flatMap((series) =>
      series.rows.map((row) => row.forecast_accuracy_pct),
    );
    const [accuracyMin, accuracyMax] = chartExtent(accuracyValues);
    const accuracyY = (value) =>
      accuracyBottom -
      ((value - accuracyMin) / (accuracyMax - accuracyMin)) *
        (accuracyBottom - accuracyTop);
    const maxBias = Math.max(
      ...biasRows.map((row) => Math.abs(row.bias_pct || 0)),
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
    const accuracyLines = activeSeries
      .map((series) => {
        const isLatest = series.id === latestId;
        const seriesRows = series.rows.filter((row) =>
          finite(row.forecast_accuracy_pct),
        );
        const points = seriesRows.map((row) => ({
          x: x(row.snop_month),
          y: accuracyY(row.forecast_accuracy_pct),
        }));
        const color = accuracyVintageSeriesColor(series, activePayload);
        const labelOffset = isLatest ? -7 : 14;
        const labels =
          activeSeries.length <= 2 || isLatest
            ? seriesRows
                .map(
                  (row) =>
                    `<text x="${x(row.snop_month)}" y="${accuracyY(row.forecast_accuracy_pct) + labelOffset}">${escapeHtml(metricValue(row.forecast_accuracy_pct, "forecast_accuracy_pct", 0))}</text>`,
                )
                .join("")
            : "";
        return `<path class="chart__smooth-line chart__series--comparison${isLatest ? " chart__series--vintage-b" : ""}" style="--series-color:${color}" data-vintage-id="${escapeHtml(series.id)}" data-vintage-fixed="${isLatest}" data-vintage-default="${Boolean(series.selected)}" data-interpolation="smooth" d="${smoothLinePath(points)}"/><g class="chart__data-labels chart__series--comparison" style="--series-color:${color}" data-vintage-id="${escapeHtml(series.id)}">${labels}</g>`;
      })
      .join("");
    const biasBars = biasRows
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
    const monthHits = biasRows
      .map((row) => {
        const seriesValues = activeSeries.map((series) => {
          const point = series.rows.find(
            (item) => item.snop_month === row.snop_month,
          );
          return {
            label: series.label,
            fixed: series.id === latestId,
            value: metricValue(
              point?.forecast_accuracy_pct,
              "forecast_accuracy_pct",
            ),
          };
        });
        const evidencePoint = activeSeries
          .map((series) =>
            series.rows.find((item) => item.snop_month === row.snop_month),
          )
          .find(Boolean);
        const commonCohort = count(evidencePoint?.eligible_parents);
        const actualDenominator = kl(evidencePoint?.actual_denominator_kl);
        const seriesSummary = seriesValues
          .map((series) => `${series.label} ${series.value}`)
          .join(", ");
        const accessibleLabel = `${monthLabel(row.snop_month)}: ${seriesSummary}, common cohort ${commonCohort} parents, actual denominator ${actualDenominator}, ${biasLabel} ${metricValue(row.bias_pct, "bias_pct")}`;
        return `<rect class="chart__month-hit chart__point" x="${Math.max(left, x(row.snop_month) - hitWidth / 2)}" y="${accuracyTop}" width="${Math.min(hitWidth, right - Math.max(left, x(row.snop_month) - hitWidth / 2))}" height="${biasBottom - accuracyTop}" tabindex="0" role="button" aria-label="${escapeHtml(`${accessibleLabel}. ${activePayload.options.some((option) => option.selected) ? "Open WAPE gap drivers" : "Select a historical vintage to open gap drivers"}`)}" data-tooltip-source="${escapeHtml(source.toUpperCase())}" data-tooltip-month="${escapeHtml(monthLabel(row.snop_month))}" data-target-month="${escapeHtml(row.snop_month)}" data-vintage-gap-enabled="${activePayload.options.some((option) => option.selected)}" data-tooltip-vintage-series="${escapeHtml(JSON.stringify(seriesValues))}" data-tooltip-common-cohort="${escapeHtml(commonCohort)}" data-tooltip-actual-denominator="${escapeHtml(actualDenominator)}" data-tooltip-bias-label="${escapeHtml(biasLabel)}" data-tooltip-bias="${escapeHtml(metricValue(row.bias_pct, "bias_pct"))}" data-tooltip-bias-raw="${escapeHtml(row.bias_pct)}"/>`;
      })
      .join("");
    return `<svg class="chart chart--overview" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(`Monthly selected historical forecast accuracy compared with fixed latest forecast accuracy and ${biasLabel}`)}"><g class="chart__grid">${accuracyGrid}</g>${accuracyLines}<g class="bias-strip"><line class="bias-strip__zero" x1="${left}" y1="${biasZero}" x2="${right}" y2="${biasZero}"/>${biasBars}</g><line class="chart__x-divider" x1="${left}" y1="${scaleY(228)}" x2="${right}" y2="${scaleY(228)}"/><g class="chart__month-hits">${monthHits}</g><g class="chart__labels">${monthLabels}</g></svg>`;
  }

  function overviewVolumeChart(
    rows,
    { height = 252, vintagePayload = null, hideUnavailableMonths = false } = {},
  ) {
    const source = rows[0]?.source || "forecast";
    const applicableMonthSet = hideUnavailableMonths
      ? new Set(overviewApplicableMonths(vintagePayload))
      : null;
    const forecastSeries = overviewVolumeVintageSeries({
      accuracy_vintages: vintagePayload,
    }).map((series) => ({
      ...series,
      rows: series.rows.filter(
        (row) => !applicableMonthSet || applicableMonthSet.has(row.snop_month),
      ),
    }));
    if (!forecastSeries.length || !forecastSeries[0].rows.length)
      return emptyVisual("No common-cohort monthly volume rows");
    const latestId = vintagePayload.latest.id;
    const months = forecastSeries[0].rows.map((row) => row.snop_month);
    const actualRows = forecastSeries[0].rows;
    const width = 1000;
    const scaleY = (value) => Math.round((value / 252) * height);
    const left = 60;
    const right = 982;
    const top = scaleY(18);
    const bottom = scaleY(220);
    const x = (month) =>
      left +
      (months.indexOf(month) / Math.max(1, months.length - 1)) * (right - left);
    const volumeValues = [
      ...forecastSeries.flatMap((series) =>
        series.rows.map((row) => row.forecast_kl),
      ),
      ...actualRows.map((row) => row.actual_denominator_kl),
    ];
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
    const forecastLines = forecastSeries
      .map((series) => {
        const isLatest = series.id === latestId;
        const className = "chart__series--comparison";
        const color = accuracyVintageSeriesColor(series, vintagePayload);
        const points = series.rows
          .filter((row) => finite(row.forecast_kl))
          .map((row) => ({ x: x(row.snop_month), y: y(row.forecast_kl) }));
        return `<path class="chart__smooth-line ${className}" style="--series-color:${color}" data-volume-role="forecast" data-vintage-id="${escapeHtml(series.id)}" data-vintage-fixed="${isLatest}" data-vintage-default="${Boolean(series.selected)}" data-volume-values="${escapeHtml(JSON.stringify(series.rows.map((row) => row.forecast_kl)))}" d="${smoothLinePath(points)}"/>`;
      })
      .join("");
    const actualPoints = actualRows
      .filter((row) => finite(row.actual_denominator_kl))
      .map((row) => ({
        x: x(row.snop_month),
        y: y(row.actual_denominator_kl),
      }));
    const actualLine = `<path class="chart__smooth-line chart__series--actual" data-volume-role="actual" data-volume-values="${escapeHtml(JSON.stringify(actualRows.map((row) => row.actual_denominator_kl)))}" d="${smoothLinePath(actualPoints)}"/>`;
    const monthLabels = months
      .map((month) => {
        const [monthName, year] = monthLabel(month).split(" ");
        return `<text x="${x(month)}" y="${scaleY(234)}"><tspan x="${x(month)}">${escapeHtml(monthName)}</tspan><tspan class="chart__axis-year" x="${x(month)}" dy="16">${escapeHtml(year)}</tspan></text>`;
      })
      .join("");
    const hitWidth = (right - left) / Math.max(1, months.length - 1);
    const monthHits = actualRows
      .map((row) => {
        const volumeSeries = forecastSeries.map((series) => {
          const point = series.rows.find(
            (item) => item.snop_month === row.snop_month,
          );
          return {
            label: series.label,
            fixed: series.id === latestId,
            value: kl(point?.forecast_kl),
          };
        });
        const latest = forecastSeries.find((series) => series.id === latestId);
        const latestRow = latest?.rows.find(
          (item) => item.snop_month === row.snop_month,
        );
        const variance = signedKl(
          latestRow?.forecast_kl - row.actual_denominator_kl,
        );
        const seriesLabel = volumeSeries
          .map((series) => `${series.label} ${series.value}`)
          .join(", ");
        const accessibleLabel = `${monthLabel(row.snop_month)}: ${seriesLabel}, actual ${kl(row.actual_denominator_kl)}, latest variance ${variance}`;
        return `<rect class="chart__month-hit chart__point chart__volume-hit" x="${Math.max(left, x(row.snop_month) - hitWidth / 2)}" y="${top}" width="${Math.min(hitWidth, right - Math.max(left, x(row.snop_month) - hitWidth / 2))}" height="${bottom - top}" tabindex="0" role="img" aria-label="${escapeHtml(accessibleLabel)}" data-tooltip-kind="volume" data-tooltip-source="${escapeHtml(source.toUpperCase())}" data-tooltip-month="${escapeHtml(monthLabel(row.snop_month))}" data-tooltip-volume-series="${escapeHtml(JSON.stringify(volumeSeries))}" data-tooltip-actual="${escapeHtml(kl(row.actual_denominator_kl))}" data-tooltip-variance="${escapeHtml(variance)}"/>`;
      })
      .join("");
    const chartLabel = `${forecastSeries.map((series) => series.label).join(" and ")} forecasts compared with actual demand on the accuracy chart common cohort`;
    return `<svg class="chart chart--overview-volume" viewBox="0 0 ${width} ${height}" data-domain-min="${min}" data-domain-max="${max}" data-data-min="${Math.min(...volumeValues.filter(finite))}" data-data-max="${Math.max(...volumeValues.filter(finite))}" role="img" aria-label="${escapeHtml(chartLabel)}"><text class="chart__axis-unit" x="${left}" y="${scaleY(13)}">KL</text><g class="chart__grid chart__grid--volume">${grid}</g>${forecastLines}${actualLine}<g class="chart__month-hits">${monthHits}</g><g class="chart__labels">${monthLabels}</g></svg>`;
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
      const selectedCount = accuracyVintageOptions(payload).filter(
        (option) => option.selected,
      ).length;
      subtitle.textContent = `Latest forecast fixed · ${selectedCount} comparison vintage${selectedCount === 1 ? "" : "s"} · ${payload.request.comparison_mode ? "Aligned TM and ML" : payload.request.source.toUpperCase()} · ${monthly.total} monthly rows`;
      setHtml(legend, accuracyVintageLegend(payload));
      setHtml(
        chartContainer,
        overviewPerformanceChart(monthly.rows, {
          height: overviewChartHeight(chartContainer),
          vintagePayload: payload.accuracy_vintages,
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

  function effectivenessScoreTone(score) {
    if (score >= 80) return "high";
    if (score >= 60) return "useful";
    if (score >= 40) return "mixed";
    return "harmful";
  }

  function effectivenessScoreLabel(score) {
    const labels = {
      high: "Highly effective",
      useful: "Effective",
      mixed: "Mixed effect",
      harmful: "Harmful",
    };
    return labels[effectivenessScoreTone(score)];
  }

  function revisionEffectivenessGuideButton(extraClass = "") {
    return `<button class="chart-guide-trigger ${escapeHtml(extraClass)}" type="button" data-action="revision-effectiveness-guide-open" aria-label="Explain revision effectiveness evolution" aria-haspopup="dialog" aria-controls="revision-effectiveness-guide-dialog">?</button>`;
  }

  function revisionScatterGuideButton(extraClass = "") {
    return `<button class="chart-guide-trigger ${escapeHtml(extraClass)}" type="button" data-action="revision-scatter-guide-open" aria-label="Explain parent vintage trend versus improvement score" aria-haspopup="dialog" aria-controls="revision-scatter-guide-dialog">?</button>`;
  }

  function openRevisionEffectivenessGuide(trigger) {
    const dialog = document.querySelector(
      "#revision-effectiveness-guide-dialog",
    );
    const source = String(
      activeRevisionPayload()?.request?.source || "selected",
    ).toUpperCase();
    dialog.querySelector("[data-effectiveness-guide-context]").textContent =
      `Chart guide · ${source} · five-vintage target-month journeys`;
    dialog.hidden = false;
    document.body.classList.add("has-revision-effectiveness-guide-dialog");
    revisionEffectivenessGuideTrigger = trigger;
    dialog
      .querySelector('[data-action="revision-effectiveness-guide-close"]')
      .focus();
  }

  function closeRevisionEffectivenessGuide({ restoreFocus = false } = {}) {
    const dialog = document.querySelector(
      "#revision-effectiveness-guide-dialog",
    );
    if (dialog.hidden) return;
    dialog.hidden = true;
    document.body.classList.remove("has-revision-effectiveness-guide-dialog");
    const trigger = revisionEffectivenessGuideTrigger;
    revisionEffectivenessGuideTrigger = null;
    if (restoreFocus) trigger?.focus();
  }

  function openRevisionScatterGuide(trigger) {
    const dialog = document.querySelector("#revision-scatter-guide-dialog");
    const source = String(
      activeRevisionPayload()?.request?.source || "selected",
    ).toUpperCase();
    closeRevisionEffectivenessGuide();
    closeComparisonKpiGuide();
    dialog.querySelector("[data-scatter-guide-context]").textContent =
      `Chart guide · ${source} · parent-level revision behaviour`;
    dialog.hidden = false;
    document.body.classList.add("has-revision-scatter-guide-dialog");
    revisionScatterGuideTrigger = trigger;
    dialog
      .querySelector('[data-action="revision-scatter-guide-close"]')
      .focus();
  }

  function closeRevisionScatterGuide({ restoreFocus = false } = {}) {
    const dialog = document.querySelector("#revision-scatter-guide-dialog");
    if (dialog.hidden) return;
    dialog.hidden = true;
    document.body.classList.remove("has-revision-scatter-guide-dialog");
    const trigger = revisionScatterGuideTrigger;
    revisionScatterGuideTrigger = null;
    if (restoreFocus) trigger?.focus();
  }

  const comparisonKpiGuideTitles = {
    "accuracy-delta": {
      title: "How to read vintage accuracy delta",
      summary:
        "This KPI shows whether the selected later vintage reduced total forecast error relative to the selected earlier vintage.",
    },
    effectiveness: {
      title: "How to read revision effectiveness",
      summary:
        "This KPI asks how often a meaningful forecast revision moved closer to actual demand.",
    },
    "error-improvement": {
      title: "How to read total error improvement",
      summary:
        "This KPI adds the forecast error removed—or added—across every complete comparison pair.",
    },
  };

  function openComparisonKpiGuide(guideKey, trigger) {
    const config = comparisonKpiGuideTitles[guideKey];
    const dialog = document.querySelector("#comparison-kpi-guide-dialog");
    const guide = dialog.querySelector(
      `[data-comparison-kpi-guide="${guideKey}"]`,
    );
    if (!config || !guide) return;
    const source = String(
      activeRevisionPayload()?.request?.source || "selected",
    ).toUpperCase();
    closeRevisionEffectivenessGuide();
    closeRevisionScatterGuide();
    dialog.querySelector("[data-comparison-kpi-guide-context]").textContent =
      `Metric guide · ${source} · active comparison population`;
    dialog.querySelector("#comparison-kpi-guide-title").textContent =
      config.title;
    dialog.querySelector("#comparison-kpi-guide-summary").textContent =
      config.summary;
    dialog
      .querySelectorAll("[data-comparison-kpi-guide]")
      .forEach((section) => {
        section.hidden = section !== guide;
      });
    dialog.hidden = false;
    document.body.classList.add("has-comparison-kpi-guide-dialog");
    comparisonKpiGuideTrigger = trigger;
    dialog.querySelector('[data-action="comparison-kpi-guide-close"]').focus();
  }

  function closeComparisonKpiGuide({ restoreFocus = false } = {}) {
    const dialog = document.querySelector("#comparison-kpi-guide-dialog");
    if (dialog.hidden) return;
    dialog.hidden = true;
    document.body.classList.remove("has-comparison-kpi-guide-dialog");
    const trigger = comparisonKpiGuideTrigger;
    comparisonKpiGuideTrigger = null;
    if (restoreFocus) trigger?.focus();
  }

  const overviewGuideTitles = {
    accuracy: {
      title: "How to read forecast accuracy",
      summary:
        "This KPI uses the chart’s KPI vintage and common cohort: oldest when several historical vintages are shown, the specific vintage when one is shown, and latest when none are shown.",
    },
    bias: {
      title: "Where does Bias come from?",
      summary:
        "Start with the formula, see eight genuine signed forecast-to-actual gaps, then follow the positive and negative errors into one portfolio-level division.",
    },
    "actual-volume": {
      title: "How to read actual volume",
      summary:
        "This box plot shows how monthly actual demand varies across the accuracy chart’s common cohort.",
    },
    "forecast-volume": {
      title: "How to read forecast volume",
      summary:
        "This box plot shows how the chart’s KPI vintage monthly totals vary across the common cohort, on the same scale as actual volume.",
    },
    wape: {
      title: "Where does WAPE come from?",
      summary:
        "Start with the formula, see eight genuine forecast-to-actual gaps, then follow every eligible gap into one portfolio-level division.",
    },
    effectiveness: {
      title: "How to read revision effectiveness",
      summary:
        "Of the common-cohort forecasts that changed materially from the KPI vintage to latest, this is the share that moved closer to actual demand.",
    },
    "error-accumulated": {
      title: "Every shaded gap becomes part of the total",
      summary:
        "Whether the forecast is over or under, accumulated error measures each distance from actual demand and adds the distances together.",
    },
    "accuracy-chart": {
      title: "How to read monthly vintage accuracy and bias",
      summary:
        "The lines compare every selected historical vintage with fixed latest M1. Bias below uses the KPI vintage—oldest selected, or latest when none are selected—on the identical common cohort.",
    },
    "volume-chart": {
      title: "How to read forecast versus actual volume",
      summary:
        "Compare every selected historical forecast, fixed latest M1 and actual demand on the accuracy chart’s common cohort. Vintage colors match the accuracy chart and selector.",
    },
  };

  function errorAccumulatedGuideData(payload) {
    const vintagePayload = payload?.accuracy_vintages;
    const overview = vintagePayload?.overview;
    const summary = errorAccumulatedSeries(payload);
    if (!summary) return null;
    const allSeries = [
      ...(vintagePayload.options || []),
      vintagePayload.latest,
    ].filter(Boolean);
    const primarySeries = allSeries.find(
      (series) => series.id === overview.primary.id,
    );
    const rows = (primarySeries?.rows || []).filter(
      (row) =>
        row.eligible_parents > 0 && finite(row.absolute_error_numerator_kl),
    );
    return {
      primary: summary.primary,
      primaryErrorKl: summary.errorKl,
      latestErrorKl: summary.latestErrorKl,
      rows,
    };
  }

  function renderErrorAccumulatedGuide(payload, guide) {
    const data = errorAccumulatedGuideData(payload);
    const months = guide.querySelector("[data-error-accumulated-months]");
    const monthCount = guide.querySelector(
      "[data-error-accumulated-month-count]",
    );
    const primary = guide.querySelector("[data-error-accumulated-primary]");
    const primaryLabel = guide.querySelector(
      "[data-error-accumulated-primary-label]",
    );
    const latest = guide.querySelector("[data-error-accumulated-latest]");
    const extra = guide.querySelector("[data-error-accumulated-extra]");
    const extraBox = guide.querySelector("[data-error-accumulated-extra-box]");
    if (!data) {
      setHtml(
        months,
        '<p class="error-accumulated-guide__empty">No common-cohort months are available for the active filters.</p>',
      );
      monthCount.textContent = "active months";
      primary.textContent = "—";
      primaryLabel.textContent = "selected forecast";
      latest.textContent = "—";
      extra.textContent = "—";
      extraBox.classList.remove("is-good");
      return;
    }
    const monthMarkup = data.rows
      .map(
        (row) =>
          `<div class="error-accumulated-guide__month-error"><span>${escapeHtml(monthLabel(row.snop_month).split(" ")[0].toUpperCase())}</span><strong>${escapeHtml(number(row.absolute_error_numerator_kl, 0))}</strong></div>`,
      )
      .join("");
    setHtml(
      months,
      monthMarkup ||
        '<p class="error-accumulated-guide__empty">No common-cohort months are available for the active filters.</p>',
    );
    months.setAttribute(
      "aria-label",
      data.rows.length
        ? `${data.rows.length} monthly absolute errors that add to ${number(data.primaryErrorKl, 0)} KL`
        : "No monthly absolute errors available",
    );
    monthCount.textContent = `${data.rows.length || "active"} months`;
    primary.textContent = number(data.primaryErrorKl, 0);
    const parentheticalLabel = data.primary.label?.match(/\(([^)]+)\)$/)?.[1];
    primaryLabel.textContent = parentheticalLabel || data.primary.label;
    latest.textContent = number(data.latestErrorKl, 0);
    const extraKl = data.primaryErrorKl - data.latestErrorKl;
    extra.textContent = `${extraKl > 0 ? "+" : ""}${number(extraKl, 0)}`;
    extraBox.classList.toggle("is-good", extraKl <= 0);
  }

  function renderWapeGuide(payload, guide) {
    const overview = payload?.accuracy_vintages?.overview;
    const metrics = overview?.metrics;
    const rows = overview?.wape_examples || [];
    const lanes = guide.querySelector("[data-wape-guide-lanes]");
    const sum = guide.querySelector("[data-wape-guide-sum]");
    if (!metrics || !rows.length) {
      setHtml(
        lanes,
        '<p class="wape-guide__empty">No eligible forecast-to-actual rows are available for the active filters.</p>',
      );
      setHtml(sum, "");
      return;
    }

    const scaleMax = Math.max(
      1,
      ...rows.flatMap((row) => [row.forecast_kl, row.actual_kl]),
    );
    const maxError = Math.max(1, ...rows.map((row) => row.absolute_error_kl));
    const shownError = rows.reduce(
      (total, row) => total + row.absolute_error_kl,
      0,
    );
    const totalError = metrics.primary_error_kl || 0;
    const remainingError = Math.max(0, totalError - shownError);
    const remainingRows = Math.max(
      0,
      (metrics.eligible_observations || 0) - rows.length,
    );
    const laneMarkup = rows
      .map((row) => {
        const actual = (row.actual_kl / scaleMax) * 100;
        const forecast = (row.forecast_kl / scaleMax) * 100;
        const gapLeft = Math.min(actual, forecast);
        const gapWidth = Math.abs(actual - forecast);
        const labelLeft = gapLeft + gapWidth / 2;
        const description = row.parent_description || `SKU ${row.parent_code}`;
        return `<div class="wape-guide__lane is-${escapeHtml(row.direction)}"><div class="wape-guide__lane-title"><strong>${escapeHtml(String(row.parent_code))} · ${escapeHtml(description)}</strong><span>${escapeHtml(monthLabel(row.snop_month))}</span></div><div class="wape-guide__lane-plot"><i class="wape-guide__actual" style="width:${actual}%"></i><i class="wape-guide__gap" style="left:${gapLeft}%;width:${gapWidth}%"></i><i class="wape-guide__forecast" style="left:${forecast}%"></i><i class="wape-guide__bracket" style="left:${gapLeft}%;width:${Math.max(gapWidth, 1.5)}%"></i><b class="wape-guide__error-label" style="left:${labelLeft}%">${escapeHtml(number(row.absolute_error_kl, 1))} KL error</b></div><div class="wape-guide__values"><span>FC ${escapeHtml(number(row.forecast_kl, 1))}</span><span>Actual ${escapeHtml(number(row.actual_kl, 1))}</span></div></div>`;
      })
      .join("");
    setHtml(lanes, laneMarkup);
    lanes.setAttribute(
      "aria-label",
      `${rows.length} real common-cohort rows showing forecast, actual and absolute error`,
    );
    setHtml(
      sum,
      rows
        .map(
          (row) =>
            `<div class="wape-guide__sum-row is-${escapeHtml(row.direction)}"><span>${escapeHtml(String(row.parent_code))}</span><i style="--sum-width:${(row.absolute_error_kl / maxError) * 100}%"></i><b>+ ${escapeHtml(number(row.absolute_error_kl, 1))} KL</b></div>`,
        )
        .join(""),
    );
    guide.querySelector("[data-wape-guide-axis-quarter]").textContent = number(
      scaleMax * 0.25,
      0,
    );
    guide.querySelector("[data-wape-guide-axis-half]").textContent = number(
      scaleMax * 0.5,
      0,
    );
    guide.querySelector("[data-wape-guide-axis-three-quarter]").textContent =
      number(scaleMax * 0.75, 0);
    guide.querySelector("[data-wape-guide-axis-max]").textContent = number(
      scaleMax,
      0,
    );
    guide.querySelector("[data-wape-guide-primary]").textContent =
      overview.primary?.label || "KPI vintage";
    guide.querySelector("[data-wape-guide-shown-error]").textContent =
      `${number(shownError, 1)} KL`;
    guide.querySelector("[data-wape-guide-remaining]").textContent =
      `+ remaining ${count(remainingRows)} rows`;
    guide.querySelector("[data-wape-guide-remaining-error]").textContent =
      `${number(remainingError, 1)} KL`;
    guide.querySelector("[data-wape-guide-total-error]").textContent =
      `${number(totalError, 1)} KL`;
    guide.querySelector("[data-wape-guide-total-actual]").textContent =
      `${number(metrics.accuracy_denominator_actual_kl, 1)} KL actual`;
    guide.querySelector("[data-wape-guide-result]").textContent = pct(
      metrics.wape_pct,
    );
    guide.querySelector("[data-wape-guide-observations]").textContent = count(
      metrics.eligible_observations,
    );
  }

  function renderBiasGuide(payload, guide) {
    const overview = payload?.accuracy_vintages?.overview;
    const metrics = overview?.metrics;
    const rows = overview?.wape_examples || [];
    const lanes = guide.querySelector("[data-bias-guide-lanes]");
    const sum = guide.querySelector("[data-bias-guide-sum]");
    if (!metrics || !rows.length) {
      setHtml(
        lanes,
        '<p class="wape-guide__empty">No eligible forecast-to-actual rows are available for the active filters.</p>',
      );
      setHtml(sum, "");
      return;
    }

    const scaleMax = Math.max(
      1,
      ...rows.flatMap((row) => [row.forecast_kl, row.actual_kl]),
    );
    const maxError = Math.max(
      1,
      ...rows.map((row) => Math.abs(row.forecast_kl - row.actual_kl)),
    );
    const shownBias = rows.reduce(
      (total, row) => total + row.forecast_kl - row.actual_kl,
      0,
    );
    const totalBias = metrics.bias_numerator_kl || 0;
    const remainingBias = totalBias - shownBias;
    const remainingRows = Math.max(
      0,
      (metrics.eligible_observations || 0) - rows.length,
    );
    const laneMarkup = rows
      .map((row) => {
        const actual = (row.actual_kl / scaleMax) * 100;
        const forecast = (row.forecast_kl / scaleMax) * 100;
        const signedError = row.forecast_kl - row.actual_kl;
        const gapLeft = Math.min(actual, forecast);
        const gapWidth = Math.abs(actual - forecast);
        const labelLeft = gapLeft + gapWidth / 2;
        const description = row.parent_description || `SKU ${row.parent_code}`;
        return `<div class="wape-guide__lane is-${escapeHtml(row.direction)}"><div class="wape-guide__lane-title"><strong>${escapeHtml(String(row.parent_code))} · ${escapeHtml(description)}</strong><span>${escapeHtml(monthLabel(row.snop_month))}</span></div><div class="wape-guide__lane-plot"><i class="wape-guide__actual" style="width:${actual}%"></i><i class="wape-guide__gap" style="left:${gapLeft}%;width:${gapWidth}%"></i><i class="wape-guide__forecast" style="left:${forecast}%"></i><i class="wape-guide__bracket" style="left:${gapLeft}%;width:${Math.max(gapWidth, 1.5)}%"></i><b class="wape-guide__error-label" style="left:${labelLeft}%">${escapeHtml(signedKl(signedError, 1))}</b></div><div class="wape-guide__values"><span>FC ${escapeHtml(number(row.forecast_kl, 1))}</span><span>Actual ${escapeHtml(number(row.actual_kl, 1))}</span></div></div>`;
      })
      .join("");
    setHtml(lanes, laneMarkup);
    lanes.setAttribute(
      "aria-label",
      `${rows.length} real common-cohort rows showing forecast, actual and signed error`,
    );
    setHtml(
      sum,
      rows
        .map((row) => {
          const signedError = row.forecast_kl - row.actual_kl;
          return `<div class="wape-guide__sum-row is-${escapeHtml(row.direction)}"><span>${escapeHtml(String(row.parent_code))}</span><i style="--sum-width:${(Math.abs(signedError) / maxError) * 100}%"></i><b>${escapeHtml(signedKl(signedError, 1))}</b></div>`;
        })
        .join(""),
    );
    guide.querySelector("[data-bias-guide-axis-quarter]").textContent = number(
      scaleMax * 0.25,
      0,
    );
    guide.querySelector("[data-bias-guide-axis-half]").textContent = number(
      scaleMax * 0.5,
      0,
    );
    guide.querySelector("[data-bias-guide-axis-three-quarter]").textContent =
      number(scaleMax * 0.75, 0);
    guide.querySelector("[data-bias-guide-axis-max]").textContent = number(
      scaleMax,
      0,
    );
    guide.querySelector("[data-bias-guide-primary]").textContent =
      overview.primary?.label || "KPI vintage";
    guide.querySelector("[data-bias-guide-shown-error]").textContent = signedKl(
      shownBias,
      1,
    );
    guide.querySelector("[data-bias-guide-remaining]").textContent =
      `Remaining ${count(remainingRows)} rows · net`;
    guide.querySelector("[data-bias-guide-remaining-error]").textContent =
      signedKl(remainingBias, 1);
    guide.querySelector("[data-bias-guide-total-error]").textContent = signedKl(
      totalBias,
      1,
    );
    guide.querySelector("[data-bias-guide-total-actual]").textContent =
      `${number(metrics.bias_denominator_actual_kl, 1)} KL actual`;
    guide.querySelector("[data-bias-guide-result]").textContent = signedPct(
      metrics.bias_pct,
    );
    guide.querySelector("[data-bias-guide-observations]").textContent = count(
      metrics.eligible_observations,
    );
    const direction =
      totalBias > 0 ? "over" : totalBias < 0 ? "under" : "match";
    guide.classList.toggle("is-over", direction === "over");
    guide.classList.toggle("is-under", direction === "under");
    guide.classList.toggle("is-match", direction === "match");
    guide.querySelector("[data-bias-guide-interpretation]").textContent =
      direction === "over"
        ? `For every 100 KL actually sold, the KPI forecast finished ${number(Math.abs(metrics.bias_pct), 1)} KL above demand.`
        : direction === "under"
          ? `For every 100 KL actually sold, the KPI forecast finished ${number(Math.abs(metrics.bias_pct), 1)} KL below demand.`
          : "The portfolio forecast and actual demand balance overall, but individual errors may still cancel.";
  }

  function openOverviewGuide(guideKey, trigger) {
    const config = overviewGuideTitles[guideKey];
    const dialog = document.querySelector("#overview-guide-dialog");
    const guide = dialog.querySelector(`[data-overview-guide="${guideKey}"]`);
    if (!config || !guide) return;
    closeRevisionEffectivenessGuide();
    closeRevisionScatterGuide();
    closeComparisonKpiGuide();
    const source = String(
      currentPayload?.request?.source || "selected",
    ).toUpperCase();
    dialog.classList.toggle(
      "is-error-accumulated-guide",
      guideKey === "error-accumulated",
    );
    dialog.classList.toggle(
      "is-wape-guide",
      guideKey === "wape" || guideKey === "bias",
    );
    if (guideKey === "error-accumulated")
      renderErrorAccumulatedGuide(currentPayload, guide);
    if (guideKey === "wape") renderWapeGuide(currentPayload, guide);
    if (guideKey === "bias") renderBiasGuide(currentPayload, guide);
    dialog.querySelector("[data-overview-guide-context]").textContent =
      `Guide · ${source} · active overview population`;
    const guideMetric =
      guideKey === "wape"
        ? currentPayload?.accuracy_vintages?.overview?.metrics?.wape_pct
        : guideKey === "bias"
          ? currentPayload?.accuracy_vintages?.overview?.metrics?.bias_pct
          : null;
    dialog.querySelector("#overview-guide-title").textContent =
      finite(guideMetric) && (guideKey === "wape" || guideKey === "bias")
        ? `Where does ${guideKey === "bias" ? signedPct(guideMetric) : pct(guideMetric)} come from?`
        : config.title;
    dialog.querySelector("#overview-guide-summary").textContent =
      config.summary;
    dialog.querySelectorAll("[data-overview-guide]").forEach((section) => {
      section.hidden = section !== guide;
    });
    dialog.hidden = false;
    document.body.classList.add("has-overview-guide-dialog");
    overviewGuideTrigger = trigger;
    dialog.querySelector('[data-action="overview-guide-close"]').focus();
  }

  function closeOverviewGuide({ restoreFocus = false } = {}) {
    const dialog = document.querySelector("#overview-guide-dialog");
    if (dialog.hidden) return;
    dialog.hidden = true;
    document.body.classList.remove("has-overview-guide-dialog");
    const trigger = overviewGuideTrigger;
    overviewGuideTrigger = null;
    if (restoreFocus) trigger?.focus();
  }

  function vintageGapModeConfig() {
    return vintageGapMode === "regressions"
      ? {
          label: "Latest regressions",
          verb: "added",
          brandPp: "regression_wape_pp",
          brandKl: "regression_kl",
          totalPp: vintageGapPayload?.summary?.regression_wape_pp || 0,
          totalKl: vintageGapPayload?.summary?.regression_kl || 0,
          parentMatches: (row) => row.error_change_kl < 0,
          parentPp: (row) => -row.wape_contribution_pp,
          parentKl: (row) => -row.error_change_kl,
        }
      : {
          label: "Gap creators",
          verb: "fixed",
          brandPp: "gross_fix_wape_pp",
          brandKl: "gross_fix_kl",
          totalPp: vintageGapPayload?.summary?.gross_fix_wape_pp || 0,
          totalKl: vintageGapPayload?.summary?.gross_fix_kl || 0,
          parentMatches: (row) => row.error_change_kl > 0,
          parentPp: (row) => row.wape_contribution_pp,
          parentKl: (row) => row.error_change_kl,
        };
  }

  function vintageGapOther(rows, visible, value) {
    const visibleSet = new Set(visible);
    return rows
      .filter((row) => !visibleSet.has(row))
      .reduce(
        (total, row) => ({
          pp: total.pp + value(row).pp,
          kl: total.kl + value(row).kl,
          count: total.count + (row.parent_count || 1),
        }),
        { pp: 0, kl: 0, count: 0 },
      );
  }

  function vintageGapBrandRows(config) {
    const query = vintageGapBrandSearch.trim().toLowerCase();
    return (vintageGapPayload?.brands || [])
      .filter((row) => row[config.brandPp] > 0)
      .filter((row) => !query || row.brand.toLowerCase().includes(query))
      .sort(
        (a, b) =>
          b[config.brandPp] - a[config.brandPp] ||
          a.brand.localeCompare(b.brand),
      );
  }

  function vintageGapParentRows(config, brand = vintageGapSelectedBrand) {
    const query = vintageGapParentSearch.trim().toLowerCase();
    return (vintageGapPayload?.parents || [])
      .filter((row) => row.brand === brand && config.parentMatches(row))
      .filter(
        (row) =>
          !query ||
          String(row.parent_code).includes(query) ||
          String(row.parent_description || "")
            .toLowerCase()
            .includes(query),
      )
      .sort(
        (a, b) =>
          config.parentPp(b) - config.parentPp(a) ||
          a.parent_code - b.parent_code,
      );
  }

  function vintageGapSummary(payload) {
    const summary = payload.summary;
    const netTone = summary.net_wape_improvement_pp >= 0 ? "good" : "bad";
    return `<section class="vintage-gap__summary" aria-label="WAPE reconciliation summary"><div><span>Baseline WAPE</span><strong>${pct(summary.baseline_wape_pct)}</strong><small>${escapeHtml(payload.baseline.label)}</small></div><i aria-hidden="true">→</i><div><span>Latest WAPE</span><strong>${pct(summary.latest_wape_pct)}</strong><small>${escapeHtml(payload.latest.label)} · fixed</small></div><div class="vintage-gap__summary-result"><span>Net improvement</span><strong class="${netTone}">${pp(summary.net_wape_improvement_pp)}</strong><small>${signedKl(summary.baseline_absolute_error_kl - summary.latest_absolute_error_kl)} error removed</small></div><div><span>Gross fixed</span><strong>${pp(summary.gross_fix_wape_pp)}</strong><small>${kl(summary.gross_fix_kl)}</small></div><div><span>Latest regressions</span><strong class="bad">${number(summary.regression_wape_pp, 1)} pp</strong><small>${kl(summary.regression_kl)} added</small></div></section>`;
  }

  function vintageGapBrandList(rows, config) {
    if (!rows.length)
      return '<p class="vintage-gap__empty">No contributors in this view.</p>';
    const sourceRows = rows;
    const visible = vintageGapShowAll ? sourceRows : sourceRows.slice(0, 10);
    const maxValue = Math.max(
      ...sourceRows.map((row) => row[config.brandPp]),
      1,
    );
    const total = Math.max(config.totalPp, 0.000001);
    const markup = visible
      .map((row) => {
        const selected = row.brand === vintageGapSelectedBrand;
        const width = Math.max(3, (row[config.brandPp] / maxValue) * 100);
        return `<button class="vintage-gap__brand${selected ? " is-selected" : ""}" data-vintage-gap-brand="${escapeHtml(row.brand)}" aria-pressed="${selected}" type="button"><span><strong>${escapeHtml(row.brand)}</strong><b>${number(row[config.brandPp], 1)} pp</b></span><i><em style="width:${width}%"></em></i><small>${kl(row[config.brandKl])} ${config.verb} · ${number((row[config.brandPp] / total) * 100, 0)}% of ${config.label.toLowerCase()} · ${count(row.parent_count)} parents</small></button>`;
      })
      .join("");
    if (vintageGapShowAll || visible.length === sourceRows.length)
      return markup;
    const other = vintageGapOther(sourceRows, visible, (row) => ({
      pp: row[config.brandPp],
      kl: row[config.brandKl],
    }));
    return `${markup}<div class="vintage-gap__brand vintage-gap__other"><span><strong>Other brands</strong><b>${number(other.pp, 1)} pp</b></span><i><em style="width:${Math.max(3, (other.pp / maxValue) * 100)}%"></em></i><small>${kl(other.kl)} ${config.verb} · ${number((other.pp / total) * 100, 0)}% · ${count(other.count)} parents</small></div>`;
  }

  function vintageGapParentTable(rows, config) {
    if (!rows.length)
      return '<p class="vintage-gap__empty">No parent SKUs match this view.</p>';
    const visible = vintageGapShowAll ? rows : rows.slice(0, 15);
    const total = Math.max(config.totalPp, 0.000001);
    const body = visible
      .map((row) => {
        const contribution = config.parentPp(row);
        const selected = row.parent_code === vintageGapSelectedParent;
        return `<button class="vintage-gap__parent-row${selected ? " is-selected" : ""}" data-vintage-gap-parent="${escapeHtml(row.parent_code)}" type="button" aria-pressed="${selected}"><span><strong>${escapeHtml(row.parent_code)}</strong><small title="${escapeHtml(row.parent_description)}">${escapeHtml(row.parent_description || "No description")}</small></span><b>${number(row.actual_kl, 1)}</b><span>${number(row.baseline_forecast_kl, 1)}<i>→</i>${number(row.latest_forecast_kl, 1)}</span><span>${number(row.baseline_absolute_error_kl, 1)}<i>→</i>${number(row.latest_absolute_error_kl, 1)}</span><strong>${number(contribution, 2)} pp<small>${kl(config.parentKl(row))} ${config.verb}</small></strong><em>${number((contribution / total) * 100, 0)}%</em></button>`;
      })
      .join("");
    if (vintageGapShowAll || visible.length === rows.length) return body;
    const other = vintageGapOther(rows, visible, (row) => ({
      pp: config.parentPp(row),
      kl: config.parentKl(row),
    }));
    return `${body}<div class="vintage-gap__parent-row vintage-gap__parent-row--other"><span><strong>Other parents</strong><small>${count(other.count)} parent SKUs</small></span><b>—</b><span>—</span><span>—</span><strong>${number(other.pp, 2)} pp<small>${kl(other.kl)} ${config.verb}</small></strong><em>${number((other.pp / total) * 100, 0)}%</em></div>`;
  }

  function vintageGapParentDetail(row, config) {
    if (!row) return "";
    return `<section class="vintage-gap__parent-detail"><div><p class="eyebrow">Selected parent SKU</p><h4>${escapeHtml(row.parent_code)} · ${escapeHtml(row.parent_description || "No description")}</h4><span>${escapeHtml(row.brand)} · ${escapeHtml(labelize(row.baseline_direction))} at baseline → ${escapeHtml(labelize(row.latest_direction))} at latest</span></div><dl><div><dt>Forecast revision</dt><dd>${signedKl(row.forecast_revision_kl)}</dd></div><div><dt>Error ${config.verb}</dt><dd class="${vintageGapMode === "fixes" ? "good" : "bad"}">${kl(config.parentKl(row))}</dd></div><div><dt>WAPE contribution</dt><dd>${number(config.parentPp(row), 2)} pp</dd></div></dl><button class="btn btn--accent" data-vintage-gap-open-product="${escapeHtml(row.parent_code)}" type="button">Open product history</button></section>`;
  }

  function renderVintageGapDrilldown() {
    const payload = vintageGapPayload;
    if (!payload) return;
    vintageGapDialog.dataset.gapMode = vintageGapMode;
    const config = vintageGapModeConfig();
    const brands = vintageGapBrandRows(config);
    if (!brands.some((row) => row.brand === vintageGapSelectedBrand))
      vintageGapSelectedBrand = brands[0]?.brand || null;
    const parents = vintageGapParentRows(config);
    if (!parents.some((row) => row.parent_code === vintageGapSelectedParent))
      vintageGapSelectedParent = parents[0]?.parent_code || null;
    const selectedParent = (vintageGapPayload.parents || []).find(
      (row) => row.parent_code === vintageGapSelectedParent,
    );
    const searchControls = vintageGapShowAll
      ? `<div class="vintage-gap__searches"><label><span>Find brand</span><input type="search" data-vintage-gap-brand-search value="${escapeHtml(vintageGapBrandSearch)}" placeholder="Brand name"/></label><label><span>Find parent SKU</span><input type="search" data-vintage-gap-parent-search value="${escapeHtml(vintageGapParentSearch)}" placeholder="Code or description"/></label></div>`
      : "";
    setHtml(
      vintageGapBody,
      `${vintageGapSummary(payload)}<div class="vintage-gap__toolbar"><div role="group" aria-label="Contribution view"><button type="button" data-vintage-gap-mode="fixes" aria-pressed="${vintageGapMode === "fixes"}">Gap creators <b>${pp(payload.summary.gross_fix_wape_pp)}</b></button><button type="button" data-vintage-gap-mode="regressions" aria-pressed="${vintageGapMode === "regressions"}">Latest regressions <b>${number(payload.summary.regression_wape_pp, 1)} pp</b></button></div><button type="button" class="vintage-gap__show-all" data-vintage-gap-show-all aria-pressed="${vintageGapShowAll}">${vintageGapShowAll ? "Top contributors" : "Show all + search"}</button></div>${searchControls}<div class="vintage-gap__workspace"><section class="vintage-gap__brands"><header><div><p class="eyebrow">Brand contribution</p><h3>${escapeHtml(config.label)}</h3></div><span>Shared-denominator WAPE pp</span></header><div class="vintage-gap__brand-list">${vintageGapBrandList(brands, config)}</div></section><section class="vintage-gap__parents"><header><div><p class="eyebrow">Parent SKU evidence</p><h3>${escapeHtml(vintageGapSelectedBrand || "No brand selected")}</h3></div><span>${count(parents.length)} matching parents</span></header><div class="vintage-gap__parent-head"><span>Parent SKU</span><b>Actual KL</b><span>Forecast<br/>baseline → latest</span><span>Abs error<br/>baseline → latest</span><strong>Contribution</strong><em>Share</em></div><div class="vintage-gap__parent-list">${vintageGapParentTable(parents, config)}</div>${vintageGapParentDetail(selectedParent, config)}</section></div><footer class="vintage-gap__foot">Brand and parent contributions use the chart's exact common cohort and shared actual denominator. Positive fixes and latest regressions reconcile to the net WAPE change.</footer>`,
    );
  }

  async function openVintageGapDrilldown(point) {
    const selectedIds = currentRequest?.accuracy_vintage_ids || [];
    if (!selectedIds.length) {
      showToast("Select a historical vintage to see WAPE gap drivers");
      return;
    }
    const targetMonth = point.dataset.targetMonth;
    if (!targetMonth || !currentRequest) return;
    vintageGapController?.abort();
    vintageGapMode = "fixes";
    vintageGapSelectedBrand = null;
    vintageGapSelectedParent = null;
    vintageGapShowAll = false;
    vintageGapBrandSearch = "";
    vintageGapParentSearch = "";
    vintageGapPayload = null;
    vintageGapTrigger = point;
    vintageGapDialog.hidden = false;
    document.body.classList.add("has-vintage-gap-dialog");
    vintageGapDialog.querySelector("[data-vintage-gap-eyebrow]").textContent =
      `${String(currentRequest.source).toUpperCase()} · monthly WAPE reconciliation`;
    vintageGapDialog.querySelector("[data-vintage-gap-title]").textContent =
      `${monthLabel(targetMonth, false)} vintage gap drivers`;
    vintageGapDialog.querySelector("[data-vintage-gap-subtitle]").textContent =
      "Loading the exact common-cohort brand and parent contributions…";
    setHtml(
      vintageGapBody,
      '<div class="vintage-gap__loading"><strong>Calculating gap contributors</strong><span>Reusing the displayed vintage cohort and active filters.</span></div>',
    );
    vintageGapClose.focus();
    const controller = new AbortController();
    vintageGapController = controller;
    try {
      const response = await jsonRequest("api/vintage-gap-drilldown", {
        method: "POST",
        body: JSON.stringify({
          ...currentRequest,
          vintage_gap_target_month: targetMonth,
        }),
        signal: controller.signal,
      });
      if (
        vintageGapController !== controller ||
        requestKey(response.request) !== requestKey(currentRequest)
      )
        return;
      vintageGapPayload = response.drilldown;
      vintageGapDialog.querySelector(
        "[data-vintage-gap-subtitle]",
      ).textContent =
        `${response.drilldown.baseline.label} compared with fixed ${response.drilldown.latest.label} · ${count(response.drilldown.summary.eligible_parents)} common-cohort parents · ${kl(response.drilldown.summary.actual_denominator_kl)} actual denominator`;
      renderVintageGapDrilldown();
    } catch (error) {
      if (isAbortError(error)) return;
      setHtml(
        vintageGapBody,
        `<div class="vintage-gap__loading vintage-gap__loading--error"><strong>Gap drivers unavailable</strong><span>${escapeHtml(error.message)}</span></div>`,
      );
      showToast(error.message, true);
    } finally {
      if (vintageGapController === controller) vintageGapController = null;
    }
  }

  function closeVintageGapDrilldown({ restoreFocus = false } = {}) {
    if (vintageGapDialog.hidden) return;
    vintageGapController?.abort();
    vintageGapController = null;
    vintageGapDialog.hidden = true;
    document.body.classList.remove("has-vintage-gap-dialog");
    vintageGapPayload = null;
    const trigger = vintageGapTrigger;
    vintageGapTrigger = null;
    if (restoreFocus) trigger?.focus();
  }

  async function openVintageGapProduct(parentCode) {
    if (!currentRequest || !vintageGapPayload) return;
    const targetMonth = vintageGapPayload.target_month;
    closeVintageGapDrilldown();
    if (!chartDialog.hidden) closeChartDialog();
    activateSubpanel("history", "product");
    activate("history", { historyMode: "push" });
    await fetchModule("product", {
      ...currentRequest,
      product_parent_code: Number(parentCode),
      product_target_month: targetMonth,
    });
  }

  function revisionEffectivenessOverlay(month, point) {
    const points = month.points || [];
    const score = point.revision_effectiveness_score;
    const errorRemoved = point.cumulative_error_removed_kl;
    const errorRemovedLabel =
      errorRemoved >= 0
        ? kl(errorRemoved)
        : `${kl(Math.abs(errorRemoved))} added`;
    const currentIndex = Math.max(0, Number(point.vintage_index || 1) - 1);
    const helpful = count(point.helpful_revision_count);
    const harmful = count(point.harmful_revision_count);
    const neutral = count(point.neutral_revision_count);
    const scoreRows = [
      [
        "Accuracy gain · 50%",
        point.accuracy_gain_score,
        errorRemoved >= 0
          ? `${Math.round((errorRemoved / Math.max(points[0].absolute_error_kl || 1, 1)) * 100)}% of starting error removed`
          : `${Math.round((Math.abs(errorRemoved) / Math.max(points[0].absolute_error_kl || 1, 1)) * 100)}% of starting error added`,
      ],
      [
        "Revision efficiency · 30%",
        point.revision_efficiency_score,
        `${(Math.abs(errorRemoved) / Math.max(point.cumulative_movement_kl || 1, 1)).toFixed(2)} KL error ${errorRemoved >= 0 ? "removed" : "added"} per 1 KL movement`,
      ],
      [
        "Consistency · 20%",
        point.revision_consistency_score,
        `${helpful} helpful · ${harmful} harmful · ${neutral} neutral revisions`,
      ],
    ];
    const scoreBars = scoreRows
      .map(
        ([label, value, note]) =>
          `<div class="revision-effectiveness__component"><div class="revision-effectiveness__component-head"><span>${escapeHtml(label)}</span><b>${number(value, 0)}</b></div><div class="revision-effectiveness__track"><i style="width:${Math.max(0, Math.min(100, value))}%"></i></div><small>${escapeHtml(note)}</small></div>`,
      )
      .join("");
    const microWidth = 430;
    const microHeight = 150;
    const microLeft = 26;
    const microRight = 408;
    const microTop = 15;
    const microBottom = 116;
    const microY = (value) =>
      microBottom - (value / 100) * (microBottom - microTop);
    const visiblePoints = points.slice(0, currentIndex + 1);
    const microStep = (microRight - microLeft) / Math.max(points.length - 1, 1);
    let microPath = `M ${microLeft} ${microY(visiblePoints[0]?.revision_effectiveness_score || 50)}`;
    visiblePoints.slice(1).forEach((visiblePoint, index) => {
      microPath += ` H ${microLeft + (index + 1) * microStep} V ${microY(visiblePoint.revision_effectiveness_score)}`;
    });
    const microGrid = [40, 60, 80]
      .map(
        (tick) =>
          `<line x1="${microLeft}" x2="${microRight}" y1="${microY(tick)}" y2="${microY(tick)}"/>`,
      )
      .join("");
    const microNodes = visiblePoints
      .map((visiblePoint, index) => {
        const cx = microLeft + index * microStep;
        const cy = microY(visiblePoint.revision_effectiveness_score);
        return `<circle cx="${cx}" cy="${cy}" r="${index === currentIndex ? 5 : 4}"/><text x="${cx}" y="${cy - 8}" text-anchor="middle">${number(visiblePoint.revision_effectiveness_score, 0)}</text><text x="${cx}" y="${microBottom + 18}" text-anchor="middle">V${index + 1}</text>`;
      })
      .join("");
    return `<div class="revision-effectiveness" data-effectiveness-tone="${effectivenessScoreTone(score)}"><div class="revision-effectiveness__summary"><div class="revision-effectiveness__score"><strong>${number(score, 0)}</strong><span>Revision effectiveness<br/>out of 100</span><em>${escapeHtml(effectivenessScoreLabel(score))}</em></div><div class="revision-effectiveness__components">${scoreBars}</div><div class="revision-effectiveness__evolution"><p class="eyebrow">Score evolution within target month</p><svg viewBox="0 0 ${microWidth} ${microHeight}" role="img" aria-label="${escapeHtml(`${monthLabel(month.snop_month)} score evolution through vintage V${point.vintage_index}`)}"><g class="revision-effectiveness__micro-grid">${microGrid}</g><path d="${microPath}"/><g class="revision-effectiveness__micro-points">${microNodes}</g></svg><div><span>V1 = neutral starting index</span><span>V${point.vintage_index} score = ${number(score, 0)}</span></div></div></div><dl class="revision-effectiveness__metrics"><div><dt>Oldest error</dt><dd>${escapeHtml(kl(points[0]?.absolute_error_kl))}</dd></div><div><dt>Current error</dt><dd>${escapeHtml(kl(point.absolute_error_kl))}</dd></div><div><dt>Error ${errorRemoved >= 0 ? "removed" : "added"}</dt><dd class="${errorRemoved >= 0 ? "good" : "bad"}">${escapeHtml(errorRemovedLabel)}</dd></div><div><dt>Total movement</dt><dd>${escapeHtml(kl(point.cumulative_movement_kl))}</dd></div><div><dt>Net forecast change</dt><dd>${escapeHtml(point.vintage_index === points.length ? pct(month.latest_delta_pct) : "In progress")}</dd></div><div><dt>Vintage reached</dt><dd>V${count(point.vintage_index)} of ${count(points.length)}</dd></div></dl><div class="revision-effectiveness__evidence"><span><b>${helpful}</b> helpful vintage steps</span><span><b>${harmful}</b> harmful</span><span><b>${neutral}</b> neutral</span><span>Fixed cohort · <b>${count(month.product_count)} products</b></span></div></div>`;
  }

  function openRevisionEffectiveness(month, point, trigger) {
    const dialog = document.querySelector("#revision-effectiveness-dialog");
    const body = dialog.querySelector("[data-effectiveness-body]");
    dialog.querySelector("[data-effectiveness-eyebrow]").textContent =
      `Selected target month · ${String(activeRevisionPayload()?.request?.source || "selected").toUpperCase()} · vintage V${point.vintage_index}`;
    dialog.querySelector("[data-effectiveness-title]").textContent =
      `${monthLabel(month.snop_month)} revision breakdown`;
    dialog.querySelector("[data-effectiveness-subtitle]").textContent =
      `Balanced score accumulated through forecast vintage V${point.vintage_index}.`;
    setHtml(body, revisionEffectivenessOverlay(month, point));
    dialog.hidden = false;
    document.body.classList.add("has-revision-effectiveness-dialog");
    revisionEffectivenessTrigger = trigger;
    dialog
      .querySelector('[data-action="revision-effectiveness-close"]')
      .focus();
  }

  function closeRevisionEffectiveness({ restoreFocus = false } = {}) {
    const dialog = document.querySelector("#revision-effectiveness-dialog");
    if (dialog.hidden) return;
    dialog.hidden = true;
    document.body.classList.remove("has-revision-effectiveness-dialog");
    const trigger = revisionEffectivenessTrigger;
    revisionEffectivenessTrigger = null;
    if (restoreFocus) trigger?.focus();
  }

  function openRevisionEffectivenessPoint(effectivenessPoint) {
    const history = activeRevisionPayload()?.revision_history;
    const month = (history?.months || []).find(
      (candidate) =>
        candidate.snop_month === effectivenessPoint.dataset.targetMonth,
    );
    const point =
      month?.points?.[Number(effectivenessPoint.dataset.vintageIndex)];
    if (!month || !point) return;
    openRevisionEffectiveness(month, point, effectivenessPoint);
  }

  function revisionHistoryChart(history) {
    const months = (history?.months || []).slice(-6);
    if (!months.length) return emptyVisual("No revision effectiveness history");
    const width = 720;
    const height = 300;
    const left = 64;
    const right = 708;
    const top = 24;
    const bottom = 224;
    const labelY = 248;
    const y = (value) => bottom - (value / 100) * (bottom - top);
    const bandWidth = (right - left) / months.length;
    const grid = [0, 20, 40, 50, 60, 80, 100]
      .map(
        (value) =>
          `<line class="${value === 50 ? "revision-history__baseline" : ""}" x1="${left}" y1="${y(value)}" x2="${right}" y2="${y(value)}"/><text x="${left - 9}" y="${y(value) + 3}" text-anchor="end">${value}</text>`,
      )
      .join("");
    const bands = months
      .map((month, monthIndex) => {
        const bandLeft = left + bandWidth * monthIndex;
        const innerLeft = bandLeft + 12;
        const innerRight = bandLeft + bandWidth - 12;
        const points = (month.points || []).filter((point) =>
          finite(point.revision_effectiveness_score),
        );
        const coordinates = points.map((point, pointIndex) => ({
          x:
            innerLeft +
            (pointIndex / Math.max(points.length - 1, 1)) *
              (innerRight - innerLeft),
          y: y(point.revision_effectiveness_score),
          point,
        }));
        const segments = coordinates
          .slice(1)
          .map((current, index) => {
            const previous = coordinates[index];
            const change = current.point.score_change || 0;
            let tone = "neutral";
            if (change > 1) tone = "improved";
            else if (change < -1) tone = "worsened";
            const label = `${monthLabel(month.snop_month)}, vintage V${current.point.vintage_index}, balanced score ${number(current.point.revision_effectiveness_score, 0)}, change ${pp(change)}`;
            return `<path class="revision-history__path revision-history__segment--${tone}" d="M ${previous.x} ${previous.y} H ${current.x} V ${current.y}"/><path class="chart__point revision-history__segment-hit" d="M ${previous.x} ${previous.y} H ${current.x} V ${current.y}" tabindex="0" role="img" aria-label="${escapeHtml(label)}" data-tooltip-kind="revision-effectiveness-segment" data-tooltip-source="${escapeHtml(String(history.source || "selected").toUpperCase())}" data-tooltip-month="${escapeHtml(monthLabel(month.snop_month))}" data-tooltip-vintage="${escapeHtml(count(current.point.vintage_index))}" data-tooltip-score="${escapeHtml(number(current.point.revision_effectiveness_score, 0))}" data-tooltip-score-change="${escapeHtml(pp(change))}" data-tooltip-accuracy-score="${escapeHtml(number(current.point.accuracy_gain_score, 0))}" data-tooltip-efficiency-score="${escapeHtml(number(current.point.revision_efficiency_score, 0))}" data-tooltip-consistency-score="${escapeHtml(number(current.point.revision_consistency_score, 0))}" data-tooltip-error-removed="${escapeHtml(signedKl(current.point.cumulative_error_removed_kl))}" data-tooltip-movement="${escapeHtml(kl(current.point.cumulative_movement_kl))}"/>`;
          })
          .join("");
        const nodes = coordinates
          .map(({ x, y: pointY, point }, pointIndex) => {
            const baseline = pointIndex === 0;
            const selected =
              monthIndex === months.length - 1 &&
              pointIndex === points.length - 1;
            let tone = "neutral";
            if (point.score_change > 1) tone = "improved";
            else if (point.score_change < -1) tone = "worsened";
            const nodeClass = baseline
              ? "revision-history__node--baseline"
              : `revision-history__node--${tone}`;
            const label = `${monthLabel(month.snop_month)}, vintage V${point.vintage_index}, balanced score ${number(point.revision_effectiveness_score, 0)}`;
            return `<g class="chart__point revision-history__point${selected ? " is-selected" : ""}" tabindex="0" role="button" aria-label="${escapeHtml(`${label}. Open detailed breakdown.`)}" data-tooltip-kind="revision-effectiveness" data-target-month="${escapeHtml(month.snop_month)}" data-vintage-index="${count(point.vintage_index - 1)}" data-tooltip-source="${escapeHtml(String(history.source || "selected").toUpperCase())}" data-tooltip-month="${escapeHtml(monthLabel(month.snop_month))}" data-tooltip-vintage="${escapeHtml(count(point.vintage_index))}" data-tooltip-score="${escapeHtml(number(point.revision_effectiveness_score, 0))}" data-tooltip-score-change="${escapeHtml(pp(point.score_change))}" data-tooltip-accuracy-score="${escapeHtml(number(point.accuracy_gain_score, 0))}" data-tooltip-efficiency-score="${escapeHtml(number(point.revision_efficiency_score, 0))}" data-tooltip-consistency-score="${escapeHtml(number(point.revision_consistency_score, 0))}" data-tooltip-error-removed="${escapeHtml(signedKl(point.cumulative_error_removed_kl))}" data-tooltip-movement="${escapeHtml(kl(point.cumulative_movement_kl))}"><circle class="revision-history__node ${nodeClass}" cx="${x}" cy="${pointY}" r="${selected ? 5.1 : 4.2}"/><text class="revision-history__score" x="${x}" y="${pointY - 8}" text-anchor="middle">${number(point.revision_effectiveness_score, 0)}</text><text class="revision-history__vintage" x="${x}" y="${bottom + 13}" text-anchor="middle">V${count(point.vintage_index)}</text></g>`;
          })
          .join("");
        const monthDate = monthLabel(month.snop_month).split(" ");
        return `<g class="revision-history__band" data-target-month="${escapeHtml(month.snop_month)}"><rect class="revision-history__band-bg" x="${bandLeft}" y="${top}" width="${bandWidth}" height="${bottom - top}"/><line class="revision-history__separator" x1="${bandLeft}" y1="${top}" x2="${bandLeft}" y2="${bottom}"/>${segments}${nodes}<text class="revision-history__month" x="${bandLeft + bandWidth / 2}" y="${labelY}"><tspan x="${bandLeft + bandWidth / 2}">${escapeHtml(monthDate[0])}</tspan><tspan class="chart__axis-year" x="${bandLeft + bandWidth / 2}" dy="14">${escapeHtml(monthDate[1])}</tspan></text></g>`;
      })
      .join("");
    return `<div class="revision-history-chart"><svg class="chart chart--revision-history" viewBox="0 0 ${width} ${height}" role="img" aria-label="Revision effectiveness evolution across the latest ${months.length} target months and five forecast vintages per month"><title>Revision effectiveness evolution by target month and forecast vintage</title><text class="revision-history__axis-title" x="15" y="${(top + bottom) / 2}" transform="rotate(-90 15 ${(top + bottom) / 2})">Balanced revision effectiveness score · V1 baseline = 50</text><g class="chart__grid revision-history__grid">${grid}</g>${bands}<line class="revision-history__separator" x1="${right}" y1="${top}" x2="${right}" y2="${bottom}"/></svg><div class="revision-history__legend"><span>Each month resets at V1</span><span class="revision-history__legend-outcome"><i class="revision-history__legend-improved"></i>Score improved</span><span class="revision-history__legend-outcome"><i class="revision-history__legend-worsened"></i>Score declined</span><span class="revision-history__legend-outcome"><i class="revision-history__legend-neutral"></i>Neutral</span><span><i></i>Latest vintage</span><span>Click any vintage for the breakdown</span></div></div>`;
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
    const scatterWindowStart = scatterPopulation[0]?.window_start_month;
    const scatterWindowEnd = scatterPopulation[0]?.window_end_month;
    const scatterWindowLabel =
      scatterWindowStart && scatterWindowEnd
        ? `${monthLabel(scatterWindowStart)}–${monthLabel(scatterWindowEnd)} · six complete target months × five vintages`
        : "No complete six-month, five-vintage window available";
    const latestActualMonth = payload.revision_history?.latest_actual_month;
    const revisionWindowLabel = latestActualMonth
      ? `6 target months through ${monthLabel(latestActualMonth)} · latest complete five-vintage actual`
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
          "accuracy-delta",
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
          "effectiveness",
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
          "error-improvement",
        )}
      </div>
      <div class="revision-selection-bar"${revisionScatterSelection.size ? "" : " hidden"}><span class="revision-selection-bar__copy"><span><b>${count(revisionScatterSelection.size)}</b> parent${revisionScatterSelection.size === 1 ? "" : "s"} selected</span><small>Scatter keeps all parents visible for context; KPIs and revision evidence follow this selection.</small></span><button class="btn btn--quiet" type="button" data-drilldown-clear>Clear selection</button></div>
      <div class="revision-layout">
        <section class="frame"><header class="frame__head"><div><div class="frame__title-row"><h3 class="frame__title">Revision effectiveness evolution · ${source.toUpperCase()}</h3>${revisionEffectivenessGuideButton()}</div><p class="frame__sub">${escapeHtml(revisionWindowLabel)} · five vintages per target month · V1 indexed to 50</p></div><div class="frame__actions"><span class="frame__metric">up ${pct(metrics.revised_up_pct)} · down ${pct(metrics.revised_down_pct)}</span>${revisionFullscreenMenu("revision-history", "scatter")}</div></header><div class="outcome-body"><div class="outcome-strip">${["improved", "worsened", "neutral", "unchanged"].map((category) => `<span class="outcome outcome--${category === "improved" ? "good" : category === "worsened" ? "bad" : category === "neutral" ? "neutral" : "idle"}"><b>${labelize(category)}</b><button class="outcome__drilldown" type="button" data-drilldown-category="${category}" aria-label="Open ${category} parent-code drill-down" aria-haspopup="dialog" aria-expanded="false"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 4h12v12H4zM7 10h6M10 7v6"/></svg></button><span class="outcome__content">${revisionOutcomeInstructions(category, actions)}<strong>${count(diagnostics.get(category)?.observations || 0)}</strong></span></span>`).join("")}</div><div class="revision-history-body">${revisionHistoryChart(payload.revision_history)}</div></div></section>
        <section class="frame"><header class="frame__head"><div><div class="frame__title-row"><h3 class="frame__title">Parent vintage trend vs improvement score</h3>${revisionScatterGuideButton()}</div><p class="frame__sub">One bubble per parent · ${escapeHtml(scatterWindowLabel)}</p><p class="frame__scope-note"><b>Out of scope · super seasonal:</b> PA Bodylot · JFB Powder · RK Cooling · Saff Honey · SP Petroleum Jelly (all SKUs) · PCNO EJ (all matching SKUs)</p></div><div class="frame__actions"><span class="frame__metric">${count(scatterRows.length)} ${source.toUpperCase()} parent bubbles</span>${revisionFullscreenMenu("revision", "step chart")}</div></header><div class="frame__body">${scatterChart(scatterPopulation, "revision_score_pct", "vintage_improvement_score_pp", `${source.toUpperCase()} parent vintage trend versus improvement score`, { source, tolerance: 0.01 })}</div></section>
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

  function scatterAbsoluteError(row) {
    return Math.max(
      0,
      Number(row.absolute_error_kl ?? row.vintage_b_absolute_error_kl) || 0,
    );
  }

  function scatterSizeLabel(mode) {
    if (mode === "error") {
      return "Size = latest-vintage absolute error (capped √ scaled)";
    }
    if (mode === "volume") {
      return "Size = actual volume (capped √ scaled)";
    }
    return "Top-volume points outlined; size off";
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

  function revisionFullscreenMenu(kind, partnerLabel) {
    return `<label class="chart-expand-select"><span class="sr-only">Choose full-screen view</span><select data-chart-fullscreen-menu data-chart-fullscreen-kind="${escapeHtml(kind)}" aria-label="Choose full-screen view"><option value="" selected disabled hidden>Full screen…</option><option value="single">View only this chart</option><option value="paired">View with ${escapeHtml(partnerLabel)}</option></select></label>`;
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
    chart.querySelectorAll("[data-scatter-zoom]").forEach((select) => {
      select.value = String(Math.round(revisionScatterZoom * 100));
    });
    chart.querySelectorAll("[data-scatter-size-label]").forEach((label) => {
      label.textContent = scatterSizeLabel(revisionScatterMode);
    });
    chart.querySelectorAll(".scatter__point").forEach((point) => {
      point.setAttribute(
        "r",
        revisionScatterMode === "error"
          ? point.dataset.radiusError
          : revisionScatterMode === "volume"
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
    const absoluteErrors = valid
      .map(scatterAbsoluteError)
      .sort((leftValue, rightValue) => leftValue - rightValue);
    const lowerError = scatterQuantile(absoluteErrors, 0.05);
    const upperError = Math.max(
      scatterQuantile(absoluteErrors, 0.95),
      lowerError + 1,
    );
    const errorRange = upperError - lowerError;
    const errorRadius = (absoluteError) => {
      const normalized = Math.max(
        0,
        Math.min(1, (absoluteError - lowerError) / errorRange),
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
        (leftRow, rightRow) =>
          scatterAbsoluteError(rightRow) - scatterAbsoluteError(leftRow),
      )
      .map((row) => {
        const outcome = row.revision_outcome || "neutral";
        const direction = row.revision_direction || "unchanged";
        const actual = scatterActual(row);
        const absoluteError = scatterAbsoluteError(row);
        const isTopVolume =
          actual >= topVolumeThreshold && actual > lowerActual;
        const isOutlier =
          Math.abs(row.__scatterX) >= revisionOutlierThreshold ||
          Math.abs(row.__scatterY) >= improvementOutlierThreshold;
        const scoreMode = finite(row.vintage_improvement_score_pp);
        const scatterKey = `${row.parent_code ?? ""}`;
        const accessibleLabel = scoreMode
          ? `${source.toUpperCase()} product ${row.parent_code}, ${monthLabel(row.window_start_month)} through ${monthLabel(row.window_end_month)}, latest-vintage absolute error ${kl(absoluteError)}, forecast trend ${signedPct(row[xKey])} of actual per vintage, vintage improvement score ${pp(row[yKey])}, ${outcome}`
          : `${source.toUpperCase()} product ${row.parent_code}, ${monthLabel(row.snop_month)}, actual ${kl(row.actual_kl)}, Vintage A ${kl(row.vintage_a_forecast_kl)}, Vintage B ${kl(row.vintage_b_forecast_kl)}, revision ${signedKl(row[xKey])}, error improvement ${signedKl(row[yKey])}, ${outcome}`;
        return `<circle class="chart__point scatter__point scatter--${escapeHtml(outcome)}${isTopVolume ? " scatter__point--top-volume" : ""}" cx="${x(row.__scatterX)}" cy="${y(row.__scatterY)}" r="${uniformRadius}" tabindex="0" role="img" aria-label="${escapeHtml(accessibleLabel)}" data-scatter-key="${escapeHtml(scatterKey)}" data-top-volume="${isTopVolume}" data-outlier="${isOutlier}" data-radius-uniform="${uniformRadius}" data-radius-error="${errorRadius(absoluteError)}" data-radius-volume="${volumeRadius(row.actual_kl)}" data-tooltip-kind="revision" data-tooltip-score-mode="${scoreMode ? "vintage-window" : "pair"}" data-tooltip-source="${escapeHtml(source.toUpperCase())}" data-tooltip-code="${escapeHtml(row.parent_code)}" data-tooltip-description="${escapeHtml(row.parent_description || "Description unavailable")}" data-tooltip-brand="${escapeHtml(row.brand || "Unmapped brand")}" data-tooltip-sku-class="${escapeHtml(row.sku_class || "Unclassified")}" data-tooltip-month="${escapeHtml(monthLabel(row.snop_month))}" data-tooltip-window="${escapeHtml(`${monthLabel(row.window_start_month)}–${monthLabel(row.window_end_month)}`)}" data-tooltip-months="${escapeHtml(row.target_months_used)}" data-tooltip-vintages="${escapeHtml(row.vintages_per_month)}" data-tooltip-transitions="${escapeHtml(row.transitions_used)}" data-tooltip-winsorized="${escapeHtml(row.winsorized_months)}" data-tooltip-improving="${escapeHtml(row.improving_months)}" data-tooltip-degrading="${escapeHtml(row.degrading_months)}" data-tooltip-neutral="${escapeHtml(row.neutral_months)}" data-tooltip-direction="${escapeHtml(labelize(direction))}" data-tooltip-revision="${escapeHtml(scoreMode ? signedPct(row[xKey]) : signedKl(row[xKey]))}" data-tooltip-raw-revision="${escapeHtml(scoreMode ? signedPct(row.raw_revision_score_pct) : signedKl(row[xKey]))}" data-tooltip-improvement="${escapeHtml(scoreMode ? pp(row[yKey]) : signedKl(row[yKey]))}" data-tooltip-raw-improvement="${escapeHtml(scoreMode ? pp(row.raw_vintage_improvement_score_pp) : signedKl(row[yKey]))}" data-tooltip-improvement-raw="${escapeHtml(row[yKey])}" data-tooltip-actual="${escapeHtml(kl(row.actual_kl))}" data-tooltip-absolute-error="${escapeHtml(kl(absoluteError))}" data-tooltip-vintage-a="${escapeHtml(kl(row.vintage_a_forecast_kl))}" data-tooltip-vintage-a-scope="${escapeHtml(`M−${row.vintage_a_horizon_months ?? "—"} · ${monthLabel(row.vintage_a_calculation_month)}`)}" data-tooltip-vintage-b="${escapeHtml(kl(row.vintage_b_forecast_kl))}" data-tooltip-vintage-b-scope="${escapeHtml(`M−${row.vintage_b_horizon_months ?? "—"} · ${monthLabel(row.vintage_b_calculation_month)}`)}" data-tooltip-error-a="${escapeHtml(kl(row.vintage_a_absolute_error_kl))}" data-tooltip-error-b="${escapeHtml(kl(row.vintage_b_absolute_error_kl))}" data-tooltip-outcome="${escapeHtml(labelize(outcome))}"></circle>`;
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
    return `<div class="revision-scatter" data-revision-scatter data-scatter-mode="${revisionScatterMode}" data-scatter-density="${revisionScatterDensity ? "on" : "off"}" data-scatter-focus="${revisionScatterFocus}"><div class="scatter-toolbar" role="toolbar" aria-label="Scatter chart display controls"><span class="scatter-toolbar__label">Size</span>${scatterControl("mode-error", "Error", revisionScatterMode === "error", 'data-scatter-mode="error" aria-label="Size bubbles by latest-vintage absolute error"')}${scatterControl("mode-volume", "Volume", revisionScatterMode === "volume", 'data-scatter-mode="volume" aria-label="Size bubbles by actual volume"')}${scatterControl("mode-uniform", "Uniform", revisionScatterMode === "uniform", 'data-scatter-mode="uniform" aria-label="Use uniform bubble sizes"')}${scatterControl("density", "Density", revisionScatterDensity, "data-scatter-density")}${scatterControl("focus-top", "Top volume", revisionScatterFocus === "top-volume", 'data-scatter-focus="top-volume"')}${scatterControl("focus-outliers", "Outliers", revisionScatterFocus === "outliers", 'data-scatter-focus="outliers"')}${scatterSkuClassSelect(rows)}<span class="scatter-toolbar__spacer"></span><label class="scatter-toolbar__filter scatter-toolbar__zoom"><span>Zoom</span><select data-scatter-zoom aria-label="Scatter chart zoom percentage"><option value="100">100%</option><option value="125">125%</option><option value="150">150%</option><option value="175">175%</option><option value="200">200%</option><option value="225">225%</option><option value="250">250%</option><option value="275">275%</option><option value="300">300%</option></select></label><button class="scatter-control" type="button" data-scatter-action="zoom-reset">Reset view</button><button class="scatter-control" type="button" data-scatter-action="clear-selection">Clear selection</button></div><svg class="chart chart--revision-scatter" viewBox="0 0 ${width} ${height}" data-base-width="${width}" data-base-height="${height}" data-zoom-center-x="${xZero}" data-zoom-center-y="${yZero}" role="img" aria-label="${escapeHtml(label)}"><rect class="scatter__tolerance" x="${xZero - toleranceWidth / 2}" y="${top}" width="${toleranceWidth}" height="${bottom - top}"/><rect class="scatter__tolerance" x="${left}" y="${yZero - toleranceHeight / 2}" width="${right - left}" height="${toleranceHeight}"/><g class="chart__grid scatter__grid">${xTicks}${yTicks}</g>${density}${quadrants}<line class="zero-line" x1="${xZero}" y1="${top}" x2="${xZero}" y2="${bottom}"/><line class="zero-line" x1="${left}" y1="${yZero}" x2="${right}" y2="${yZero}"/><g class="scatter__crosshair" aria-hidden="true"><line class="scatter__crosshair-x" x1="${xZero}" y1="${top}" x2="${xZero}" y2="${bottom}"/><line class="scatter__crosshair-y" x1="${left}" y1="${yZero}" x2="${right}" y2="${yZero}"/></g><g class="scatter">${circles}</g><text class="scatter__axis-title" x="${(left + right) / 2}" y="${height - 17}">${escapeHtml(xAxisTitle)}</text><text class="scatter__axis-title" x="18" y="${(top + bottom) / 2}" transform="rotate(-90 18 ${(top + bottom) / 2})">${escapeHtml(yAxisTitle)}</text></svg><div class="revision-scatter__legend"><span><i class="scatter-key scatter-key--improved"></i>Improved</span><span><i class="scatter-key scatter-key--worsened"></i>Worsened</span><span><i class="scatter-key scatter-key--neutral"></i>Neutral</span><span><i class="scatter-key scatter-key--density"></i>Density</span><span><i class="scatter-key scatter-key--size"></i><span data-scatter-size-label>${scatterSizeLabel(revisionScatterMode)}</span></span>${scoreEvidence}<span>Zoom menu · drag pan · Shift-drag select</span>${revisionScatterSelection.size ? "<span>Selected parents highlighted · others stay pale for context</span>" : ""}</div></div>`;
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

  const FINANCIAL_MONTH_NAMES = [
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
    "Jan",
    "Feb",
    "Mar",
  ];

  function yearOverlayRows(history) {
    return history?.points?.rows || [];
  }

  function financialYearLabel(year) {
    return `FY${String(year).slice(-2).padStart(2, "0")}`;
  }

  function financialYearForMonth(value) {
    const date = new Date(`${value}T00:00:00Z`);
    const year = date.getUTCFullYear();
    return date.getUTCMonth() + 1 >= 4 ? year : year - 1;
  }

  function financialMonthForMonth(value) {
    const month = new Date(`${value}T00:00:00Z`).getUTCMonth() + 1;
    return month >= 4 ? month - 3 : month + 9;
  }

  function yearOverlayYears(history) {
    return [
      ...new Set(
        yearOverlayRows(history).map((row) =>
          Number(row.fiscal_year ?? financialYearForMonth(row.snop_month)),
        ),
      ),
    ]
      .filter(Number.isFinite)
      .sort((a, b) => a - b);
  }

  function yearOverlayColor(year, years) {
    const colors = [
      "var(--amber)",
      "var(--teal)",
      "var(--series-actual)",
      "var(--series-vintage-b)",
      "var(--red)",
    ];
    const index = Math.max(0, years.indexOf(year));
    return colors[index] || `hsl(${(index * 137.508 + 28) % 360} 52% 42%)`;
  }

  function yearOverlaySourceColor(source) {
    return source === "tm" ? "var(--amber)" : "var(--teal)";
  }

  function syncYearOverlaySelection(history) {
    const years = yearOverlayYears(history);
    const key = `${history?.source || ""}:${years.join(",")}`;
    if (key === yearOverlayKey) return years;
    const retained = new Set(
      [...yearOverlayVisible].filter((year) => years.includes(year)),
    );
    yearOverlayVisible = retained.size ? retained : new Set(years);
    yearOverlayKey = key;
    return years;
  }

  function yearOverlayLegend(history) {
    const years = syncYearOverlaySelection(history);
    const modeControls = `<div class="year-overlay-modes" role="group" aria-label="History chart layout"><button type="button" data-year-overlay-mode="fy" aria-pressed="${yearOverlayMode === "fy"}">FY overlay</button><button type="button" data-year-overlay-mode="long" aria-pressed="${yearOverlayMode === "long"}">Long horizon</button></div>`;
    const buttons = years
      .map(
        (year) =>
          `<button class="year-overlay-control${yearOverlayVisible.has(year) ? "" : " is-off"}" type="button" data-year-overlay-year="${year}" aria-pressed="${yearOverlayVisible.has(year)}" style="--year-color:${yearOverlayColor(year, years)}" title="Click to toggle · double-click to isolate"><i></i>${financialYearLabel(year)}</button>`,
      )
      .join("");
    const yearControls =
      yearOverlayMode === "fy" && years.length
        ? `<div class="year-overlay-years">${buttons}<button class="year-overlay-reset" type="button" data-year-overlay-reset>Reset</button></div>`
        : "";
    return `${modeControls}${yearControls}<span class="year-overlay-style"><i class="year-overlay-line"></i>Actual</span><span class="year-overlay-style"><i class="year-overlay-line year-overlay-line--forecast"></i>Forecast</span>`;
  }

  function yearOverlayPath(values, x, y, className, color) {
    const groups = [];
    let group = [];
    values.forEach((value, index) => {
      if (finite(value)) group.push({ x: x(index + 1), y: y(value) });
      else if (group.length) {
        groups.push(group);
        group = [];
      }
    });
    if (group.length) groups.push(group);
    return groups
      .map(
        (points) =>
          `<path class="year-overlay-path ${className}" d="${smoothLinePath(points)}" stroke="${color}"></path>`,
      )
      .join("");
  }

  function renderYearOverlay(detail = currentPayload?.product_detail) {
    const history = detail?.year_overlay;
    const summary = document.querySelector("[data-year-overlay-summary]");
    if (summary) {
      const source = history?.source ? history.source.toUpperCase() : "—";
      const actualThrough = history?.actual_through
        ? monthLabel(history.actual_through)
        : "no actual cutoff";
      const forecastRun = history?.forecast_run
        ? monthLabel(history.forecast_run)
        : "no forward run";
      const layout =
        yearOverlayMode === "fy"
          ? "Apr–Mar FY comparison"
          : "Continuous monthly history";
      summary.textContent = `${layout} · ${source} · actual through ${actualThrough} · forecast run ${forecastRun}`;
    }
    setHtml(
      document.querySelector("[data-year-overlay-legend]"),
      yearOverlayLegend(history),
    );
    setHtml(
      document.querySelector("[data-postmortem-performance-chart]"),
      productYearOverlayChart(history),
    );
    if (!chartDialog.hidden && fullscreenChart === "postmortem-performance")
      renderFullscreenChart();
  }

  function toggleYearOverlay(year, isolate = false) {
    if (isolate) {
      yearOverlayVisible = new Set([year]);
    } else if (yearOverlayVisible.has(year)) {
      yearOverlayVisible.delete(year);
    } else {
      yearOverlayVisible.add(year);
    }
    renderYearOverlay();
  }

  function resetYearOverlay() {
    const years = yearOverlayYears(
      currentPayload?.product_detail?.year_overlay,
    );
    yearOverlayVisible = new Set(years);
    renderYearOverlay();
  }

  function yearOverlayGrid(min, max, left, right, top, bottom) {
    return [0, 0.25, 0.5, 0.75, 1]
      .map((ratio) => {
        const value = max - ratio * (max - min);
        const gridY = top + ratio * (bottom - top);
        return `<line x1="${left}" y1="${gridY}" x2="${right}" y2="${gridY}"></line><text x="${left - 8}" y="${gridY + 3}">${escapeHtml(number(value, 0))}</text>`;
      })
      .join("");
  }

  function yearOverlayMonthHit({
    x,
    index,
    total,
    top,
    bottom,
    month,
    source,
    rows,
  }) {
    const hitWidth = (x(total) - x(1)) / Math.max(1, total - 1);
    const left = Math.max(x(1), x(index + 1) - hitWidth / 2);
    const right = Math.min(x(total), x(index + 1) + hitWidth / 2);
    const summary = rows.map((row) => `${row.label} ${row.value}`).join(", ");
    return `<rect class="chart__month-hit chart__point year-overlay-month-hit" x="${left}" y="${top}" width="${Math.max(1, right - left)}" height="${bottom - top}" tabindex="0" role="img" aria-label="${escapeHtml(`${month}: ${summary}`)}" data-tooltip-kind="year-overlay" data-tooltip-source="${escapeHtml(source)}" data-tooltip-month="${escapeHtml(month)}" data-tooltip-year-series="${escapeHtml(JSON.stringify(rows))}"/>`;
  }

  function productFiscalYearOverlayChart(history) {
    const rows = yearOverlayRows(history);
    const years = syncYearOverlaySelection(history);
    if (!rows.length || !years.length)
      return emptyVisual("No actual or forward forecast history");
    const rowsByYear = new Map(
      years.map((year) => [
        year,
        Array.from({ length: 12 }, () => ({ actual: null, forecast: null })),
      ]),
    );
    rows.forEach((row) => {
      const year = Number(
        row.fiscal_year ?? financialYearForMonth(row.snop_month),
      );
      const month = Number(
        row.fiscal_month ?? financialMonthForMonth(row.snop_month),
      );
      const values = rowsByYear.get(year);
      if (values && month >= 1 && month <= 12) {
        values[month - 1] = {
          actual: finite(row.actual_kl) ? row.actual_kl : null,
          forecast: finite(row.forecast_kl) ? row.forecast_kl : null,
        };
      }
    });
    const active = years.filter((year) => yearOverlayVisible.has(year));
    const values = active.flatMap((year) =>
      (rowsByYear.get(year) || []).flatMap((point) => [
        point.actual,
        point.forecast,
      ]),
    );
    const [min, max] = chartExtent(values);
    const width = 900;
    const height = 300;
    const left = 58;
    const right = 866;
    const top = 28;
    const bottom = 252;
    const x = (month) => left + ((month - 1) / 11) * (right - left);
    const y = (value) =>
      bottom - ((value - min) / Math.max(max - min, 0.001)) * (bottom - top);
    const monthLabels = FINANCIAL_MONTH_NAMES.map(
      (label, index) => `<text x="${x(index + 1)}" y="278">${label}</text>`,
    ).join("");
    const series = active
      .map((year) => {
        const yearPoints = rowsByYear.get(year) || [];
        const color = yearOverlayColor(year, years);
        const actual = yearPoints.map((point) => point.actual);
        const forecast = yearPoints.map((point) => point.forecast);
        const points = [
          ...actual.map((value, index) => ({ value, index, kind: "actual" })),
          ...forecast.map((value, index) => ({
            value,
            index,
            kind: "forecast",
          })),
        ]
          .filter((point) => finite(point.value))
          .map(
            (point) =>
              `<circle class="year-overlay-point ${point.kind}" cx="${x(point.index + 1)}" cy="${y(point.value)}" r="3.5" stroke="${color}"/>`,
          )
          .join("");
        return `${yearOverlayPath(actual, x, y, "actual", color)}${yearOverlayPath(forecast, x, y, "forecast", color)}${points}`;
      })
      .join("");
    const monthHits = FINANCIAL_MONTH_NAMES.map((month, index) => {
      const tooltipRows = active.flatMap((year) => {
        const point = rowsByYear.get(year)?.[index];
        return [
          finite(point?.actual)
            ? {
                label: `${financialYearLabel(year)} actual`,
                value: kl(point.actual),
              }
            : null,
          finite(point?.forecast)
            ? {
                label: `${financialYearLabel(year)} forecast`,
                value: kl(point.forecast),
              }
            : null,
        ].filter(Boolean);
      });
      if (!tooltipRows.length) return "";
      if (
        history.forecast_run &&
        active.some((year) => finite(rowsByYear.get(year)?.[index]?.forecast))
      ) {
        tooltipRows.push({
          label: "Forecast run",
          value: monthLabel(history.forecast_run),
        });
      }
      return yearOverlayMonthHit({
        x,
        index,
        total: 12,
        top,
        bottom,
        month: `${month} · FY comparison`,
        source: String(history.source || "").toUpperCase(),
        rows: tooltipRows,
      });
    }).join("");
    const cutoffMonth = history.actual_through
      ? financialMonthForMonth(history.actual_through)
      : null;
    const cutoff =
      cutoffMonth && cutoffMonth < 12
        ? `<line class="year-overlay-cutoff" x1="${x(cutoffMonth + 0.5)}" y1="${top}" x2="${x(cutoffMonth + 0.5)}" y2="${bottom}"></line><text class="year-overlay-cutoff-label" x="${x(cutoffMonth + 0.5) + 7}" y="${top + 11}">Actual through ${escapeHtml(monthLabel(history.actual_through))}</text>`
        : "";
    const empty = active.length
      ? ""
      : `<text class="year-overlay-empty" x="450" y="145" text-anchor="middle">No FYs selected · use Reset to restore the comparison</text>`;
    return `<svg class="chart postmortem-chart year-overlay-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Actual demand and forward forecast by FY"><title>Actual demand and forward forecast by FY</title><g class="year-overlay-grid">${yearOverlayGrid(min, max, left, right, top, bottom)}</g><text class="year-overlay-axis-unit" x="${left}" y="16">KL</text>${series}${empty}<g class="year-overlay-labels">${monthLabels}</g>${cutoff}<g class="year-overlay-month-hits">${monthHits}</g></svg>`;
  }

  function monthRange(start, end) {
    const months = [];
    const cursor = new Date(`${start}T00:00:00Z`);
    const last = new Date(`${end}T00:00:00Z`);
    while (cursor <= last) {
      months.push(cursor.toISOString().slice(0, 10));
      cursor.setUTCMonth(cursor.getUTCMonth() + 1);
    }
    return months;
  }

  function productLongHorizonChart(history) {
    const sourceRows = yearOverlayRows(history)
      .slice()
      .sort((a, b) => String(a.snop_month).localeCompare(String(b.snop_month)));
    if (!sourceRows.length)
      return emptyVisual("No actual or forward forecast history");
    const rowsByMonth = new Map(sourceRows.map((row) => [row.snop_month, row]));
    const rows = monthRange(
      sourceRows[0].snop_month,
      sourceRows[sourceRows.length - 1].snop_month,
    ).map(
      (snopMonth) =>
        rowsByMonth.get(snopMonth) || {
          snop_month: snopMonth,
          calendar_month: Number(snopMonth.slice(5, 7)),
          fiscal_year: financialYearForMonth(snopMonth),
          actual_kl: null,
          forecast_kl: null,
        },
    );
    const actual = rows.map((row) =>
      finite(row.actual_kl) ? row.actual_kl : null,
    );
    const forecast = rows.map((row) =>
      finite(row.forecast_kl) ? row.forecast_kl : null,
    );
    const [min, max] = chartExtent([...actual, ...forecast]);
    const width = 900;
    const height = 300;
    const left = 58;
    const right = 866;
    const top = 28;
    const bottom = 252;
    const x = (period) =>
      rows.length === 1
        ? (left + right) / 2
        : left + ((period - 1) / (rows.length - 1)) * (right - left);
    const y = (value) =>
      bottom - ((value - min) / Math.max(max - min, 0.001)) * (bottom - top);
    const actualColor = "var(--series-actual)";
    const forecastColor = yearOverlaySourceColor(history.source);
    const points = rows
      .flatMap((row, index) => [
        finite(row.actual_kl)
          ? { value: row.actual_kl, index, kind: "actual", color: actualColor }
          : null,
        finite(row.forecast_kl)
          ? {
              value: row.forecast_kl,
              index,
              kind: "forecast",
              color: forecastColor,
            }
          : null,
      ])
      .filter(Boolean)
      .map(
        (point) =>
          `<circle class="year-overlay-point ${point.kind}" cx="${x(point.index + 1)}" cy="${y(point.value)}" r="3.5" stroke="${point.color}"/>`,
      )
      .join("");
    const labels = rows
      .map((row, index) => {
        const calendarMonth = Number(
          row.calendar_month ?? String(row.snop_month).slice(5, 7),
        );
        const show =
          index === 0 ||
          index === rows.length - 1 ||
          index % 2 === 0 ||
          calendarMonth === 4;
        return show
          ? `<text x="${x(index + 1)}" y="278">${escapeHtml(monthLabel(row.snop_month).split(" ")[0])}</text>`
          : "";
      })
      .join("");
    const fiscalYears = [
      ...new Set(
        rows.map((row) =>
          Number(row.fiscal_year ?? financialYearForMonth(row.snop_month)),
        ),
      ),
    ];
    const fiscalSeparators = fiscalYears
      .map((year) => {
        const index = rows.findIndex(
          (row) =>
            Number(row.fiscal_year ?? financialYearForMonth(row.snop_month)) ===
            year,
        );
        const separatorX = index <= 0 ? left : x(index + 0.5);
        return `<line class="year-overlay-fy-separator" x1="${separatorX}" y1="${top}" x2="${separatorX}" y2="${bottom}"></line><text class="year-overlay-fy-label" x="${separatorX + 7}" y="${top + 11}">${financialYearLabel(year)}</text>`;
      })
      .join("");
    const cutoffIndex = history.actual_through
      ? rows.findIndex((row) => row.snop_month === history.actual_through)
      : -1;
    const cutoff =
      cutoffIndex >= 0 && cutoffIndex < rows.length - 1
        ? `<line class="year-overlay-cutoff" x1="${x(cutoffIndex + 1.5)}" y1="${top}" x2="${x(cutoffIndex + 1.5)}" y2="${bottom}"></line><text class="year-overlay-cutoff-label" x="${x(cutoffIndex + 1.5) + 7}" y="${top + 26}">Actual through ${escapeHtml(monthLabel(history.actual_through))}</text>`
        : "";
    const monthHits = rows
      .map((row, index) => {
        const year = Number(
          row.fiscal_year ?? financialYearForMonth(row.snop_month),
        );
        const hasValue = finite(row.actual_kl) || finite(row.forecast_kl);
        if (!hasValue) return "";
        const tooltipRows = [
          { label: "FY", value: financialYearLabel(year) },
          finite(row.actual_kl)
            ? { label: "Actual", value: kl(row.actual_kl) }
            : null,
          finite(row.forecast_kl)
            ? { label: "Forecast", value: kl(row.forecast_kl) }
            : null,
          finite(row.forecast_kl) && history.forecast_run
            ? { label: "Forecast run", value: monthLabel(history.forecast_run) }
            : null,
        ].filter(Boolean);
        return yearOverlayMonthHit({
          x,
          index,
          total: rows.length,
          top,
          bottom,
          month: monthLabel(row.snop_month),
          source: String(history.source || "").toUpperCase(),
          rows: tooltipRows,
        });
      })
      .join("");
    return `<svg class="chart postmortem-chart year-overlay-chart year-overlay-chart--long" viewBox="0 0 ${width} ${height}" role="img" aria-label="Actual demand and forward forecast across the continuous monthly horizon"><title>Actual demand and forward forecast across the continuous monthly horizon</title><g class="year-overlay-grid">${yearOverlayGrid(min, max, left, right, top, bottom)}</g><text class="year-overlay-axis-unit" x="${left}" y="16">KL</text>${fiscalSeparators}${yearOverlayPath(actual, x, y, "actual", actualColor)}${yearOverlayPath(forecast, x, y, "forecast", forecastColor)}${points}<g class="year-overlay-labels">${labels}</g>${cutoff}<g class="year-overlay-month-hits">${monthHits}</g></svg>`;
  }

  function productYearOverlayChart(history) {
    return yearOverlayMode === "long"
      ? productLongHorizonChart(history)
      : productFiscalYearOverlayChart(history);
  }

  function productRevisionOutcomeChart(postmortem) {
    const points = (postmortem?.revision_outcomes?.rows || []).filter((row) =>
      finite(row.error_improvement_kl),
    );
    if (!points.length) return emptyVisual("No complete Vintage A/B outcomes");
    const width = 520;
    const height = 148;
    const left = 25;
    const right = 505;
    const top = 14;
    const bottom = 105;
    const maxAbsolute = Math.max(
      ...points.map((point) => Math.abs(point.error_improvement_kl)),
      0.01,
    );
    const zeroY = (top + bottom) / 2;
    const x = (index) =>
      points.length === 1
        ? width / 2
        : left + (index / (points.length - 1)) * (right - left);
    const y = (value) =>
      zeroY - (value / maxAbsolute) * ((bottom - top) / 2 - 4);
    const line = points
      .map(
        (point, index) =>
          `${index ? "L" : "M"}${x(index).toFixed(1)} ${y(point.error_improvement_kl).toFixed(1)}`,
      )
      .join(" ");
    const dots = points
      .map((point, index) => {
        const outcome = point.revision_outcome || "neutral";
        const label = `${monthLabel(point.snop_month)}, revision ${signedKl(point.revision_kl)}, error improvement ${signedKl(point.error_improvement_kl)}, ${labelize(outcome)}`;
        return `<circle class="chart__point postmortem-revision-chart__point postmortem-revision-chart__point--${escapeHtml(outcome)}" cx="${x(index).toFixed(1)}" cy="${y(point.error_improvement_kl).toFixed(1)}" r="4" tabindex="0" role="img" aria-label="${escapeHtml(label)}"><title>${escapeHtml(label)}</title></circle>`;
      })
      .join("");
    const labels = points
      .map(
        (point, index) =>
          `<text x="${x(index)}" y="126">${escapeHtml(monthLabel(point.snop_month).split(" ")[0])}</text>`,
      )
      .join("");
    return `<div class="postmortem-revision-chart"><svg class="chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Monthly revision error improvement with zero baseline"><title>Monthly revision error improvement with zero baseline</title><line class="postmortem-revision-chart__zero" x1="${left}" y1="${zeroY}" x2="${right}" y2="${zeroY}"></line><path class="postmortem-revision-chart__line" d="${line}"></path>${dots}<g class="chart__labels">${labels}</g></svg><div class="postmortem-revision-chart__legend"><span><i class="scatter-key scatter-key--improved"></i>Improved</span><span><i class="scatter-key scatter-key--worsened"></i>Worsened</span><span><i class="scatter-key scatter-key--neutral"></i>Neutral</span><span>Error improvement · zero baseline · ${count(points.length)} months</span></div></div>`;
  }

  function productCommentary(postmortem) {
    const rows = postmortem?.commentary?.rows || [];
    const body = rows.length
      ? rows
          .map((row) => {
            const kind =
              row.severity === "positive"
                ? "good"
                : row.severity === "critical"
                  ? "bad"
                  : row.severity === "warning"
                    ? "warn"
                    : "neutral";
            const refs = (row.evidence_refs || []).join(" · ");
            return `<article class="postmortem-comment postmortem-comment--${kind}"><i class="postmortem-comment__lamp" aria-hidden="true"></i><div class="postmortem-comment__copy"><b>${escapeHtml(labelize(row.category))}</b><strong>${escapeHtml(row.headline)}</strong><p>${escapeHtml(row.body)}${refs ? `<br><span>Evidence: ${escapeHtml(refs)}</span>` : ""}</p></div><span class="postmortem-comment__confidence">${escapeHtml(row.confidence)} confidence</span></article>`;
          })
          .join("")
      : '<div class="empty-row">No material issue callouts for this selection.</div>';
    return `<header class="postmortem-commentary__head"><h3>Planner commentary</h3><p>Rules-based observations · evidence refs · no invented cause</p></header><div class="postmortem-commentary__body">${body}</div>`;
  }

  function productPeerBenchmark(postmortem) {
    const peers = postmortem?.peer_benchmarks?.rows || [];
    if (!peers.length) return emptyVisual("No eligible sibling cohort");
    const values = peers
      .flatMap((row) => [
        row.p25_accuracy_pct,
        row.median_accuracy_pct,
        row.p75_accuracy_pct,
        row.selected_accuracy_pct,
      ])
      .filter(finite);
    const lower = Math.min(...values, 0);
    const upper = Math.max(...values, 100);
    const position = (value) =>
      finite(value)
        ? Math.max(
            0,
            Math.min(100, ((value - lower) / Math.max(upper - lower, 1)) * 100),
          )
        : 0;
    return `<div class="postmortem-peer-list">${peers
      .map((row) => {
        const selected = position(row.selected_accuracy_pct);
        const p25 = position(row.p25_accuracy_pct);
        const p75 = position(row.p75_accuracy_pct);
        const median = position(row.median_accuracy_pct);
        return `<article class="postmortem-peer"><span><b>${escapeHtml(labelize(row.cohort_type))}</b><small>${escapeHtml(row.cohort_value)} · ${count(row.eligible_count)} eligible</small></span><div class="postmortem-peer__track" aria-label="Selected accuracy ${pct(row.selected_accuracy_pct)} versus ${labelize(row.cohort_type)} median ${pct(row.median_accuracy_pct)}"><i class="postmortem-peer__band" style="left:${p25}%;width:${Math.max(1, p75 - p25)}%"></i><i class="postmortem-peer__median" style="left:${median}%"></i><i class="postmortem-peer__selected" style="left:${selected}%"></i></div><strong>${pct(row.selected_accuracy_pct)}</strong><p class="postmortem-peer-note">Median ${pct(row.median_accuracy_pct)} · rank ${row.selected_rank || "—"}/${count(row.eligible_count)} · percentile ${pct(row.selected_percentile_pct)}</p></article>`;
      })
      .join(
        "",
      )}<p class="postmortem-peer-note">Accuracy scale ${number(lower, 0)}% to ${number(upper, 0)}% · same target month and active source.</p></div>`;
  }

  function renderProductPostmortem(detail) {
    const postmortem = detail.postmortem || {};
    const summary = postmortem.summary || {};
    const treatment = postmortem.treatment || {};
    const decisionKind =
      treatment.action === "hold" ? "severity--good" : "severity--warn";
    setHtml(
      document.querySelector("[data-postmortem-decision]"),
      `<div class="postmortem-decision__lead"><header><span class="severity ${decisionKind}">${escapeHtml(labelize(treatment.action || "Review"))}</span><h3>${escapeHtml(treatment.rationale || postmortem.status_message)}</h3></header><p>Evidence-bound recommendation for the forward baseline; business cause remains a review input.</p></div><div class="postmortem-decision__fact"><b>Proposed impact</b><strong>${finite(treatment.impact_kl) ? signedKl(treatment.impact_kl) : "No quantified change"}</strong><small>Directional adjustment, not an auto-write</small></div><div class="postmortem-decision__fact"><b>Confidence</b><strong>${escapeHtml(labelize(treatment.confidence))}</strong><small>Based on connected forecast evidence</small></div><div class="postmortem-decision__fact"><b>Review trigger</b><strong>${escapeHtml(treatment.review_trigger || "Next material update")}</strong><small>Planner retains final judgment</small></div>`,
    );
    const metrics = [
      [
        "Latest forecast",
        kl(summary.latest_forecast_kl),
        `As of ${dateLabel(summary.latest_calculation_month)}`,
      ],
      ["Actual", kl(summary.actual_kl), monthLabel(detail.target_month)],
      [
        "Forecast accuracy",
        pct(summary.forecast_accuracy_pct),
        "Latest forecast vs actual",
      ],
      ["Bias", signedKl(summary.bias_kl), pct(summary.bias_pct)],
      [
        "Absolute error",
        kl(summary.absolute_error_kl),
        "Magnitude of latest miss",
      ],
      [
        "Revision efficiency",
        pct(summary.revision_efficiency_pct),
        `${count(summary.material_revision_hits)} of ${count(summary.material_revisions)} material moves helped`,
      ],
    ];
    setHtml(
      document.querySelector("[data-postmortem-metrics]"),
      metrics
        .map(
          ([label, value, note]) =>
            `<article class="postmortem-metric"><b>${escapeHtml(label)}</b><strong>${escapeHtml(value)}</strong><small>${escapeHtml(note)}</small></article>`,
        )
        .join(""),
    );
    renderYearOverlay(detail);
    setHtml(
      document.querySelector("[data-postmortem-commentary]"),
      productCommentary(postmortem),
    );
    setHtml(
      document.querySelector("[data-postmortem-revision-chart]"),
      productRevisionOutcomeChart(postmortem),
    );
    document.querySelector("[data-postmortem-revision-summary]").textContent =
      `${signedKl(summary.first_to_latest_fva_kl)} FVA · ${pct(summary.material_hit_rate_pct)} hit rate`;
    setHtml(
      document.querySelector("[data-postmortem-peers]"),
      productPeerBenchmark(postmortem),
    );
    const peerCount = (postmortem.peer_benchmarks?.rows || []).reduce(
      (total, row) => Math.max(total, Number(row.eligible_count || 0)),
      0,
    );
    document.querySelector("[data-postmortem-peer-scope]").textContent =
      `${count(peerCount)} eligible siblings`;
    setHtml(
      document.querySelector("[data-postmortem-evidence]"),
      `<header class="postmortem-evidence__head"><h3>Selected-target evidence</h3><p>Facts to take into the forecast review</p></header><div class="postmortem-evidence__body"><div class="postmortem-evidence__row"><strong>Latest position</strong><span>${kl(summary.latest_forecast_kl)} forecast vs ${kl(summary.actual_kl)} actual</span><b>${signedKl(summary.bias_kl)}</b></div><div class="postmortem-evidence__row"><strong>Forecast value add</strong><span>Oldest-to-latest absolute-error change</span><b>${signedKl(summary.first_to_latest_fva_kl)}</b></div><div class="postmortem-evidence__row"><strong>Revision discipline</strong><span>${count(summary.material_revisions)} material moves · ${count(summary.material_revision_hits)} helped</span><b>${pct(summary.material_hit_rate_pct)}</b></div><div class="postmortem-evidence__row"><strong>Data scope</strong><span>${escapeHtml(postmortem.source?.toUpperCase())} · class ${escapeHtml(postmortem.sku_class)} · ${count(summary.vintage_count)} vintages</span><b>${escapeHtml(labelize(postmortem.status))}</b></div></div>`,
    );
    setHtml(
      document.querySelector("[data-postmortem-treatment]"),
      `<header class="postmortem-treatment__head"><h3>Forward forecast treatment</h3><p>Decision contract for planner, business and forecasting teams</p></header><div class="postmortem-treatment__item"><b>Action</b><strong>${escapeHtml(labelize(treatment.action))}</strong><small>Controlled recommendation</small></div><div class="postmortem-treatment__item"><b>Adjustment</b><strong>${finite(treatment.impact_kl) ? signedKl(treatment.impact_kl) : "Hold pending evidence"}</strong><small>Against current baseline</small></div><div class="postmortem-treatment__item"><b>Rationale</b><strong title="${escapeHtml(treatment.rationale)}">${escapeHtml(treatment.rationale)}</strong><small>Forecast evidence only</small></div><div class="postmortem-treatment__item"><b>Review contract</b><strong title="${escapeHtml(treatment.review_trigger)}">${escapeHtml(treatment.review_trigger)}</strong><small>Reassess, do not autopilot</small></div>`,
    );
  }

  function renderProduct(detail) {
    const productControl = document.querySelector(
      '[data-product-control="parent"]',
    );
    const monthControl = document.querySelector(
      '[data-product-control="month"]',
    );
    const postmortemTargets = [
      "[data-postmortem-decision]",
      "[data-postmortem-metrics]",
      "[data-postmortem-performance-chart]",
      "[data-year-overlay-legend]",
      "[data-postmortem-commentary]",
      "[data-postmortem-revision-chart]",
      "[data-postmortem-peers]",
      "[data-postmortem-evidence]",
      "[data-postmortem-treatment]",
      "[data-product-revisions]",
    ];
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
      postmortemTargets.forEach((selector) =>
        setHtml(document.querySelector(selector), ""),
      );
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
    setHtml(
      document.querySelector("[data-product-summary]"),
      [
        populationItem("Brand", detail.brand || "Unmapped"),
        populationItem("SKU class", detail.sku_class || "Unclassified"),
      ].join(""),
    );
    renderProductPostmortem(detail);
    setHtml(
      document.querySelector("[data-history-chart]"),
      historyChart(detail),
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
        const points = sourceRows.map((row) => ({
          x: x(row.calculation_month),
          y: y(row.forecast_kl),
        }));
        return `<path data-interpolation="smooth" d="${smoothLinePath(points)}" fill="none" stroke="${colors[source]}" stroke-width="3"/>${sourceRows.map((row) => `<circle cx="${x(row.calculation_month)}" cy="${y(row.forecast_kl)}" r="4" fill="white" stroke="${colors[source]}" stroke-width="3"><title>${source.toUpperCase()} · ${dateLabel(row.calculation_month)} · M−${row.forecast_horizon_months} · ${kl(row.forecast_kl)} · error ${signedKl(row.error_kl)} · bias ${pct(row.bias_pct)}</title></circle>`).join("")}`;
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

  function productRevisionTable(rows) {
    const header =
      '<div role="row"><b role="columnheader">Source</b><strong role="columnheader">From → to</strong><em role="columnheader">Horizon</em><i role="columnheader">Revision</i><span role="columnheader">Direction</span><small role="columnheader">Error after</small><small role="columnheader">Outcome</small></div>';
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
            `<div role="row"><b role="cell">${sourceBadge(row.source)}</b><strong role="cell">${dateLabel(row.previous_calculation_month)} → ${dateLabel(row.calculation_month)}</strong><em role="cell">M−${row.previous_horizon_months} → M−${row.forecast_horizon_months}</em><i role="cell">${signedKl(row.revision_kl)}</i><span role="cell">${labelize(row.revision_direction)}</span><small role="cell" class="${row.error_improvement_kl > 0 ? "good" : row.error_improvement_kl < 0 ? "bad" : ""}">${signedKl(row.error_kl)}</small><small role="cell" class="${row.error_improvement_kl > 0 ? "good" : row.error_improvement_kl < 0 ? "bad" : ""}">${labelize(row.revision_outcome)} · ${signedKl(row.error_improvement_kl)}</small></div>`,
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
    revisionScatterMode = "error";
    revisionScatterDensity = true;
    revisionScatterFocus = "all";
    revisionScatterSkuClass = "all";
    revisionScatterZoom = 1;
    revisionScatterSelection = new Set();
    revisionScatterPan = { x: 0, y: 0 };
    yearOverlayVisible = new Set();
    yearOverlayKey = "";
    yearOverlayMode = "fy";
    closeVintageSelector();
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
    setProductFilterValue("brands", request.brands || []);
    setProductFilterValue("sku_classes", request.sku_classes || []);
    setProductFilterValue("parent_codes", request.parent_codes || []);
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
  scopeButtons.forEach((button) => {
    button.addEventListener("click", () => {
      setScopeDrawerOpen(scopeDrawer.hidden, button);
    });
  });
  chartDialogClose.addEventListener("click", closeChartDialog);
  fullscreenFilters.addEventListener("click", () => {
    setScopeDrawerOpen(scopeDrawer.hidden, fullscreenFilters);
  });
  document.querySelectorAll('[data-action="reset"]').forEach((button) => {
    button.addEventListener("click", resetDashboard);
  });
  timelines.forEach((timelineView) => {
    timelineView.root
      .querySelectorAll("[data-timeline-grain]")
      .forEach((button) => {
        button.addEventListener("click", () => {
          timelineState.grain = button.dataset.timelineGrain;
          updateTimelineUi(
            currentPayload?.options.target_months || [],
            controls.get("target_start").value,
            controls.get("target_end").value,
          );
        });
      });
    timelineView.root
      .querySelectorAll("[data-timeline-months]")
      .forEach((button) => {
        button.addEventListener("click", () => {
          applyTimelinePreset(
            currentPayload?.options.target_months || [],
            button.dataset.timelineMonths,
          );
          scheduleRefresh({ immediate: true });
        });
      });
    const applyTimelineHandle = (kind) => {
      const months = currentPayload?.options.target_months || [];
      let startIndex = Number(timelineView.startSlider.value);
      let endIndex = Number(timelineView.endSlider.value);
      if (kind === "start" && startIndex > endIndex) endIndex = startIndex;
      if (kind === "end" && endIndex < startIndex) startIndex = endIndex;
      const range = ForecastTimeline.rangeFromIndices(
        months,
        startIndex,
        endIndex,
      );
      setTimelineRange(months, range.start, range.end);
    };
    timelineView.startSlider?.addEventListener("input", () =>
      applyTimelineHandle("start"),
    );
    timelineView.endSlider?.addEventListener("input", () =>
      applyTimelineHandle("end"),
    );
    timelineView.startSlider?.addEventListener("change", () =>
      scheduleRefresh({ immediate: true }),
    );
    timelineView.endSlider?.addEventListener("change", () =>
      scheduleRefresh({ immediate: true }),
    );
    timelineView.startSelect?.addEventListener("change", () => {
      setTimelineRange(
        currentPayload?.options.target_months || [],
        timelineView.startSelect.value,
        timelineView.endSelect.value,
      );
      scheduleRefresh({ immediate: true });
    });
    timelineView.endSelect?.addEventListener("change", () => {
      setTimelineRange(
        currentPayload?.options.target_months || [],
        timelineView.startSelect.value,
        timelineView.endSelect.value,
      );
      scheduleRefresh({ immediate: true });
    });
    timelineView.selection?.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
      event.preventDefault();
      const months = currentPayload?.options.target_months || [];
      const moved = ForecastTimeline.moveWindow(
        months,
        Number(timelineView.startSlider.value),
        Number(timelineView.endSlider.value),
        event.key === "ArrowLeft" ? -1 : 1,
      );
      const range = ForecastTimeline.rangeFromIndices(
        months,
        moved.start,
        moved.end,
      );
      setTimelineRange(months, range.start, range.end);
      scheduleRefresh({ immediate: true });
    });
    timelineView.selection?.addEventListener("pointerdown", (event) => {
      timelineWindowDrag = {
        pointerId: event.pointerId,
        originX: event.clientX,
        start: Number(timelineView.startSlider.value),
        end: Number(timelineView.endSlider.value),
        view: timelineView,
      };
      timelineView.selection.setPointerCapture(event.pointerId);
    });
    timelineView.selection?.addEventListener("pointermove", (event) => {
      if (
        !timelineWindowDrag ||
        event.pointerId !== timelineWindowDrag.pointerId
      )
        return;
      const width = timelineView.rail.getBoundingClientRect().width;
      const steps = Number(timelineView.endSlider.max) || 1;
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
  });
  const endTimelineWindowDrag = (event) => {
    if (!timelineWindowDrag || event.pointerId !== timelineWindowDrag.pointerId)
      return;
    timelineWindowDrag = null;
    scheduleRefresh({ immediate: true });
  };
  document.addEventListener("pointerup", endTimelineWindowDrag);
  document.addEventListener("pointercancel", endTimelineWindowDrag);

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
  document.addEventListener("input", (event) => {
    const brandSearch = event.target.closest?.(
      "[data-vintage-gap-brand-search]",
    );
    const parentSearch = event.target.closest?.(
      "[data-vintage-gap-parent-search]",
    );
    if (!brandSearch && !parentSearch) return;
    const selector = brandSearch
      ? "[data-vintage-gap-brand-search]"
      : "[data-vintage-gap-parent-search]";
    const value = event.target.value;
    const selectionStart = event.target.selectionStart;
    if (brandSearch) vintageGapBrandSearch = value;
    else vintageGapParentSearch = value;
    renderVintageGapDrilldown();
    const replacement = vintageGapDialog.querySelector(selector);
    replacement?.focus();
    replacement?.setSelectionRange(selectionStart, selectionStart);
  });
  document.addEventListener("change", (event) => {
    if (event.target.matches?.("[data-vintage-option]")) {
      scheduleRefresh({ immediate: true, closeSelector: false });
      return;
    }
    if (event.target.matches?.("[data-chart-fullscreen-menu]")) {
      const mode = event.target.value;
      if (!mode) return;
      openChartDialog(
        event.target.dataset.chartFullscreenKind,
        event.target,
        mode,
      );
      event.target.value = "";
      return;
    }
    if (event.target.matches?.("[data-scatter-zoom]")) {
      revisionScatterZoom = Number(event.target.value) / 100;
      refreshScatterCharts();
      return;
    }
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
    const yearOverlayReset = event.target.closest?.(
      "[data-year-overlay-reset]",
    );
    if (yearOverlayReset) {
      if (yearOverlayClickTimer) window.clearTimeout(yearOverlayClickTimer);
      yearOverlayClickTimer = null;
      resetYearOverlay();
      return;
    }
    const yearOverlayModeButton = event.target.closest?.(
      "[data-year-overlay-mode]",
    );
    if (yearOverlayModeButton) {
      yearOverlayMode = yearOverlayModeButton.dataset.yearOverlayMode || "fy";
      renderYearOverlay();
      return;
    }
    const yearOverlayButton = event.target.closest?.(
      "[data-year-overlay-year]",
    );
    if (yearOverlayButton) {
      const year = Number(yearOverlayButton.dataset.yearOverlayYear);
      if (!Number.isFinite(year)) return;
      if (yearOverlayClickTimer) window.clearTimeout(yearOverlayClickTimer);
      yearOverlayClickTimer = window.setTimeout(() => {
        yearOverlayClickTimer = null;
        toggleYearOverlay(year);
      }, 220);
      return;
    }
    const vintageTrigger = event.target.closest?.(
      "[data-vintage-selector-trigger]",
    );
    if (vintageTrigger) {
      const open =
        vintageSelectorPopover.hidden ||
        vintageSelectorTrigger !== vintageTrigger;
      if (open) {
        closeScopeDrawer();
        setVintageSelectorOpen(true, vintageTrigger);
      } else {
        closeVintageSelector({ restoreFocus: true });
      }
      return;
    }
    if (
      !vintageSelectorPopover.hidden &&
      !event.target.closest?.(".vintage-selector")
    ) {
      closeVintageSelector();
    }
    if (event.target.closest?.('[data-action="vintage-gap-close"]')) {
      closeVintageGapDrilldown({ restoreFocus: true });
      return;
    }
    const vintageGapBackdrop = event.target.closest?.("#vintage-gap-dialog");
    if (vintageGapBackdrop && event.target === vintageGapBackdrop) {
      closeVintageGapDrilldown();
      return;
    }
    const vintageGapModeButton = event.target.closest?.(
      "[data-vintage-gap-mode]",
    );
    if (vintageGapModeButton) {
      vintageGapMode = vintageGapModeButton.dataset.vintageGapMode;
      vintageGapSelectedBrand = null;
      vintageGapSelectedParent = null;
      vintageGapBrandSearch = "";
      vintageGapParentSearch = "";
      renderVintageGapDrilldown();
      vintageGapDialog
        .querySelector(
          `[data-vintage-gap-mode="${vintageGapModeButton.dataset.vintageGapMode}"]`,
        )
        ?.focus();
      return;
    }
    const vintageGapBrandButton = event.target.closest?.(
      "[data-vintage-gap-brand]",
    );
    if (vintageGapBrandButton) {
      vintageGapSelectedBrand = vintageGapBrandButton.dataset.vintageGapBrand;
      vintageGapSelectedParent = null;
      vintageGapParentSearch = "";
      renderVintageGapDrilldown();
      vintageGapDialog
        .querySelector(
          `[data-vintage-gap-brand="${CSS.escape(vintageGapSelectedBrand)}"]`,
        )
        ?.focus();
      return;
    }
    const vintageGapParentButton = event.target.closest?.(
      "[data-vintage-gap-parent]",
    );
    if (vintageGapParentButton) {
      vintageGapSelectedParent = Number(
        vintageGapParentButton.dataset.vintageGapParent,
      );
      renderVintageGapDrilldown();
      vintageGapDialog
        .querySelector(
          `[data-vintage-gap-parent="${vintageGapSelectedParent}"]`,
        )
        ?.focus();
      return;
    }
    if (event.target.closest?.("[data-vintage-gap-show-all]")) {
      vintageGapShowAll = !vintageGapShowAll;
      if (!vintageGapShowAll) {
        vintageGapBrandSearch = "";
        vintageGapParentSearch = "";
      }
      renderVintageGapDrilldown();
      vintageGapDialog.querySelector("[data-vintage-gap-show-all]")?.focus();
      return;
    }
    const vintageGapProductButton = event.target.closest?.(
      "[data-vintage-gap-open-product]",
    );
    if (vintageGapProductButton) {
      void openVintageGapProduct(
        vintageGapProductButton.dataset.vintageGapOpenProduct,
      );
      return;
    }
    const vintageGapMonth = event.target.closest?.(
      ".chart--overview .chart__month-hit:not(.chart__volume-hit)",
    );
    if (vintageGapMonth) {
      hideChartTooltip(vintageGapMonth);
      void openVintageGapDrilldown(vintageGapMonth);
      return;
    }
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
    const comparisonKpiGuideOpen = event.target.closest?.(
      '[data-action="comparison-kpi-guide-open"]',
    );
    if (comparisonKpiGuideOpen) {
      openComparisonKpiGuide(
        comparisonKpiGuideOpen.dataset.kpiGuide,
        comparisonKpiGuideOpen,
      );
      return;
    }
    if (event.target.closest?.('[data-action="comparison-kpi-guide-close"]')) {
      closeComparisonKpiGuide({ restoreFocus: true });
      return;
    }
    const comparisonKpiGuideDialog = event.target.closest?.(
      "#comparison-kpi-guide-dialog",
    );
    if (comparisonKpiGuideDialog && event.target === comparisonKpiGuideDialog) {
      closeComparisonKpiGuide();
      return;
    }
    const overviewGuideTrigger = event.target.closest?.(
      '[data-action="overview-guide-open"]',
    );
    if (overviewGuideTrigger) {
      openOverviewGuide(
        overviewGuideTrigger.dataset.overviewGuide,
        overviewGuideTrigger,
      );
      return;
    }
    if (event.target.closest?.('[data-action="overview-guide-close"]')) {
      closeOverviewGuide({ restoreFocus: true });
      return;
    }
    const overviewGuideDialog = event.target.closest?.(
      "#overview-guide-dialog",
    );
    if (overviewGuideDialog && event.target === overviewGuideDialog) {
      closeOverviewGuide();
      return;
    }
    const scatterGuideTrigger = event.target.closest?.(
      '[data-action="revision-scatter-guide-open"]',
    );
    if (scatterGuideTrigger) {
      openRevisionScatterGuide(scatterGuideTrigger);
      return;
    }
    if (
      event.target.closest?.('[data-action="revision-scatter-guide-close"]')
    ) {
      closeRevisionScatterGuide({ restoreFocus: true });
      return;
    }
    const scatterGuideDialog = event.target.closest?.(
      "#revision-scatter-guide-dialog",
    );
    if (scatterGuideDialog && event.target === scatterGuideDialog) {
      closeRevisionScatterGuide();
      return;
    }
    const effectivenessGuideTrigger = event.target.closest?.(
      '[data-action="revision-effectiveness-guide-open"]',
    );
    if (effectivenessGuideTrigger) {
      openRevisionEffectivenessGuide(effectivenessGuideTrigger);
      return;
    }
    if (
      event.target.closest?.(
        '[data-action="revision-effectiveness-guide-close"]',
      )
    ) {
      closeRevisionEffectivenessGuide({ restoreFocus: true });
      return;
    }
    const effectivenessGuideDialog = event.target.closest?.(
      "#revision-effectiveness-guide-dialog",
    );
    if (effectivenessGuideDialog && event.target === effectivenessGuideDialog) {
      closeRevisionEffectivenessGuide();
      return;
    }
    if (
      event.target.closest?.('[data-action="revision-effectiveness-close"]')
    ) {
      closeRevisionEffectiveness({ restoreFocus: true });
      return;
    }
    const effectivenessDialog = event.target.closest?.(
      "#revision-effectiveness-dialog",
    );
    if (effectivenessDialog && event.target === effectivenessDialog) {
      closeRevisionEffectiveness();
      return;
    }
    const effectivenessPoint = event.target.closest?.(
      ".revision-history__point",
    );
    if (effectivenessPoint) {
      openRevisionEffectivenessPoint(effectivenessPoint);
      return;
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
      if (action === "mode-error") revisionScatterMode = "error";
      else if (action === "mode-volume") revisionScatterMode = "volume";
      else if (action === "mode-uniform") revisionScatterMode = "uniform";
      else if (action === "density")
        revisionScatterDensity = !revisionScatterDensity;
      else if (action === "focus-top")
        revisionScatterFocus =
          revisionScatterFocus === "top-volume" ? "all" : "top-volume";
      else if (action === "focus-outliers")
        revisionScatterFocus =
          revisionScatterFocus === "outliers" ? "all" : "outliers";
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
      scheduleRefresh({ immediate: true });
    } else if (modeButton?.dataset.modeAction === "single") {
      controls.get("comparison_mode").value = "false";
      scheduleRefresh({ immediate: true });
    } else if (modeButton?.dataset.modeAction === "filters") {
      setScopeDrawerOpen(true, scopeButton);
    }
  });
  document.addEventListener("dblclick", (event) => {
    const yearOverlayButton = event.target.closest?.(
      "[data-year-overlay-year]",
    );
    if (!yearOverlayButton) return;
    if (yearOverlayClickTimer) window.clearTimeout(yearOverlayClickTimer);
    yearOverlayClickTimer = null;
    const year = Number(yearOverlayButton.dataset.yearOverlayYear);
    if (Number.isFinite(year)) toggleYearOverlay(year, true);
  });
  document.addEventListener("keydown", (event) => {
    const vintageGapMonth = event.target.closest?.(
      ".chart--overview .chart__month-hit:not(.chart__volume-hit)",
    );
    if (vintageGapMonth && (event.key === "Enter" || event.key === " ")) {
      event.preventDefault();
      hideChartTooltip(vintageGapMonth);
      void openVintageGapDrilldown(vintageGapMonth);
      return;
    }
    const effectivenessPoint = event.target.closest?.(
      ".revision-history__point",
    );
    if (effectivenessPoint && (event.key === "Enter" || event.key === " ")) {
      event.preventDefault();
      openRevisionEffectivenessPoint(effectivenessPoint);
      return;
    }
    if (event.key !== "Escape") return;
    if (!vintageGapDialog.hidden) {
      closeVintageGapDrilldown({ restoreFocus: true });
      return;
    }
    const comparisonKpiGuideDialog = document.querySelector(
      "#comparison-kpi-guide-dialog",
    );
    if (!comparisonKpiGuideDialog.hidden) {
      closeComparisonKpiGuide({ restoreFocus: true });
      return;
    }
    const overviewGuideDialog = document.querySelector(
      "#overview-guide-dialog",
    );
    if (!overviewGuideDialog.hidden) {
      closeOverviewGuide({ restoreFocus: true });
      return;
    }
    const scatterGuideDialog = document.querySelector(
      "#revision-scatter-guide-dialog",
    );
    if (!scatterGuideDialog.hidden) {
      closeRevisionScatterGuide({ restoreFocus: true });
      return;
    }
    const effectivenessGuideDialog = document.querySelector(
      "#revision-effectiveness-guide-dialog",
    );
    if (!effectivenessGuideDialog.hidden) {
      closeRevisionEffectivenessGuide({ restoreFocus: true });
      return;
    }
    const effectivenessDialog = document.querySelector(
      "#revision-effectiveness-dialog",
    );
    if (!effectivenessDialog.hidden) {
      closeRevisionEffectiveness({ restoreFocus: true });
      return;
    }
    if (!chartTooltip.hidden) hideChartTooltip(document.activeElement);
    if (!vintageSelectorPopover.hidden) {
      closeVintageSelector({ restoreFocus: true });
      return;
    }
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
    if (!vintageSelectorPopover.hidden && vintageSelectorTrigger)
      positionVintageSelector(vintageSelectorTrigger);
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
