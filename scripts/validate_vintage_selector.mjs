#!/usr/bin/env node

import { spawn, spawnSync } from "node:child_process";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { get as httpGet } from "node:http";
import { createServer } from "node:net";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { setTimeout as sleep } from "node:timers/promises";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
let output = join(ROOT, "validation-artifacts/vintage-selector");
const outputIndex = process.argv.indexOf("--output");
if (outputIndex >= 0) output = resolve(ROOT, process.argv[outputIndex + 1]);
const assert = (condition, message) => {
  if (!condition) throw new Error(message);
};
const commandExists = (command) =>
  spawnSync("sh", ["-c", `command -v ${command}`]).status === 0;
const freePort = () =>
  new Promise((resolvePort, reject) => {
    const server = createServer();
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      server.close(() => resolvePort(address.port));
    });
  });
const status = (url) =>
  new Promise((resolveStatus, reject) => {
    const request = httpGet(url, (response) => {
      response.resume();
      response.on("end", () => resolveStatus(response.statusCode || 0));
    });
    request.on("error", reject);
  });
async function waitForUrl(url) {
  for (let attempt = 0; attempt < 300; attempt += 1) {
    try {
      if ((await status(url)) === 200) return;
    } catch {}
    await sleep(200);
  }
  throw new Error(`Timed out waiting for ${url}`);
}
const terminate = (child) => {
  if (child?.exitCode === null) child.kill("SIGTERM");
};

class Page {
  constructor(url) {
    this.socket = new WebSocket(url);
    this.nextId = 0;
    this.pending = new Map();
    this.errors = [];
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
        this.errors.push(`Invalid CDP message: ${error.message}`);
        return;
      }
      if (message.id && this.pending.has(message.id)) {
        const pending = this.pending.get(message.id);
        this.pending.delete(message.id);
        if (message.error) pending.reject(new Error(message.error.message));
        else pending.resolve(message.result);
      } else if (message.method === "Runtime.exceptionThrown") {
        this.errors.push(message.params.exceptionDetails.text);
      }
    };
    await this.send("Page.enable");
    await this.send("Runtime.enable");
  }
  send(method, params = {}) {
    return new Promise((resolveCommand, rejectCommand) => {
      const id = ++this.nextId;
      this.pending.set(id, { resolve: resolveCommand, reject: rejectCommand });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }
  async evaluate(expression) {
    const result = await this.send("Runtime.evaluate", {
      expression,
      returnByValue: true,
      awaitPromise: true,
    });
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.text);
    return result.result.value;
  }
  async viewport(width, height) {
    await this.send("Emulation.setDeviceMetricsOverride", {
      width,
      height,
      deviceScaleFactor: 1,
      mobile: false,
    });
  }
  async screenshot(path) {
    const result = await this.send("Page.captureScreenshot", { format: "png" });
    writeFileSync(path, Buffer.from(result.data, "base64"));
  }
}
async function waitFor(page, expression, label) {
  for (let attempt = 0; attempt < 300; attempt += 1) {
    if (await page.evaluate(expression)) return;
    await sleep(200);
  }
  throw new Error(`Timed out: ${label}`);
}

const requestKey = (ids) => JSON.stringify(ids);

async function selectVintageIds(page, ids) {
  const before = await page.evaluate(
    `window.__vintageValidation?.compactResponses?.length || 0`,
  );
  if (
    await page.evaluate(`document.querySelector('.vintage-selector').hidden`)
  ) {
    await page.evaluate(
      `document.querySelector('[data-vintage-selector-trigger]').click()`,
    );
  }
  await waitFor(
    page,
    `!document.querySelector('.vintage-selector').hidden`,
    "selector open for selection",
  );
  const changed = await page.evaluate(`(() => {
    const wanted = new Set(${JSON.stringify(ids)});
    const options = [...document.querySelectorAll('[data-vintage-option]')];
    const change = options.find((option) => option.checked !== wanted.has(option.value));
    if (!change) return false;
    change.checked = wanted.has(change.value);
    change.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
  })()`);
  if (!changed) {
    const current = await page.evaluate(
      `JSON.stringify([...document.querySelectorAll('[data-vintage-option]:checked')].map((option) => option.value))`,
    );
    assert(
      current === requestKey(ids),
      `selector state differs from ${requestKey(ids)}`,
    );
    return;
  }
  await waitFor(
    page,
    `(() => {
      const record = window.__vintageValidation?.compactResponses?.at(-1);
      return (window.__vintageValidation?.compactResponses?.length || 0) > ${before} &&
        JSON.stringify(record?.request?.accuracy_vintage_ids || []) === ${JSON.stringify(requestKey(ids))} &&
        !document.querySelector('.loading')?.classList.contains('is-visible');
    })()`,
    `selection ${requestKey(ids)}`,
  );
}

function verifyCommonCohort(payload) {
  const selected = [
    ...(payload?.accuracy_vintages?.options || []).filter(
      (option) => option.selected,
    ),
    payload?.accuracy_vintages?.latest,
  ].filter(Boolean);
  assert(selected.length >= 1, "response contains no plotted vintage series");
  const monthMaps = selected.map(
    (series) =>
      new Map((series.rows || []).map((row) => [row.snop_month, row])),
  );
  const months = [...monthMaps[0].keys()];
  assert(months.length > 0, "response contains no common-cohort months");
  for (const month of months) {
    const rows = monthMaps.map((map) => map.get(month));
    assert(rows.every(Boolean), `series do not share target month ${month}`);
    const eligible = new Set(rows.map((row) => row.eligible_parents));
    const denominators = new Set(
      rows.map((row) => Number(row.actual_denominator_kl).toFixed(9)),
    );
    assert(
      eligible.size === 1 && denominators.size === 1,
      `cohort evidence differs at ${month}`,
    );
  }
  return { series: selected.length, months: months.length };
}

async function main() {
  assert(
    commandExists("uv") && commandExists("chromium"),
    "uv and chromium are required",
  );
  rmSync(output, { recursive: true, force: true });
  mkdirSync(output, { recursive: true });
  const serverPort = await freePort();
  const debugPort = await freePort();
  const profile = `/tmp/vintage-selector-${Date.now()}`;
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
    { cwd: ROOT, stdio: "ignore" },
  );
  const chrome = spawn(
    "chromium",
    [
      "--headless=new",
      "--no-sandbox",
      "--disable-gpu",
      `--remote-debugging-port=${debugPort}`,
      `--user-data-dir=${profile}`,
      "about:blank",
    ],
    { stdio: "ignore" },
  );
  let page;
  try {
    await waitForUrl(`http://127.0.0.1:${serverPort}/api/health`);
    await waitForUrl(`http://127.0.0.1:${debugPort}/json/version`);
    const target = await (
      await fetch(`http://127.0.0.1:${debugPort}/json/new?about:blank`, {
        method: "PUT",
      })
    ).json();
    page = new Page(target.webSocketDebuggerUrl);
    await page.connect();
    await page.send("Page.addScriptToEvaluateOnNewDocument", {
      source: `(() => {
        window.__vintageValidation = { compactRequests: [], compactResponses: [] };
        const nativeFetch = window.fetch.bind(window);
        window.fetch = async (...args) => {
          const [input, init = {}] = args;
          const url = typeof input === 'string' ? input : input?.url || String(input);
          const tracked = url.includes('api/bootstrap') || url.includes('api/view/compact');
          let request = null;
          if (url.includes('api/view/compact') && init.body) {
            try { request = JSON.parse(init.body); } catch {}
            window.__vintageValidation.compactRequests.push(request);
          }
          const response = await nativeFetch(...args);
          if (tracked) {
            try {
              const payload = await response.clone().json();
              window.__vintageValidation.compactResponses.push({
                request: request || payload.request,
                payload,
                status: response.status,
                url,
              });
            } catch {}
          }
          return response;
        };
      })()`,
    });
    await page.viewport(1440, 900);
    await page.send("Page.navigate", {
      url: `http://127.0.0.1:${serverPort}/#overview`,
    });
    await waitFor(
      page,
      `document.querySelector('[data-status]')?.textContent.includes('canonical dataset ready')`,
      "dashboard bootstrap",
    );
    await page.evaluate("document.fonts.ready");
    await waitFor(
      page,
      `Boolean(window.__vintageValidation?.compactResponses?.length)`,
      "captured bootstrap response",
    );

    const initialResponse = await page.evaluate(
      `window.__vintageValidation.compactResponses.at(-1)`,
    );
    assert(
      requestKey(initialResponse.request.accuracy_vintage_ids) ===
        requestKey(["oldest_available"]),
      `default request is not oldest-only selection: ${JSON.stringify(initialResponse.request)}`,
    );
    const initialCohort = verifyCommonCohort(initialResponse.payload);
    const initialMetrics = JSON.stringify(initialResponse.payload.metrics);

    const inspect = () =>
      page.evaluate(`(() => {
      const lines = [...document.querySelectorAll('[data-overview-chart] [data-vintage-id]')].filter((node) => node.tagName === 'path' || node.tagName === 'PATH');
      const fixed = lines.filter((node) => node.dataset.vintageFixed === 'true');
      const frame = document.querySelector('#overview-chart-title').closest('.frame');
      const actions = frame.querySelector('.frame__actions');
      const trigger = actions.querySelector('[data-vintage-selector-trigger]');
      const fullscreen = actions.querySelector('[data-chart-fullscreen="accuracy"]');
      const triggerRect = trigger.getBoundingClientRect();
      const fullscreenRect = fullscreen.getBoundingClientRect();
      const actionRect = actions.getBoundingClientRect();
      const frameRect = frame.getBoundingClientRect();
      const chartRect = frame.querySelector('[data-overview-chart]').getBoundingClientRect();
      const pathsContained = lines.every((line)=>{const rect=line.getBoundingClientRect();return rect.left>=chartRect.left-2&&rect.right<=chartRect.right+2&&rect.top>=chartRect.top-2&&rect.bottom<=chartRect.bottom+2});
      return {lineIds:lines.map((node)=>node.dataset.vintageId),fixed:fixed.length,count:trigger.querySelector('[data-vintage-selector-count]').textContent,triggerBeforeFullscreen:triggerRect.right<=fullscreenRect.left+1,actionsContained:triggerRect.left>=actionRect.left-1&&fullscreenRect.right<=actionRect.right+1,toolbarInsideFrame:actionRect.left>=frameRect.left&&actionRect.right<=frameRect.right+1,pathsContained,pageOverflow:document.documentElement.scrollWidth-innerWidth};
    })()`);

    const initial = await inspect();
    assert(initial.fixed === 1, "latest series is not fixed and unique");
    assert(
      initial.lineIds.includes("oldest_available") &&
        initial.lineIds.includes("latest_available"),
      "default oldest/latest series missing",
    );
    assert(initial.count === "1", "default selected count is not one");
    assert(
      initial.triggerBeforeFullscreen &&
        initial.actionsContained &&
        initial.toolbarInsideFrame &&
        initial.pathsContained,
      "selector or chart geometry is invalid",
    );

    await page.evaluate(
      `document.querySelector('[data-vintage-selector-trigger]').click()`,
    );
    await waitFor(
      page,
      `!document.querySelector('.vintage-selector').hidden`,
      "selector open",
    );
    const menu = await page.evaluate(
      `(() => ({fixedText:document.querySelector('.vintage-selector__fixed').textContent,options:[...document.querySelectorAll('[data-vintage-option]')].map((node)=>({value:node.value,checked:node.checked})),overflow:document.querySelector('.vintage-selector').getBoundingClientRect().right-innerWidth}))()`,
    );
    assert(
      menu.fixedText.includes("Latest (1 month ahead)") &&
        menu.fixedText.toLowerCase().includes("fixed"),
      `fixed latest is not explained: ${menu.fixedText}`,
    );
    assert(
      menu.options.length === 4 &&
        menu.options[0].value === "oldest_available" &&
        menu.options[0].checked,
      "canonical M5-to-M2 options/default are incomplete",
    );
    assert(menu.overflow <= 0, "selector popover overflows viewport");
    await page.screenshot(join(output, "desktop-open.png"));

    const extraVintageIds = menu.options
      .slice(1, 3)
      .map((option) => option.value);
    const multiIds = ["oldest_available", ...extraVintageIds];
    await selectVintageIds(page, ["oldest_available", extraVintageIds[0]]);
    await selectVintageIds(page, multiIds);
    const multiResponse = await page.evaluate(
      `window.__vintageValidation.compactResponses.at(-1)`,
    );
    const multiCohort = verifyCommonCohort(multiResponse.payload);
    assert(
      JSON.stringify(multiResponse.payload.metrics) === initialMetrics,
      "chart-local vintage selection changed global KPI metrics",
    );
    const multi = await inspect();
    assert(
      multi.fixed === 1 &&
        multi.lineIds.length === 4 &&
        multi.count === "3" &&
        multi.pathsContained,
      `multi-select failed: ${JSON.stringify(multi)}`,
    );
    const hit = await page.evaluate(`(() => {
      const points = [...document.querySelectorAll('[data-overview-chart] .chart__month-hit')];
      const point = points.find((candidate) => Number.parseInt(candidate.dataset.tooltipCommonCohort, 10) > 0);
      if (!point) return null;
      point.dispatchEvent(new PointerEvent('pointerover', { bubbles: true, clientX: 500, clientY: 350 }));
      return {
        cohort: point.dataset.tooltipCommonCohort,
        denominator: point.dataset.tooltipActualDenominator,
      };
    })()`);
    await waitFor(
      page,
      `document.querySelector('.chart-tooltip')?.textContent.includes('Common cohort') && document.querySelector('.chart-tooltip')?.textContent.includes('Actual denominator')`,
      "common-cohort tooltip",
    );
    assert(
      Number.parseInt(hit?.cohort, 10) > 0 && hit?.denominator !== "0.0 KL",
      "chart point lacks non-empty cohort evidence",
    );
    await page.evaluate(
      `document.querySelector('[data-overview-chart] .chart__month-hit[aria-describedby]')?.dispatchEvent(new PointerEvent('pointerout', { bubbles: true }))`,
    );
    await waitFor(
      page,
      `document.querySelector('.chart-tooltip')?.hidden`,
      "tooltip dismissed before screenshot",
    );
    await page.screenshot(join(output, "desktop-multi.png"));

    await selectVintageIds(page, extraVintageIds);
    const replaced = await inspect();
    assert(
      replaced.fixed === 1 &&
        !replaced.lineIds.includes("oldest_available") &&
        replaced.count === "2",
      "oldest could not be deselected while retaining latest",
    );

    await selectVintageIds(page, [extraVintageIds[1]]);
    await selectVintageIds(page, []);
    const latestOnlyResponse = await page.evaluate(
      `window.__vintageValidation.compactResponses.at(-1)`,
    );
    const latestOnlyCohort = verifyCommonCohort(latestOnlyResponse.payload);
    const latestOnly = await inspect();
    assert(
      latestOnly.fixed === 1 &&
        latestOnly.lineIds.length === 1 &&
        latestOnly.count === "0",
      "latest-only state failed",
    );

    await page.evaluate(
      `document.querySelector('[data-chart-fullscreen="accuracy"]').click()`,
    );
    await waitFor(
      page,
      `!document.querySelector('#overview-chart-dialog').hidden`,
      "accuracy full screen",
    );
    const fullscreen = await page.evaluate(
      `(() => ({triggerVisible:!document.querySelector('.chart-dialog [data-vintage-selector-trigger]').hidden,fixed:document.querySelectorAll('.chart-dialog__body [data-vintage-fixed="true"]').length,lines:document.querySelectorAll('.chart-dialog__body path[data-vintage-id]').length,overflow:document.documentElement.scrollWidth-innerWidth}))()`,
    );
    assert(
      fullscreen.triggerVisible &&
        fullscreen.fixed === 1 &&
        fullscreen.lines === 1 &&
        fullscreen.overflow === 0,
      "full-screen latest-only parity failed",
    );
    await page.screenshot(join(output, "fullscreen-latest-only.png"));
    await page.evaluate(
      `document.querySelector('.chart-dialog [data-vintage-selector-trigger]').click()`,
    );
    await waitFor(
      page,
      `!document.querySelector('.vintage-selector').hidden`,
      "full-screen selector open",
    );
    const fullscreenMenu = await page.evaluate(
      `(() => { const menu=document.querySelector('.vintage-selector').getBoundingClientRect(); const trigger=document.querySelector('.chart-dialog [data-vintage-selector-trigger]').getBoundingClientRect(); return {insideViewport:menu.left>=0&&menu.top>=0&&menu.right<=innerWidth&&menu.bottom<=innerHeight,anchored:menu.right<=trigger.right+1}; })()`,
    );
    assert(
      fullscreenMenu.insideViewport && fullscreenMenu.anchored,
      `full-screen selector geometry failed: ${JSON.stringify(fullscreenMenu)}`,
    );
    await page.screenshot(join(output, "fullscreen-selector-open.png"));
    await page.evaluate(
      `document.querySelector('.chart-dialog [data-vintage-selector-trigger]').click()`,
    );

    for (const viewport of [
      { name: "wide", width: 1680, height: 1050 },
      { name: "compact", width: 800, height: 700 },
    ]) {
      await page.evaluate(
        `document.querySelector('[data-action="overview-fullscreen-close"]').click()`,
      );
      await page.viewport(viewport.width, viewport.height);
      await selectVintageIds(page, ["oldest_available"]);
      const layout = await inspect();
      assert(
        layout.triggerBeforeFullscreen &&
          layout.actionsContained &&
          layout.toolbarInsideFrame &&
          layout.pathsContained &&
          layout.pageOverflow === 0,
        `${viewport.name} toolbar/chart geometry failed: ${JSON.stringify(layout)}`,
      );
      await page.screenshot(join(output, `${viewport.name}.png`));
      if (viewport.name === "wide") {
        await page.evaluate(
          `document.querySelector('[data-chart-fullscreen="accuracy"]').click()`,
        );
        await waitFor(
          page,
          `!document.querySelector('#overview-chart-dialog').hidden`,
          "wide full screen",
        );
      }
    }
    assert(page.errors.length === 0, `page errors: ${page.errors.join(" | ")}`);
    writeFileSync(
      join(output, "validation-report.json"),
      `${JSON.stringify({ initial, initialCohort, menu, multi, multiCohort, hit, replaced, latestOnly, latestOnlyCohort, fullscreen, fullscreenMenu }, null, 2)}\n`,
    );
    process.stdout.write("VINTAGE SELECTOR VALIDATION PASSED\n");
  } finally {
    page?.socket.close();
    terminate(chrome);
    terminate(server);
    rmSync(profile, { recursive: true, force: true });
  }
}
main().catch((error) => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
