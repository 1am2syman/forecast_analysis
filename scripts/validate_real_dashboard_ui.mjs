#!/usr/bin/env node

/** Browser validation for the canonical real-data static forecast dashboard. */

import { spawn, spawnSync } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import {
  mkdirSync,
  readFileSync,
  readdirSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { get as httpGet } from "node:http";
import { createServer } from "node:net";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { setTimeout as sleep } from "node:timers/promises";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const DEFAULT_OUTPUT = join(
  ROOT,
  "validation-artifacts/static-dashboard-real-data",
);
const TABS = ["overview", "trends", "comparison", "history", "quality"];
const VIEWPORTS = [
  { name: "desktop", width: 1440, height: 900 },
  { name: "short", width: 1440, height: 720 },
  { name: "narrow", width: 800, height: 700 },
];
const FOCUSED_VIEWPORTS = [
  { name: "desktop-focus", width: 1440, height: 900, collapseRail: false },
  { name: "short-focus", width: 1440, height: 720, collapseRail: false },
  {
    name: "supplied-width-focus",
    width: 1018,
    height: 700,
    collapseRail: true,
  },
  { name: "narrow-focus", width: 800, height: 700, collapseRail: false },
];

function parseArgs(argv) {
  const args = { output: DEFAULT_OUTPUT };
  for (let index = 0; index < argv.length; index += 1) {
    if (argv[index] === "--output") {
      args.output = resolve(ROOT, argv[index + 1]);
      index += 1;
    } else if (argv[index] === "--help") {
      process.stdout.write(
        "Usage: node scripts/validate_real_dashboard_ui.mjs [--output DIR]\n",
      );
      process.exit(0);
    } else {
      throw new Error(`Unknown argument: ${argv[index]}`);
    }
  }
  return args;
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function commandExists(command) {
  return (
    spawnSync("sh", ["-c", `command -v ${command}`], {
      encoding: "utf8",
    }).status === 0
  );
}

async function freePort() {
  return new Promise((resolvePort, reject) => {
    const server = createServer();
    server.unref();
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      assert(typeof address === "object" && address, "Could not allocate port");
      server.close(() => resolvePort(address.port));
    });
  });
}

function status(url) {
  return new Promise((resolveStatus, reject) => {
    const request = httpGet(
      url,
      { headers: { connection: "close" } },
      (response) => {
        response.resume();
        response.once("end", () => resolveStatus(response.statusCode ?? 0));
      },
    );
    request.once("error", reject);
    request.setTimeout(3_000, () =>
      request.destroy(new Error("request timed out")),
    );
  });
}

async function waitForUrl(url, timeoutMs = 75_000) {
  const deadline = Date.now() + timeoutMs;
  let lastError;
  while (Date.now() < deadline) {
    try {
      const responseStatus = await status(url);
      if (responseStatus >= 200 && responseStatus < 300) return;
      lastError = new Error(`${url} returned ${responseStatus}`);
    } catch (error) {
      lastError = error;
    }
    await sleep(250);
  }
  throw new Error(`Timed out waiting for ${url}: ${lastError}`);
}

function terminate(process) {
  if (!process || process.exitCode !== null) return;
  process.kill("SIGTERM");
  setTimeout(() => {
    if (process.exitCode === null) process.kill("SIGKILL");
  }, 1_000).unref();
}

class CdpPage {
  constructor(webSocketUrl) {
    this.socket = new WebSocket(webSocketUrl);
    this.nextId = 0;
    this.pending = new Map();
    this.consoleErrors = [];
    this.pageErrors = [];
    this.networkFailures = [];
    this.httpErrors = [];
  }

  async connect() {
    await new Promise((resolveConnect, reject) => {
      this.socket.onopen = resolveConnect;
      this.socket.onerror = reject;
    });
    this.socket.onmessage = (event) => {
      let message;
      try {
        message = JSON.parse(String(event.data));
      } catch (error) {
        this.pageErrors.push(`Invalid CDP message: ${error.message}`);
        return;
      }
      if (message.id && this.pending.has(message.id)) {
        const pending = this.pending.get(message.id);
        this.pending.delete(message.id);
        if (message.error) pending.reject(new Error(message.error.message));
        else pending.resolve(message.result);
        return;
      }
      if (message.method === "Runtime.consoleAPICalled") {
        if (["error", "warning"].includes(message.params.type)) {
          this.consoleErrors.push(
            message.params.args
              .map((arg) => arg.value ?? arg.description ?? "")
              .join(" "),
          );
        }
      } else if (message.method === "Runtime.exceptionThrown") {
        this.pageErrors.push(message.params.exceptionDetails.text);
      } else if (
        message.method === "Network.loadingFailed" &&
        !message.params.canceled
      ) {
        this.networkFailures.push(message.params.errorText);
      } else if (message.method === "Network.responseReceived") {
        const response = message.params.response;
        if (response.status >= 400)
          this.httpErrors.push(`${response.status} ${response.url}`);
      }
    };
  }

  send(method, params = {}) {
    return new Promise((resolveCommand, rejectCommand) => {
      const id = ++this.nextId;
      this.pending.set(id, { resolve: resolveCommand, reject: rejectCommand });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }

  async evaluate(expression, awaitPromise = false) {
    const result = await this.send("Runtime.evaluate", {
      expression,
      returnByValue: true,
      awaitPromise,
    });
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.text);
    return result.result?.value;
  }

  async viewport(width, height) {
    await this.send("Emulation.setDeviceMetricsOverride", {
      width,
      height,
      deviceScaleFactor: 1,
      mobile: false,
    });
  }

  async screenshot(path, clip = null) {
    const result = await this.send("Page.captureScreenshot", {
      format: "png",
      ...(clip
        ? {
            clip: { ...clip, scale: 1 },
            captureBeyondViewport: false,
          }
        : {}),
    });
    writeFileSync(path, Buffer.from(result.data, "base64"));
  }

  close() {
    this.socket.close();
  }
}

async function browserPage(debugPort) {
  const response = await fetch(
    `http://127.0.0.1:${debugPort}/json/new?about:blank`,
    {
      method: "PUT",
    },
  );
  const target = await response.json();
  const page = new CdpPage(target.webSocketDebuggerUrl);
  await page.connect();
  await page.send("Page.enable");
  await page.send("Runtime.enable");
  await page.send("Network.enable");
  return page;
}

async function waitFor(page, expression, message, timeoutMs = 60_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await page.evaluate(expression)) return;
    await sleep(200);
  }
  throw new Error(`Timed out: ${message}`);
}

function sha256(path) {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

async function checkLazyEndpointCoverage(page) {
  const urls = await page.evaluate(
    "window.__dashboardFetches.map((record) => record.url)",
  );
  for (const moduleName of [
    "trends",
    "heatmap",
    "exceptions",
    "product",
    "quality",
  ]) {
    assert(
      urls.some((url) => url.includes(`/api/module/${moduleName}`)),
      `Lazy ${moduleName} module was not requested`,
    );
  }
  assert(
    !urls.some((url) => /\/api\/view(?:$|\?)/.test(url)),
    "Legacy /api/view was used by normal browser flow",
  );
}

async function overviewAudit(page, viewport) {
  const audit = await page.evaluate(`(() => {
      const rect = (node) => {
        const bounds = node.getBoundingClientRect();
        return {top: bounds.top, left: bounds.left, right: bounds.right, bottom: bounds.bottom, width: bounds.width, height: bounds.height};
      };
      const charts = [...document.querySelectorAll('.overview-charts .frame__body')].map((body) => {
        const svg = body.querySelector('svg.chart');
        const bodyRect = rect(body);
        const svgRect = rect(svg);
        const viewBox = svg.viewBox.baseVal;
        const renderedAspect = svgRect.width / svgRect.height;
        const viewBoxAspect = viewBox.width / viewBox.height;
        return {
          body: bodyRect,
          svg: svgRect,
          viewBox: {width: viewBox.width, height: viewBox.height},
          aspectError: Math.abs(renderedAspect - viewBoxAspect) / viewBoxAspect,
          contained: svgRect.left >= bodyRect.left - 1 && svgRect.top >= bodyRect.top - 1 && svgRect.right <= bodyRect.right + 1 && svgRect.bottom <= bodyRect.bottom + 1,
        };
      });
      const volume = document.querySelector('.chart--overview-volume');
      return {
        viewport: {width: innerWidth, height: innerHeight},
        scopeTitle: getComputedStyle(document.querySelector('.scopebar__overview-title')).display,
        paneHeads: document.querySelectorAll('#pane-overview > .pane__head').length,
        health: rect(document.querySelector('.overview-health')),
        chartTop: Math.min(...[...document.querySelectorAll('.overview-charts > .frame')].map((node) => node.getBoundingClientRect().top)),
        detailsOpen: document.querySelector('.overview-details').open,
        kpiLabels: [...document.querySelectorAll('[data-kpis] .kpi__label')].map((node) => node.textContent.trim()),
        kpiVisible: [...document.querySelectorAll('[data-kpis] .kpi')].every((node) => { const bounds = node.getBoundingClientRect(); return getComputedStyle(node).display !== 'none' && bounds.width > 0 && bounds.height > 0; }),
        charts,
        volumeDomain: {
          domainMin: Number(volume.dataset.domainMin),
          domainMax: Number(volume.dataset.domainMax),
          dataMin: Number(volume.dataset.dataMin),
          dataMax: Number(volume.dataset.dataMax),
        },
      };
    })()`);
  assert(
    audit.scopeTitle !== "none",
    `${viewport.name}: merged overview title is hidden`,
  );
  assert(
    audit.paneHeads === 0,
    `${viewport.name}: duplicate overview heading row remains`,
  );
  assert(
    audit.health.height <= 36,
    `${viewport.name}: compact population row is too tall (${audit.health.height}px)`,
  );
  assert(
    audit.chartTop <= 275,
    `${viewport.name}: charts begin too late (${audit.chartTop}px)`,
  );
  assert(
    !audit.detailsOpen,
    `${viewport.name}: data details should default closed`,
  );
  assert(
    audit.kpiLabels.length === 6 && audit.kpiVisible,
    `${viewport.name}: all six KPI cards must remain visible`,
  );
  assert(
    audit.kpiLabels.includes("WAPE"),
    `${viewport.name}: WAPE KPI is missing`,
  );
  assert(
    audit.kpiLabels.includes("Revision effectiveness"),
    `${viewport.name}: revision effectiveness KPI is missing`,
  );
  assert(
    audit.charts.length === 2,
    `${viewport.name}: expected two overview charts`,
  );
  assert(
    audit.charts.every((chart) => chart.aspectError <= 0.012),
    `${viewport.name}: chart viewBox does not match rendered aspect`,
  );
  assert(
    audit.charts.every((chart) => chart.contained),
    `${viewport.name}: chart SVG exceeds its visual frame`,
  );
  const domain = audit.volumeDomain;
  assert(
    domain.domainMin >= 0,
    `${viewport.name}: volume scale extends below zero`,
  );
  assert(
    domain.domainMin <= domain.dataMin && domain.domainMax >= domain.dataMax,
    `${viewport.name}: volume domain does not bound all data`,
  );
  if (domain.dataMin > 0)
    assert(
      domain.domainMin > 0,
      `${viewport.name}: positive volume data was unnecessarily forced to zero`,
    );
  assert(
    domain.domainMax - domain.domainMin <=
      (domain.dataMax - domain.dataMin) * 1.6,
    `${viewport.name}: volume domain wastes excessive vertical range`,
  );
  return audit;
}

function gallery(report) {
  const cards = [...report.focusedScreenshots, ...report.screenshots]
    .map(
      (shot) =>
        `<figure><img src="${shot.name}" alt="${shot.tab} at ${shot.viewport}"/><figcaption>${shot.viewport} · ${shot.tab}</figcaption></figure>`,
    )
    .join("");
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Real dashboard validation</title><style>body{margin:0;padding:28px;background:#edf3f1;color:#172421;font:14px system-ui}h1{margin-top:0}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:18px}figure{margin:0;padding:10px;background:white;border:1px solid #c8d5d1;border-radius:8px}img{display:block;width:100%;height:auto;border:1px solid #dbe4e1}figcaption{padding-top:8px;font-family:monospace}</style></head><body><h1>Canonical real-data dashboard validation</h1><p>${report.screenshots.length} matrix states + ${report.focusedScreenshots.length} focused overview captures · ${report.generatedAt}</p><main>${cards}</main></body></html>`;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  for (const command of ["uv", "chromium"]) {
    assert(commandExists(command), `Required command is missing: ${command}`);
  }
  rmSync(args.output, { recursive: true, force: true });
  mkdirSync(args.output, { recursive: true });

  const serverPort = await freePort();
  const debugPort = await freePort();
  const profileDir = join("/tmp", `real-dashboard-chrome-${randomUUID()}`);
  const downloadDir = join(args.output, "downloads");
  mkdirSync(downloadDir, { recursive: true });
  const server = spawn(
    "uv",
    [
      "run",
      "python",
      "-m",
      "dashboard.server",
      "--host",
      "127.0.0.1",
      "--port",
      String(serverPort),
    ],
    { cwd: ROOT, stdio: ["ignore", "ignore", "pipe"] },
  );
  const chrome = spawn(
    "chromium",
    [
      "--headless=new",
      "--no-sandbox",
      "--disable-gpu",
      `--remote-debugging-port=${debugPort}`,
      `--user-data-dir=${profileDir}`,
      "about:blank",
    ],
    { stdio: ["ignore", "ignore", "pipe"] },
  );

  let page;
  try {
    const baseUrl = `http://127.0.0.1:${serverPort}/`;
    await waitForUrl(`${baseUrl}api/health`);
    await waitForUrl(`http://127.0.0.1:${debugPort}/json/version`, 20_000);
    page = await browserPage(debugPort);
    await page.viewport(1440, 900);
    await page.send("Emulation.setEmulatedMedia", {
      features: [{ name: "prefers-reduced-motion", value: "reduce" }],
    });
    await page.send("Page.navigate", { url: `${baseUrl}#overview` });
    await waitFor(
      page,
      `document.querySelector('[data-status]')?.textContent.includes('canonical dataset ready') && document.querySelectorAll('[data-kpis] .kpi').length === 6 && !document.querySelector('.loading')?.classList.contains('is-visible')`,
      "canonical dashboard bootstrap",
      75_000,
    );
    await page.evaluate("document.fonts.ready", true);
    await page.evaluate(`(() => {
      window.__dashboardFetches = [];
      const originalFetch = window.fetch.bind(window);
      window.fetch = async (...args) => {
        const options = args[1] || {};
        const record = {url: String(args[0]), method: options.method || 'GET', body: options.body || null, done: false, status: null};
        window.__dashboardFetches.push(record);
        try { const response = await originalFetch(...args); record.status = response.status; record.done = true; return response; }
        catch (error) { record.error = String(error); record.done = true; throw error; }
      };
    })()`);

    const semantic = JSON.parse(
      await page.evaluate(`JSON.stringify({
        lang: document.documentElement.lang,
        tabs: [...document.querySelectorAll('.rail [role="tab"]')].map((node) => ({name: node.getAttribute('aria-label'), controls: node.getAttribute('aria-controls')})),
        panes: [...document.querySelectorAll('.stage > [role="tabpanel"]')].map((node) => ({id: node.id, labelledBy: node.getAttribute('aria-labelledby')})),
        selected: document.querySelectorAll('.rail [role="tab"][aria-selected="true"]').length,
        visible: document.querySelectorAll('.stage > .pane.is-active').length,
        kpis: document.querySelectorAll('[data-kpis] .kpi').length,
        liveChip: document.querySelector('.chip--live')?.textContent.trim(),
        syntheticText: /synthetic|demo data/i.test(document.body.innerText),
        scopeControls: document.querySelectorAll('[data-control]').length,
        metricAttribution: document.querySelector('.statusbar').innerText,
        pageText: document.body.innerText,
      })`),
    );
    assert(semantic.lang === "en", "Document language must be English");
    assert(
      semantic.tabs.length === 5 && semantic.panes.length === 5,
      "Expected five primary tabs and panes",
    );
    assert(
      semantic.selected === 1 && semantic.visible === 1,
      "Exactly one primary tab and pane must be active",
    );
    assert(
      semantic.tabs.every(
        (tab, index) => tab.controls === semantic.panes[index].id,
      ),
      "Tab controls do not match panes",
    );
    assert(
      semantic.panes.every(
        (pane, index) => pane.labelledBy === `tab-${TABS[index]}`,
      ),
      "Pane labels do not match tabs",
    );
    assert(semantic.kpis === 6, "Expected six canonical KPI cards");
    assert(
      semantic.liveChip === "Live data" && !semantic.syntheticText,
      "Dashboard must clearly render real rather than synthetic data",
    );
    assert(
      semantic.scopeControls >= 20,
      "Shared filter workbench is incomplete",
    );
    assert(
      semantic.metricAttribution.includes(
        "metrics computed by forecast_analysis",
      ),
      "Canonical metric attribution is missing",
    );
    const screenshots = [];
    const focusedScreenshots = [];
    const overviewAudits = [];
    const layouts = [];
    for (const viewport of VIEWPORTS) {
      await page.viewport(viewport.width, viewport.height);
      for (const tab of TABS) {
        await page.evaluate(
          `document.querySelector('[data-target="${tab}"]').click()`,
        );
        await waitFor(
          page,
          `!document.querySelector('#pane-${tab}').classList.contains('is-stale') && !document.querySelector('#pane-${tab}').classList.contains('is-module-loading')`,
          `${viewport.name}/${tab} lazy module load`,
        );
        await sleep(60);
        const layout = JSON.parse(
          await page.evaluate(`(() => {
            const active = document.querySelector('.stage > .pane.is-active');
            const rail = document.querySelector('.rail');
            const tabName = document.querySelector('.tab__name');
            const rect = active.getBoundingClientRect();
            return JSON.stringify({
              tab: document.querySelector('.rail [aria-selected="true"]')?.dataset.target,
              pane: active?.id,
              pageVertical: document.documentElement.scrollHeight - innerHeight,
              pageHorizontal: document.documentElement.scrollWidth - innerWidth,
              bodyVertical: document.body.scrollHeight - innerHeight,
              railWidth: Math.round(rail.getBoundingClientRect().width),
              tabNamesVisible: getComputedStyle(tabName).display !== 'none',
              paneInsideViewport: rect.left >= 0 && rect.top >= 0 && rect.right <= innerWidth + 1 && rect.bottom <= innerHeight + 1,
              visibleLoading: document.querySelector('.loading').classList.contains('is-visible'),
            });
          })()`),
        );
        assert(
          layout.tab === tab && layout.pane === `pane-${tab}`,
          `${viewport.name}/${tab}: wrong active pane`,
        );
        assert(
          layout.pageVertical === 0 && layout.bodyVertical === 0,
          `${viewport.name}/${tab}: document scrolling detected`,
        );
        assert(
          layout.pageHorizontal === 0,
          `${viewport.name}/${tab}: horizontal document overflow detected`,
        );
        assert(
          layout.paneInsideViewport,
          `${viewport.name}/${tab}: active pane exceeds viewport`,
        );
        assert(
          !layout.visibleLoading,
          `${viewport.name}/${tab}: loading overlay did not settle`,
        );
        if (viewport.name === "narrow") {
          assert(
            layout.railWidth === 76 && !layout.tabNamesVisible,
            "Narrow rail did not collapse correctly",
          );
        } else {
          assert(
            layout.railWidth === 232 && layout.tabNamesVisible,
            `${viewport.name}: desktop rail contract failed`,
          );
        }
        layouts.push({ viewport: viewport.name, ...layout });
        if (tab === "overview")
          overviewAudits.push(await overviewAudit(page, viewport));
        const name = `${viewport.width}-${viewport.height}-${tab}.png`;
        const path = join(args.output, name);
        await page.screenshot(path);
        screenshots.push({
          name,
          tab,
          viewport: viewport.name,
          sha256: sha256(path),
        });
      }
    }

    for (const viewport of FOCUSED_VIEWPORTS) {
      await page.viewport(viewport.width, viewport.height);
      await page.evaluate(
        `(() => {
          const shouldCollapse = ${viewport.collapseRail};
          const isCollapsed = document.querySelector('.body').classList.contains('is-rail-collapsed');
          if (shouldCollapse !== isCollapsed) document.querySelector('[data-action="rail"]').click();
          document.querySelector('[data-target="overview"]').click();
          document.querySelector('.overview-details').open = false;
          return new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        })()`,
        true,
      );
      await sleep(80);
      overviewAudits.push(await overviewAudit(page, viewport));
      const clip = await page.evaluate(`(() => {
        const bounds = document.querySelector('.workspace').getBoundingClientRect();
        return {x: Math.max(0, bounds.x), y: Math.max(0, bounds.y), width: Math.min(innerWidth - Math.max(0, bounds.x), bounds.width), height: Math.min(innerHeight - Math.max(0, bounds.y), bounds.height)};
      })()`);
      const name = `focused-${viewport.width}-${viewport.height}-overview.png`;
      const path = join(args.output, name);
      await page.screenshot(path, clip);
      focusedScreenshots.push({
        name,
        tab: "overview",
        viewport: viewport.name,
        sha256: sha256(path),
      });
    }

    await checkLazyEndpointCoverage(page);

    await page.viewport(1440, 900);
    await page.evaluate(`(() => {
      document.querySelector('[data-target="overview"]').click();
      document.querySelector('[data-action="scope"]').click();
      const product = document.querySelector('[data-control="parent_code"]');
      product.value = '703584';
      product.dispatchEvent(new Event('change', {bubbles: true}));
    })()`);
    await sleep(400);
    await waitFor(
      page,
      `!document.querySelector('.loading').classList.contains('is-visible') && document.querySelector('[data-control="parent_code"]').value === '703584' && document.querySelector('[data-action="scope"]')?.textContent.includes('Filters · 1')`,
      "shared product filter recomputation",
    );
    const filtered = JSON.parse(
      await page.evaluate(`JSON.stringify({
        filters: document.querySelector('[data-action="scope"]').textContent.trim(),
        product: document.querySelector('[data-control="parent_code"]').value,
        population: document.querySelector('[data-population]').innerText,
        scope: document.querySelector('[data-scope-primary]').innerText,
      })`),
    );
    assert(
      filtered.product === "703584",
      "Requested product filter was not retained",
    );
    assert(
      !filtered.filters.endsWith("0"),
      "Active filter count did not update",
    );
    assert(
      /products\s+1/i.test(filtered.scope),
      `Filtered scope did not collapse to one product: ${filtered.scope}`,
    );

    await page.evaluate(
      `document.querySelector('[data-action="reset"]').click()`,
    );
    await sleep(400);
    await waitFor(
      page,
      `!document.querySelector('.loading').classList.contains('is-visible') && document.querySelector('[data-control="parent_code"]').value === ''`,
      "reset before comparison",
    );
    await page.evaluate(`(() => {
      const mode = document.querySelector('[data-control="comparison_mode"]');
      mode.value = 'true';
      mode.dispatchEvent(new Event('change', {bubbles: true}));
    })()`);
    await sleep(400);
    await waitFor(
      page,
      `!document.querySelector('.loading').classList.contains('is-visible') && document.querySelector('[data-control="comparison_mode"]').value === 'true'`,
      "comparison mode recomputation",
    );
    await page.evaluate(
      `document.querySelector('[data-target="comparison"]').click(); document.querySelector('[data-subtabs="comparison"] [data-subtab-target="sources"]').click()`,
    );
    await waitFor(
      page,
      `!document.querySelector('#pane-comparison').classList.contains('is-stale') && document.querySelector('[data-source-panel]').innerText.trim().length > 0`,
      "lazy source comparison module",
    );
    const comparisonText = await page.evaluate(
      `document.querySelector('[data-source-panel]').innerText`,
    );
    assert(
      comparisonText.includes("Aligned"),
      `Comparison did not render aligned population: ${comparisonText}`,
    );
    assert(
      comparisonText.includes("TM") && comparisonText.includes("ML"),
      "Comparison must render both source metrics",
    );

    await page.evaluate(
      `document.querySelector('[data-action="reset"]').click()`,
    );
    await sleep(400);
    await waitFor(
      page,
      `!document.querySelector('.loading').classList.contains('is-visible') && document.querySelector('[data-control="comparison_mode"]').value === 'false'`,
      "dashboard reset",
    );
    await page.evaluate(
      `document.querySelector('[data-target="history"]').click(); (() => { const product = document.querySelector('[data-product-control="parent"]'); product.value = '999173'; product.dispatchEvent(new Event('change', {bubbles: true})); })()`,
    );
    await sleep(200);
    await waitFor(
      page,
      `!document.querySelector('#pane-history').classList.contains('is-stale') && !document.querySelector('#pane-history').classList.contains('is-module-loading') && document.querySelector('[data-product-summary]')?.innerText.includes('999173')`,
      "product drill-down",
    );
    const productState = JSON.parse(
      await page.evaluate(`JSON.stringify({
        selected: document.querySelector('[data-product-control="parent"]').value,
        summary: document.querySelector('[data-product-summary]').innerText,
        points: document.querySelectorAll('[data-history-chart] circle').length,
        metrics: document.querySelectorAll('[data-postmortem-metrics] .postmortem-metric').length,
        commentary: document.querySelectorAll('[data-postmortem-commentary] .postmortem-comment').length,
      })`),
    );
    assert(
      productState.selected === "999173" &&
        productState.summary.includes("999173"),
      "Product drill-down selection drifted",
    );
    assert(
      productState.points > 0 &&
        productState.metrics === 6 &&
        productState.commentary > 0,
      "Product history did not render points, post-mortem ledger and commentary",
    );

    await page.send("Page.setDownloadBehavior", {
      behavior: "allow",
      downloadPath: downloadDir,
    });
    await page.evaluate(
      `document.querySelector('[data-subtabs="history"] [data-subtab-target="exceptions"]').click()`,
    );
    await waitFor(
      page,
      `!document.querySelector('#pane-history').classList.contains('is-stale') && !!document.querySelector('[data-export-kind="vintages"]')`,
      "lazy exception module before export",
    );
    await page.evaluate(
      `document.querySelector('[data-export-kind="vintages"]').click()`,
    );
    const downloadDeadline = Date.now() + 60_000;
    while (
      Date.now() < downloadDeadline &&
      !readdirSync(downloadDir).some((name) => name.endsWith(".csv"))
    ) {
      await sleep(250);
    }
    const downloads = readdirSync(downloadDir).filter((name) =>
      name.endsWith(".csv"),
    );
    assert(
      downloads.some((name) => name.includes("filtered_vintages")),
      `Filtered CSV download did not complete: ${downloads.join(", ")}`,
    );
    rmSync(downloadDir, { recursive: true, force: true });

    assert(
      page.consoleErrors.length === 0,
      `Console warnings/errors: ${page.consoleErrors.join(" | ")}`,
    );
    assert(
      page.pageErrors.length === 0,
      `Page exceptions: ${page.pageErrors.join(" | ")}`,
    );
    assert(
      page.networkFailures.length === 0,
      `Network failures: ${page.networkFailures.join(" | ")}`,
    );
    assert(
      page.httpErrors.length === 0,
      `HTTP errors: ${page.httpErrors.join(" | ")}`,
    );

    const report = {
      generatedAt: new Date().toISOString(),
      baseUrl,
      semantic,
      filtered,
      comparison: comparisonText,
      product: productState,
      downloads,
      layouts,
      overviewAudits,
      screenshots,
      focusedScreenshots,
      consoleErrors: page.consoleErrors,
      pageErrors: page.pageErrors,
      networkFailures: page.networkFailures,
      httpErrors: page.httpErrors,
    };
    writeFileSync(
      join(args.output, "validation-report.json"),
      `${JSON.stringify(report, null, 2)}\n`,
    );
    writeFileSync(
      join(args.output, "validation-report.md"),
      `# Real dashboard UI validation\n\n- Result: PASS\n- Generated: ${report.generatedAt}\n- Matrix screenshots: ${screenshots.length}\n- Focused overview screenshots: ${focusedScreenshots.length}\n- Viewports: ${VIEWPORTS.map((viewport) => `${viewport.width}×${viewport.height}`).join(", ")}\n- Overview audits: ${overviewAudits.length} passed\n- Download: ${downloads.join(", ")}\n- Console/page/network errors: 0\n`,
    );
    writeFileSync(join(args.output, "index.html"), gallery(report));
    process.stdout.write("REAL DASHBOARD UI VALIDATION PASSED\n");
  } finally {
    page?.close();
    terminate(chrome);
    terminate(server);
    await sleep(1_200);
    rmSync(profileDir, {
      recursive: true,
      force: true,
      maxRetries: 5,
      retryDelay: 100,
    });
  }
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error.message || String(error)}\n`);
  process.exitCode = 1;
});
