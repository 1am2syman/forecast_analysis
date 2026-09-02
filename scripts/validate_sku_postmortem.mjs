#!/usr/bin/env node

/** Browser contract for the dashboard-native SKU post-mortem page. */

import { spawn, spawnSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { createServer } from "node:net";
import { join, resolve } from "node:path";
import { setTimeout as sleep } from "node:timers/promises";

const ROOT = resolve(new URL("..", import.meta.url).pathname);
const OUTPUT = join(ROOT, "validation-artifacts/sku-postmortem");
const BASE_URL = process.env.SKU_POSTMORTEM_BASE_URL || "http://127.0.0.1:8876/";
const VIEWPORTS = [
  { name: "desktop", width: 1440, height: 900 },
  { name: "wide", width: 1680, height: 1050 },
  { name: "compact", width: 800, height: 700 },
];

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function commandExists(command) {
  return spawnSync("sh", ["-c", `command -v ${command}`]).status === 0;
}

function freePort() {
  return new Promise((resolvePort, reject) => {
    const server = createServer();
    server.unref();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      assert(address && typeof address === "object", "Could not allocate CDP port");
      server.close(() => resolvePort(address.port));
    });
  });
}

async function waitFor(url, timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs;
  let lastError;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
      lastError = new Error(`${url} returned ${response.status}`);
    } catch (error) {
      lastError = error;
    }
    await sleep(250);
  }
  throw new Error(`Timed out waiting for ${url}: ${lastError}`);
}

class Page {
  constructor(webSocketUrl) {
    this.socket = new WebSocket(webSocketUrl);
    this.nextId = 0;
    this.pending = new Map();
    this.errors = [];
  }

  async connect() {
    await new Promise((resolveConnect, rejectConnect) => {
      this.socket.onopen = resolveConnect;
      this.socket.onerror = rejectConnect;
    });
    this.socket.onmessage = (event) => {
      const message = JSON.parse(String(event.data));
      if (message.id && this.pending.has(message.id)) {
        const pending = this.pending.get(message.id);
        this.pending.delete(message.id);
        if (message.error) pending.reject(new Error(message.error.message));
        else pending.resolve(message.result);
      } else if (message.method === "Runtime.exceptionThrown") {
        this.errors.push(message.params.exceptionDetails.text);
      } else if (message.method === "Runtime.consoleAPICalled" && ["error", "warning"].includes(message.params.type)) {
        this.errors.push(message.params.args.map((arg) => arg.value ?? arg.description ?? "").join(" "));
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
      width, height, deviceScaleFactor: 1, mobile: false,
    });
  }

  async screenshot(path) {
    const result = await this.send("Page.captureScreenshot", { format: "png" });
    writeFileSync(path, Buffer.from(result.data, "base64"));
  }

  close() { this.socket.close(); }
}

async function openPage(debugPort) {
  const response = await fetch(`http://127.0.0.1:${debugPort}/json/new?about:blank`, { method: "PUT" });
  const target = await response.json();
  const page = new Page(target.webSocketDebuggerUrl);
  await page.connect();
  await page.send("Page.enable");
  await page.send("Runtime.enable");
  await page.send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: "reduce" }] });
  return page;
}

async function waitForExpression(page, expression, label, timeoutMs = 60000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await page.evaluate(expression)) return;
    await sleep(300);
  }
  throw new Error(`Timed out waiting for ${label}`);
}

function terminate(process) {
  if (process.exitCode === null) process.kill("SIGTERM");
}

async function main() {
  assert(commandExists("chromium"), "chromium is required");
  await waitFor(`${BASE_URL}api/health`, 20000);
  rmSync(OUTPUT, { recursive: true, force: true });
  mkdirSync(OUTPUT, { recursive: true });
  const debugPort = await freePort();
  const profileDir = join("/tmp", `sku-postmortem-chrome-${randomUUID()}`);
  const chrome = spawn("chromium", [
    "--headless=new", "--no-sandbox", "--disable-gpu",
    `--remote-debugging-port=${debugPort}`, `--user-data-dir=${profileDir}`, "about:blank",
  ], { stdio: ["ignore", "ignore", "pipe"] });
  let page;
  try {
    await waitFor(`http://127.0.0.1:${debugPort}/json/version`, 20000);
    page = await openPage(debugPort);
    await page.send("Page.navigate", { url: `${BASE_URL}#history` });
    await waitForExpression(page, `(() => {
      const pane = document.querySelector('#pane-history');
      return pane?.classList.contains('is-active') &&
        !pane.classList.contains('is-module-loading') &&
        !document.querySelector('.loading')?.classList.contains('is-visible') &&
        document.querySelector('[data-product-summary]')?.innerText.trim().length > 0;
    })()`, "history product module");
    await page.evaluate(`document.querySelector('[data-subtabs="history"] [data-subtab-target="product"]')?.click()`);
    await waitForExpression(page, `document.querySelector('[data-postmortem-decision]')?.innerText.trim().length > 0 && document.querySelectorAll('[data-postmortem-metrics] .postmortem-metric').length === 6`, "post-mortem render");

    const screenshots = [];
    const audits = [];
    for (const viewport of VIEWPORTS) {
      await page.viewport(viewport.width, viewport.height);
      await sleep(150);
      const audit = await page.evaluate(`(() => {
        const pane = document.querySelector('#pane-history');
        const product = document.querySelector('[data-product-control="parent"]');
        const metrics = document.querySelectorAll('[data-postmortem-metrics] .postmortem-metric');
        const revisionPoints = document.querySelectorAll('[data-postmortem-revision-chart] .postmortem-revision-chart__point');
        const commentary = document.querySelectorAll('[data-postmortem-commentary] .postmortem-comment');
        const historyContext = document.querySelector('.history-context');
        const historyToolbar = document.querySelector('.history-context .history-toolbar');
        const productSummary = document.querySelector('.history-context [data-product-summary]');
        const contextLabels = [...document.querySelectorAll('.history-context .field__k, .history-context [data-product-summary] b')].map((node) => node.innerText.trim());
        const contextChildren = [historyToolbar, productSummary].map((node) => node?.getBoundingClientRect());
        const summaryLabelLines = [...document.querySelectorAll('.history-context [data-product-summary] b')].map((node) => Math.round(node.getBoundingClientRect().height));
        const sectionRects = [...document.querySelectorAll('[data-postmortem-decision], [data-postmortem-metrics], .postmortem-primary, .postmortem-secondary, .postmortem-detail-grid, [data-postmortem-treatment]')].map((node) => ({top: node.getBoundingClientRect().top, bottom: node.getBoundingClientRect().bottom, left: node.getBoundingClientRect().left, right: node.getBoundingClientRect().right}));
        const overlap = sectionRects.some((rect, index) => sectionRects.slice(index + 1).some((other) => rect.left < other.right && rect.right > other.left && rect.top < other.bottom && rect.bottom > other.top));
        return {
          viewport: {width: innerWidth, height: innerHeight},
          selected: product?.value || null,
          paneActive: pane?.classList.contains('is-active') || false,
          contextLabels,
          contextSingleRow: Boolean(historyContext && contextChildren.every((rect) => rect && Math.abs(rect.top - contextChildren[0].top) <= 1 && Math.abs(rect.bottom - contextChildren[0].bottom) <= 1)),
          contextOrder: Boolean(historyToolbar && productSummary && historyToolbar.compareDocumentPosition(productSummary) & Node.DOCUMENT_POSITION_FOLLOWING),
          summaryLabelLines,
          metrics: metrics.length,
          performancePaths: document.querySelectorAll('[data-postmortem-performance-chart] path').length,
          revisionPoints: revisionPoints.length,
          revisionZero: !!document.querySelector('[data-postmortem-revision-chart] .postmortem-revision-chart__zero'),
          commentary: commentary.length,
          peers: document.querySelectorAll('[data-postmortem-peers] .postmortem-peer').length,
          treatment: document.querySelector('[data-postmortem-treatment]')?.innerText.trim().length || 0,
          documentHorizontalOverflow: document.documentElement.scrollWidth - innerWidth,
          bodyHorizontalOverflow: document.body.scrollWidth - innerWidth,
          paneHorizontalOverflow: pane ? pane.scrollWidth - pane.clientWidth : 0,
          overlap,
          displayFont: getComputedStyle(document.querySelector('.pane__title')).fontFamily,
          bodyFont: getComputedStyle(document.body).fontFamily,
          background: getComputedStyle(document.body).backgroundColor,
          title: document.querySelector('.pane__title')?.innerText || '',
          fullscreenButtons: document.querySelectorAll('#pane-history [data-chart-fullscreen]').length,
          firstChartVisiblePx: (() => {
            const rect = document.querySelector('[data-postmortem-performance-chart]')?.getBoundingClientRect();
            return rect ? Math.max(0, Math.min(rect.bottom, innerHeight - 30) - Math.max(rect.top, 0)) : 0;
          })(),
          metricFont: parseFloat(getComputedStyle(document.querySelector('.postmortem-metric strong')).fontSize),
          commentaryFont: parseFloat(getComputedStyle(document.querySelector('.postmortem-comment__copy p')).fontSize),
          metadataFont: parseFloat(getComputedStyle(document.querySelector('.product-summary strong')).fontSize),
        };
      })()`);
      assert(audit.paneActive, `${viewport.name}: history pane is not active`);
      assert(audit.selected, `${viewport.name}: no selected SKU`);
      assert(JSON.stringify(audit.contextLabels) === JSON.stringify(["PRODUCT", "TARGET MONTH", "BRAND", "SKU CLASS"]), `${viewport.name}: history context fields are duplicated or out of order`);
      assert(audit.contextSingleRow, `${viewport.name}: history context does not stay on one row`);
      assert(audit.contextOrder, `${viewport.name}: history selectors must precede metadata`);
      assert(audit.summaryLabelLines.every((height) => height <= 10), `${viewport.name}: history metadata labels wrap`);
      assert(audit.metrics === 6, `${viewport.name}: expected six post-mortem metrics`);
      assert(audit.performancePaths >= 2, `${viewport.name}: forecast/actual chart missing`);
      assert(audit.revisionPoints > 0 && audit.revisionZero, `${viewport.name}: revision zero-baseline chart missing`);
      assert(audit.commentary > 0, `${viewport.name}: categorized commentary missing`);
      assert(audit.peers >= 2, `${viewport.name}: sibling benchmark missing`);
      assert(audit.treatment > 0, `${viewport.name}: forward treatment missing`);
      assert(audit.documentHorizontalOverflow <= 2 && audit.bodyHorizontalOverflow <= 2 && audit.paneHorizontalOverflow <= 2, `${viewport.name}: horizontal overflow detected`);
      assert(!audit.overlap, `${viewport.name}: post-mortem sections overlap`);
      assert(/Chakra Petch/i.test(audit.displayFont) && /IBM Plex/i.test(audit.bodyFont), `${viewport.name}: dashboard typography tokens missing`);
      assert(audit.background === "rgb(237, 243, 241)", `${viewport.name}: dashboard background token missing`);
      assert(audit.fullscreenButtons >= 3, `${viewport.name}: chart full-screen controls missing`);
      assert(audit.firstChartVisiblePx >= 100, `${viewport.name}: first chart is not meaningfully visible on landing`);
      assert(audit.metricFont >= 16 && audit.commentaryFont >= 9 && audit.metadataFont >= 9.5, `${viewport.name}: post-mortem typography remains too small`);
      const path = join(OUTPUT, `${viewport.name}-${viewport.width}x${viewport.height}.png`);
      await page.screenshot(path);
      audits.push(audit);
      screenshots.push(path);
      if (["desktop", "compact"].includes(viewport.name)) {
        await page.evaluate(`(() => {
          const panel = document.querySelector('[data-subpanel="history:product"]');
          panel.scrollTop = panel.scrollHeight;
          return new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        })()`, true);
        const lowerPath = join(OUTPUT, `${viewport.name}-${viewport.width}x${viewport.height}-lower.png`);
        await page.screenshot(lowerPath);
        screenshots.push(lowerPath);
        await page.evaluate(`document.querySelector('[data-subpanel="history:product"]').scrollTop = 0`);
      }
    }
    await page.viewport(1440, 900);
    const fullscreenAudits = [];
    for (const kind of ["postmortem-performance", "postmortem-revision", "product-history"]) {
      await page.evaluate(`document.querySelector('[data-chart-fullscreen="${kind}"]').click()`);
      await waitForExpression(page, `!document.querySelector('#overview-chart-dialog').hidden && document.querySelector('#overview-chart-dialog').dataset.chartKind === '${kind}' && document.querySelector('[data-overview-chart-fullscreen] svg')`, `${kind} fullscreen chart`);
      const audit = await page.evaluate(`(() => ({
        kind: document.querySelector('#overview-chart-dialog').dataset.chartKind,
        title: document.querySelector('#overview-chart-dialog-title').innerText,
        chartWidth: document.querySelector('[data-overview-chart-fullscreen] svg').getBoundingClientRect().width,
        chartHeight: document.querySelector('[data-overview-chart-fullscreen] svg').getBoundingClientRect().height,
      }))()`);
      assert(audit.chartWidth > 900 && audit.chartHeight > 500, `${kind}: fullscreen chart did not use the dialog canvas`);
      const fullscreenPath = join(OUTPUT, `fullscreen-${kind}.png`);
      await page.screenshot(fullscreenPath);
      screenshots.push(fullscreenPath);
      fullscreenAudits.push(audit);
      await page.evaluate(`document.querySelector('[data-action="overview-fullscreen-close"]').click()`);
    }
    assert(page.errors.length === 0, `Browser errors: ${page.errors.join(" | ")}`);
    writeFileSync(join(OUTPUT, "validation-report.json"), `${JSON.stringify({ baseUrl: BASE_URL, audits, fullscreenAudits, screenshots }, null, 2)}\n`);
    writeFileSync(join(OUTPUT, "validation-report.md"), `# SKU post-mortem browser validation\n\n- Result: PASS\n- Viewports: ${VIEWPORTS.map((viewport) => `${viewport.width}×${viewport.height}`).join(", ")}\n- Core sections: decision, ledger, forecast/actual, commentary, revision outcome, peers, evidence, treatment\n- Landing-page chart visibility: at least 100 px at every validated viewport\n- Full-screen charts: forecast/actual, revision outcome, selected-target development\n- Minimum checked fonts: KPI 16 px, commentary 9 px, product metadata 9.5 px\n- Browser errors: 0\n`);
    process.stdout.write("sku postmortem browser validation passed\n");
  } finally {
    page?.close();
    terminate(chrome);
    await sleep(800);
    rmSync(profileDir, { recursive: true, force: true, maxRetries: 5 });
  }
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error.message || String(error)}\n`);
  process.exitCode = 1;
});
