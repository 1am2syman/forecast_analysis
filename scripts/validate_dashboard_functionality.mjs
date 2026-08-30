#!/usr/bin/env node

/** Exhaustive real-Chromium interaction validation for the forecast dashboard. */

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
  "validation-artifacts/static-dashboard-browser-exhaustive",
);
const TABS = ["overview", "trends", "comparison", "history", "quality"];

function parseArgs(argv) {
  const args = { output: DEFAULT_OUTPUT };
  for (let index = 0; index < argv.length; index += 1) {
    if (argv[index] === "--output") {
      args.output = resolve(ROOT, argv[index + 1]);
      index += 1;
    } else if (argv[index] === "--help") {
      process.stdout.write(
        "Usage: node scripts/validate_dashboard_functionality.mjs [--output DIR]\n",
      );
      process.exit(0);
    } else throw new Error(`Unknown argument: ${argv[index]}`);
  }
  return args;
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function commandExists(command) {
  return (
    spawnSync("sh", ["-c", `command -v ${command}`], { encoding: "utf8" })
      .status === 0
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
      const code = await status(url);
      if (code >= 200 && code < 300) return;
      lastError = new Error(`${url} returned ${code}`);
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
  setTimeout(
    () => process.exitCode === null && process.kill("SIGKILL"),
    1_000,
  ).unref();
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
      if (
        message.method === "Runtime.consoleAPICalled" &&
        ["error", "warning"].includes(message.params.type)
      ) {
        this.consoleErrors.push(
          message.params.args
            .map((arg) => arg.value ?? arg.description ?? "")
            .join(" "),
        );
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
    if (result.exceptionDetails) {
      const description = result.exceptionDetails.exception?.description;
      throw new Error(description || result.exceptionDetails.text);
    }
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

  async screenshot(path) {
    const result = await this.send("Page.captureScreenshot", { format: "png" });
    writeFileSync(path, Buffer.from(result.data, "base64"));
  }

  close() {
    this.socket.close();
  }
}

async function browserPage(debugPort) {
  const response = await fetch(
    `http://127.0.0.1:${debugPort}/json/new?about:blank`,
    { method: "PUT" },
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
    await sleep(120);
  }
  throw new Error(`Timed out: ${message}`);
}

function sha256(path) {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

function valueAt(object, path) {
  return path.split(".").reduce((value, key) => value?.[key], object);
}

function gallery(report) {
  const cards = report.screenshots
    .map(
      (shot) =>
        `<figure><img src="${shot.name}" alt="${shot.label}"/><figcaption>${shot.label}</figcaption></figure>`,
    )
    .join("");
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Exhaustive dashboard validation</title><style>body{margin:0;padding:28px;background:#edf3f1;color:#172421;font:14px system-ui}h1{margin-top:0}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:18px}figure{margin:0;padding:10px;background:#fff;border:1px solid #c8d5d1;border-radius:8px}img{display:block;width:100%;border:1px solid #dbe4e1}figcaption{padding-top:8px;font-family:monospace}</style></head><body><h1>Exhaustive dashboard functionality</h1><p>${report.checks.length} checks · ${report.controlInventory.length} shared controls · ${report.generatedAt}</p><main>${cards}</main></body></html>`;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  for (const command of ["uv", "chromium"])
    assert(commandExists(command), `Required command is missing: ${command}`);
  rmSync(args.output, { recursive: true, force: true });
  mkdirSync(args.output, { recursive: true });
  const downloadDir = join(args.output, "downloads");
  mkdirSync(downloadDir, { recursive: true });

  const serverPort = await freePort();
  const debugPort = await freePort();
  const profileDir = join("/tmp", `dashboard-exhaustive-${randomUUID()}`);
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
    await page.send("Page.setDownloadBehavior", {
      behavior: "allow",
      downloadPath: downloadDir,
    });
    await page.send("Page.navigate", { url: `${baseUrl}#overview` });
    await waitFor(
      page,
      `document.querySelector('[data-status]')?.textContent.includes('canonical dataset ready') && !document.querySelector('.loading')?.classList.contains('is-visible')`,
      "dashboard bootstrap",
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

    const checks = [];
    const failures = [];
    const check = async (name, callback) => {
      const started = Date.now();
      try {
        const detail = await callback();
        checks.push({
          name,
          status: "pass",
          durationMs: Date.now() - started,
          detail: detail ?? null,
        });
      } catch (error) {
        const message = error.stack || error.message || String(error);
        checks.push({
          name,
          status: "fail",
          durationMs: Date.now() - started,
          detail: message,
        });
        failures.push(`${name}: ${error.message || error}`);
      }
    };

    const controlInventory = JSON.parse(
      await page.evaluate(
        `JSON.stringify([...document.querySelectorAll('[data-control]')].map((control) => ({name: control.dataset.control, tag: control.tagName, type: control.type, disabled: control.disabled, options: control.tagName === 'SELECT' ? [...control.options].map((option) => ({value: option.value, label: option.textContent})) : []})))`,
      ),
    );
    const expectedControlNames = controlInventory
      .map((control) => control.name)
      .sort();
    const exercised = new Set();

    const resetShared = async () => {
      await page.evaluate(
        `document.querySelector('[data-action="reset"]').click()`,
      );
      await waitFor(
        page,
        `!document.querySelector('.loading').classList.contains('is-visible') && document.querySelector('[data-action="scope"]').textContent.includes('Filters · 0')`,
        "shared reset",
      );
    };

    const mutateShared = async ({
      name,
      mutation,
      expectedPath = name,
      expected,
    }) => {
      await resetShared();
      const before = await page.evaluate("window.__dashboardFetches.length");
      const selected = await page.evaluate(mutation);
      await waitFor(
        page,
        `window.__dashboardFetches.length > ${before} && window.__dashboardFetches.at(-1).done && !document.querySelector('.loading').classList.contains('is-visible')`,
        `${name} recomputation`,
      );
      const record = JSON.parse(
        await page.evaluate("JSON.stringify(window.__dashboardFetches.at(-1))"),
      );
      assert(
        record.status === 200 && record.url.includes("api/view"),
        `${name} did not complete a successful /api/view request`,
      );
      const body = JSON.parse(record.body);
      const actual = valueAt(body, expectedPath);
      const wanted = expected === undefined ? selected : expected;
      assert(
        String(actual) === String(wanted),
        `${name} request drifted: expected ${wanted}, got ${actual}`,
      );
      assert(
        await page.evaluate(
          `document.querySelector('[data-status]').textContent !== 'dashboard request failed'`,
        ),
        `${name} left the dashboard in an error state`,
      );
      assert(
        !(await page.evaluate(
          `document.querySelector('[data-action="scope"]').textContent.trim().endsWith('0')`,
        )),
        `${name} did not update the active-filter count`,
      );
      exercised.add(name);
      return { selected, requestValue: actual };
    };

    const simpleCases = [
      {
        name: "source",
        mutation: `(()=>{const c=document.querySelector('[data-control="source"]');c.value='ml';c.dispatchEvent(new Event('change',{bubbles:true}));return c.value})()`,
      },
      {
        name: "target_start",
        mutation: `(()=>{const c=document.querySelector('[data-control="target_start"]');c.selectedIndex=Math.min(1,c.options.length-1);c.dispatchEvent(new Event('change',{bubbles:true}));return c.value})()`,
      },
      {
        name: "target_end",
        mutation: `(()=>{const c=document.querySelector('[data-control="target_end"]');c.selectedIndex=Math.max(0,c.options.length-2);c.dispatchEvent(new Event('change',{bubbles:true}));return c.value})()`,
      },
      {
        name: "brand",
        mutation: `(()=>{const c=document.querySelector('[data-control="brand"]');c.selectedIndex=Math.min(1,c.options.length-1);c.dispatchEvent(new Event('change',{bubbles:true}));return c.value})()`,
      },
      {
        name: "parent_code",
        mutation: `(()=>{const c=document.querySelector('[data-control="parent_code"]');c.selectedIndex=Math.min(1,c.options.length-1);c.dispatchEvent(new Event('change',{bubbles:true}));return Number(c.value)})()`,
      },
      {
        name: "horizon",
        mutation: `(()=>{const c=document.querySelector('[data-control="horizon"]');c.selectedIndex=Math.min(1,c.options.length-1);c.dispatchEvent(new Event('change',{bubbles:true}));return Number(c.value)})()`,
      },
      {
        name: "minimum_actual_volume",
        mutation: `(()=>{const c=document.querySelector('[data-control="minimum_actual_volume"]');c.value='1';c.dispatchEvent(new Event('change',{bubbles:true}));return Number(c.value)})()`,
      },
      {
        name: "revision_direction",
        mutation: `(()=>{const c=document.querySelector('[data-control="revision_direction"]');c.value='up';c.dispatchEvent(new Event('change',{bubbles:true}));return c.value})()`,
      },
      {
        name: "revision_outcome",
        mutation: `(()=>{const c=document.querySelector('[data-control="revision_outcome"]');c.value='improved';c.dispatchEvent(new Event('change',{bubbles:true}));return c.value})()`,
      },
      {
        name: "revision_tolerance_kl",
        mutation: `(()=>{const c=document.querySelector('[data-control="revision_tolerance_kl"]');c.value='1';c.dispatchEvent(new Event('change',{bubbles:true}));return Number(c.value)})()`,
      },
      {
        name: "forecast_direction",
        mutation: `(()=>{const c=document.querySelector('[data-control="forecast_direction"]');c.value='over';c.dispatchEvent(new Event('change',{bubbles:true}));return c.value})()`,
      },
      {
        name: "accuracy_band",
        mutation: `(()=>{const c=document.querySelector('[data-control="accuracy_band"]');c.value='0_50';c.dispatchEvent(new Event('change',{bubbles:true}));return c.value})()`,
      },
      {
        name: "bias_band",
        mutation: `(()=>{const c=document.querySelector('[data-control="bias_band"]');c.value='0_50';c.dispatchEvent(new Event('change',{bubbles:true}));return c.value})()`,
      },
      {
        name: "minimum_absolute_error_kl",
        mutation: `(()=>{const c=document.querySelector('[data-control="minimum_absolute_error_kl"]');c.value='1';c.dispatchEvent(new Event('change',{bubbles:true}));return Number(c.value)})()`,
      },
      {
        name: "top_n",
        mutation: `(()=>{const c=document.querySelector('[data-control="top_n"]');c.value='10';c.dispatchEvent(new Event('change',{bubbles:true}));return Number(c.value)})()`,
      },
      {
        name: "top_n_metric",
        mutation: `(()=>{const c=document.querySelector('[data-control="top_n_metric"]');c.value='absolute_error';c.dispatchEvent(new Event('change',{bubbles:true}));return c.value})()`,
      },
      {
        name: "hierarchy_status",
        mutation: `(()=>{const c=document.querySelector('[data-control="hierarchy_status"]');c.value='mapped';c.dispatchEvent(new Event('change',{bubbles:true}));return c.value})()`,
      },
      {
        name: "actual_status",
        mutation: `(()=>{const c=document.querySelector('[data-control="actual_status"]');c.value='matched_positive';c.dispatchEvent(new Event('change',{bubbles:true}));return c.value})()`,
      },
      {
        name: "pair_status",
        mutation: `(()=>{const c=document.querySelector('[data-control="pair_status"]');c.value='complete';c.dispatchEvent(new Event('change',{bubbles:true}));return c.value})()`,
      },
      {
        name: "source_availability",
        mutation: `(()=>{const c=document.querySelector('[data-control="source_availability"]');c.value='tm_only';c.dispatchEvent(new Event('change',{bubbles:true}));return c.value})()`,
      },
      {
        name: "zero_forecast_only",
        mutation: `(()=>{const c=document.querySelector('[data-control="zero_forecast_only"]');c.click();return c.checked})()`,
      },
      {
        name: "complete_vintage_history_only",
        mutation: `(()=>{const c=document.querySelector('[data-control="complete_vintage_history_only"]');c.click();return c.checked})()`,
      },
    ];

    for (const testCase of simpleCases)
      await check(`shared control · ${testCase.name}`, () =>
        mutateShared(testCase),
      );

    await check(
      "shared control · comparison_mode and disabled groups",
      async () => {
        const detail = await mutateShared({
          name: "comparison_mode",
          mutation: `(()=>{const c=document.querySelector('[data-control="comparison_mode"]');c.value='true';c.dispatchEvent(new Event('change',{bubbles:true}));return true})()`,
        });
        const disabled = JSON.parse(
          await page.evaluate(
            `JSON.stringify({source:document.querySelector('[data-control="source"]').disabled,vintage:document.querySelector('[data-vintage-group]').disabled,performance:document.querySelector('[data-performance-group]').disabled,horizon:document.querySelector('[data-control="horizon"]').value})`,
          ),
        );
        assert(
          disabled.source &&
            disabled.vintage &&
            disabled.performance &&
            disabled.horizon !== "",
          "Comparison mode did not enforce its control contract",
        );
        return { ...detail, disabled };
      },
    );

    for (const prefix of ["vintage_a", "vintage_b"]) {
      await check(`shared control · ${prefix}_kind`, async () => {
        const detail = await mutateShared({
          name: `${prefix}_kind`,
          expectedPath: `${prefix}.kind`,
          mutation: `(()=>{const c=document.querySelector('[data-control="${prefix}_kind"]');c.value='specific_horizon';c.dispatchEvent(new Event('change',{bubbles:true}));return c.value})()`,
        });
        exercised.add(`${prefix}_value`);
        return detail;
      });
      await check(`shared control · ${prefix}_value`, async () => {
        await resetShared();
        const kind = `${prefix}_kind`;
        let before = await page.evaluate("window.__dashboardFetches.length");
        await page.evaluate(
          `(()=>{const c=document.querySelector('[data-control="${kind}"]');c.value='specific_horizon';c.dispatchEvent(new Event('change',{bubbles:true}))})()`,
        );
        await waitFor(
          page,
          `window.__dashboardFetches.length > ${before} && window.__dashboardFetches.at(-1).done && !document.querySelector('.loading').classList.contains('is-visible')`,
          `${kind} setup`,
        );
        before = await page.evaluate("window.__dashboardFetches.length");
        const selected = await page.evaluate(
          `(()=>{const c=document.querySelector('[data-control="${prefix}_value"]');c.selectedIndex=c.options.length-1;c.dispatchEvent(new Event('change',{bubbles:true}));return Number(c.value)})()`,
        );
        await waitFor(
          page,
          `window.__dashboardFetches.length > ${before} && window.__dashboardFetches.at(-1).done && !document.querySelector('.loading').classList.contains('is-visible')`,
          `${prefix}_value recomputation`,
        );
        const record = JSON.parse(
          await page.evaluate(
            "JSON.stringify(window.__dashboardFetches.at(-1))",
          ),
        );
        assert(record.status === 200, `${prefix}_value request failed`);
        const body = JSON.parse(record.body);
        assert(
          body[prefix].kind === "specific_horizon" &&
            Number(body[prefix].value) === selected,
          `${prefix}_value was not submitted`,
        );
        exercised.add(`${prefix}_value`);
        return { selected };
      });
    }

    await check("all shared controls exercised", () => {
      const missing = expectedControlNames.filter(
        (name) => !exercised.has(name),
      );
      assert(
        missing.length === 0,
        `Unexercised shared controls: ${missing.join(", ")}`,
      );
      return { count: expectedControlNames.length };
    });

    await check("filter drawer toggle and Escape", async () => {
      await resetShared();
      await page.evaluate(
        `document.querySelector('[data-action="scope"]').click()`,
      );
      assert(
        await page.evaluate(
          `!document.querySelector('#scope-drawer').hidden && document.querySelector('[data-action="scope"]').getAttribute('aria-expanded') === 'true'`,
        ),
        "Filter drawer did not open",
      );
      await page.evaluate(
        `document.querySelector('[data-action="scope"]').click()`,
      );
      assert(
        await page.evaluate(
          `document.querySelector('#scope-drawer').hidden && document.querySelector('[data-action="scope"]').getAttribute('aria-expanded') === 'false'`,
        ),
        "Filter drawer did not close from its toggle",
      );
      await page.evaluate(
        `document.querySelector('[data-action="scope"]').click()`,
      );
      await page.evaluate(
        `document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))`,
      );
      assert(
        await page.evaluate(
          `document.querySelector('#scope-drawer').hidden && document.activeElement === document.querySelector('[data-action="scope"]')`,
        ),
        "Escape did not close and return focus to Filters",
      );
    });

    await check(
      "primary tabs, keyboard navigation, and hash history",
      async () => {
        await page.evaluate(
          `document.querySelector('[data-target="overview"]').click()`,
        );
        const beforeLength = await page.evaluate("history.length");
        for (const tab of TABS) {
          await page.evaluate(
            `document.querySelector('[data-target="${tab}"]').click()`,
          );
          assert(
            await page.evaluate(
              `location.hash === '#${tab}' && document.querySelector('#pane-${tab}').classList.contains('is-active')`,
            ),
            `${tab} click did not activate its pane`,
          );
        }
        const afterLength = await page.evaluate("history.length");
        assert(
          afterLength >= beforeLength + TABS.length - 1,
          "Tab visits were not added to browser history",
        );
        await page.evaluate(
          `document.querySelector('[data-target="overview"]').focus();document.querySelector('[role="tablist"]').dispatchEvent(new KeyboardEvent('keydown',{key:'End',bubbles:true}))`,
        );
        assert(
          await page.evaluate(
            `document.activeElement.dataset.target === 'quality' && location.hash === '#quality'`,
          ),
          "End key did not reach Data quality",
        );
        await page.evaluate(
          `document.querySelector('[role="tablist"]').dispatchEvent(new KeyboardEvent('keydown',{key:'Home',bubbles:true}))`,
        );
        assert(
          await page.evaluate(
            `document.activeElement.dataset.target === 'overview' && location.hash === '#overview'`,
          ),
          "Home key did not reach Overview",
        );
        await page.evaluate(
          `document.querySelector('[role="tablist"]').dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowDown',bubbles:true}))`,
        );
        assert(
          await page.evaluate(
            `document.activeElement.dataset.target === 'trends'`,
          ),
          "ArrowDown did not advance tabs",
        );
        await page.evaluate("history.back()");
        await waitFor(
          page,
          `location.hash === '#overview'`,
          "browser Back tab restoration",
        );
        await page.evaluate("history.forward()");
        await waitFor(
          page,
          `location.hash === '#trends'`,
          "browser Forward tab restoration",
        );
        return { beforeLength, afterLength };
      },
    );

    await check("every subview toggle", async () => {
      const groups = {
        comparison: ["revision", "sources"],
        history: ["product", "exceptions"],
        quality: ["hierarchy", "actual", "pairs", "source_availability"],
      };
      for (const [group, targets] of Object.entries(groups)) {
        for (const target of targets) {
          await page.evaluate(
            `document.querySelector('[data-subtabs="${group}"] [data-subtab-target="${target}"]').click()`,
          );
          assert(
            await page.evaluate(
              `!document.querySelector('[data-subpanel="${group}:${target}"]').hidden && document.querySelector('[data-subtabs="${group}"] [data-subtab-target="${target}"]').getAttribute('aria-pressed') === 'true'`,
            ),
            `${group}:${target} did not activate`,
          );
        }
      }
    });

    await check("all trend metric options render", async () => {
      await page.evaluate(
        `document.querySelector('[data-target="trends"]').click()`,
      );
      const selectors = ["monthly", "horizon", "heatmap"];
      const results = {};
      for (const selector of selectors) {
        const values = JSON.parse(
          await page.evaluate(
            `JSON.stringify([...document.querySelector('[data-metric-selector="${selector}"]').options].map(o=>o.value))`,
          ),
        );
        results[selector] = [];
        for (const value of values) {
          const render = await page.evaluate(
            `(()=>{const c=document.querySelector('[data-metric-selector="${selector}"]');c.value='${value}';c.dispatchEvent(new Event('change',{bubbles:true}));const target='${selector}'==='monthly'?document.querySelector('[data-trend-chart]'):'${selector}'==='horizon'?document.querySelector('[data-horizon-bars]'):document.querySelector('[data-heatmap]');return {value:c.value,content:target.textContent.trim().length+target.querySelectorAll('*').length}})()`,
          );
          assert(
            render.value === value && render.content > 0,
            `${selector}:${value} did not render`,
          );
          results[selector].push(value);
        }
      }
      return results;
    });

    await check("horizon bars have visible geometry", async () => {
      await page.evaluate(
        `document.querySelector('[data-target="trends"]').click()`,
      );
      const widths = JSON.parse(
        await page.evaluate(
          `JSON.stringify([...document.querySelectorAll('.dual-row i')].map(i=>({before:parseFloat(getComputedStyle(i,'::before').width),after:parseFloat(getComputedStyle(i,'::after').width)})))`,
        ),
      );
      assert(
        widths.some((row) => row.before > 0 || row.after > 0),
        "Every horizon bar has zero computed width",
      );
      return widths;
    });

    await check("product parent and target-month drill-down", async () => {
      await resetShared();
      await page.evaluate(
        `document.querySelector('[data-target="history"]').click()`,
      );
      const parent = await page.evaluate(
        `(()=>{const c=document.querySelector('[data-product-control="parent"]');c.selectedIndex=Math.min(1,c.options.length-1);c.dispatchEvent(new Event('change',{bubbles:true}));return c.value})()`,
      );
      await waitFor(
        page,
        `!document.querySelector('.loading').classList.contains('is-visible') && document.querySelector('[data-product-summary]').textContent.includes('${parent}')`,
        "product parent drill-down",
      );
      const month = await page.evaluate(
        `(()=>{const c=document.querySelector('[data-product-control="month"]');c.selectedIndex=Math.max(0,c.options.length-1);c.dispatchEvent(new Event('change',{bubbles:true}));return c.value})()`,
      );
      await waitFor(
        page,
        `!document.querySelector('.loading').classList.contains('is-visible') && document.querySelector('[data-product-control="month"]').value === '${month}'`,
        "product target-month drill-down",
      );
      assert(
        await page.evaluate(
          `document.querySelectorAll('[data-history-chart] circle').length > 0 && document.querySelectorAll('[data-stability] article').length > 0`,
        ),
        "Product detail did not render chart and stability",
      );
      return { parent, month };
    });

    await check("exception search and row limits", async () => {
      await page.evaluate(
        `document.querySelector('[data-subtabs="history"] [data-subtab-target="exceptions"]').click()`,
      );
      const product = await page.evaluate(
        `document.querySelector('.audit-table__row strong')?.textContent.trim()`,
      );
      assert(product, "No exception product available for search");
      await page.evaluate(
        `(()=>{const c=document.querySelector('[data-exception-search]');c.value='${product}';c.dispatchEvent(new Event('input',{bubbles:true}))})()`,
      );
      const searched = await page.evaluate(
        `document.querySelectorAll('.audit-table__row').length`,
      );
      assert(searched >= 1, "Exception search returned no matching row");
      for (const limit of ["10", "20", "80"]) {
        await page.evaluate(
          `(()=>{const c=document.querySelector('[data-exception-search]');c.value='';c.dispatchEvent(new Event('input',{bubbles:true}));const l=document.querySelector('[data-exception-limit]');l.value='${limit}';l.dispatchEvent(new Event('change',{bubbles:true}))})()`,
        );
        const count = await page.evaluate(
          `document.querySelectorAll('.audit-table__row').length`,
        );
        assert(
          count <= Number(limit),
          `Exception limit ${limit} rendered ${count} rows`,
        );
      }
      return { product, searched };
    });

    await check("dynamic comparison mode action buttons", async () => {
      await resetShared();
      await page.evaluate(
        `document.querySelector('[data-target="comparison"]').click();document.querySelector('[data-subtabs="comparison"] [data-subtab-target="sources"]').click()`,
      );
      assert(
        await page.evaluate(
          `!!document.querySelector('[data-mode-action="comparison"]')`,
        ),
        "Enable comparison action button is missing",
      );
      let before = await page.evaluate("window.__dashboardFetches.length");
      await page.evaluate(
        `document.querySelector('[data-mode-action="comparison"]').click()`,
      );
      await waitFor(
        page,
        `window.__dashboardFetches.length > ${before} && window.__dashboardFetches.at(-1).done && !document.querySelector('.loading').classList.contains('is-visible') && document.querySelector('[data-control="comparison_mode"]').value === 'true'`,
        "Enable comparison action",
      );
      await page.evaluate(
        `document.querySelector('[data-subtabs="comparison"] [data-subtab-target="revision"]').click()`,
      );
      assert(
        await page.evaluate(
          `!!document.querySelector('[data-mode-action="single"]')`,
        ),
        "Use single-source action button is missing",
      );
      before = await page.evaluate("window.__dashboardFetches.length");
      await page.evaluate(
        `document.querySelector('[data-mode-action="single"]').click()`,
      );
      await waitFor(
        page,
        `window.__dashboardFetches.length > ${before} && window.__dashboardFetches.at(-1).done && !document.querySelector('.loading').classList.contains('is-visible') && document.querySelector('[data-control="comparison_mode"]').value === 'false'`,
        "Use single-source action",
      );
    });

    await check("all CSV export buttons download", async () => {
      await resetShared();
      await page.evaluate(
        `document.querySelector('[data-target="history"]').click();document.querySelector('[data-subtabs="history"] [data-subtab-target="exceptions"]').click();document.querySelector('[data-export-kind="vintages"]').click()`,
      );
      await waitFor(
        page,
        `!document.querySelector('.loading').classList.contains('is-visible')`,
        "vintage export",
      );
      await page.evaluate(
        `document.querySelector('[data-target="quality"]').click()`,
      );
      for (const category of [
        "hierarchy",
        "actual",
        "pairs",
        "source_availability",
      ]) {
        await page.evaluate(
          `document.querySelector('[data-subtabs="quality"] [data-subtab-target="${category}"]').click();document.querySelector('[data-subpanel="quality:${category}"] [data-export-kind="quality"]').click()`,
        );
        await waitFor(
          page,
          `!document.querySelector('.loading').classList.contains('is-visible')`,
          `${category} export`,
        );
      }
      await page.evaluate(`document.querySelector('.baseline').open=true`);
      const hasScopeExport = await page.evaluate(
        `!!document.querySelector('[data-baseline] [data-export-kind="scope_exclusions"]')`,
      );
      if (hasScopeExport) {
        await page.evaluate(
          `document.querySelector('[data-baseline] [data-export-kind="scope_exclusions"]').click()`,
        );
        await waitFor(
          page,
          `!document.querySelector('.loading').classList.contains('is-visible')`,
          "scope exclusions export",
        );
      }
      const expectedDownloads = hasScopeExport ? 6 : 5;
      const deadline = Date.now() + 30_000;
      while (
        Date.now() < deadline &&
        readdirSync(downloadDir).filter((name) => name.endsWith(".csv"))
          .length < expectedDownloads
      )
        await sleep(150);
      const files = readdirSync(downloadDir).filter((name) =>
        name.endsWith(".csv"),
      );
      assert(
        files.some((name) => name.includes("filtered_vintages")),
        "Filtered vintages CSV is missing",
      );
      for (const category of [
        "hierarchy",
        "actual",
        "pairs",
        "source_availability",
      ])
        assert(
          files.some((name) => name.includes(`${category}_exceptions`)),
          `${category} quality CSV is missing`,
        );
      if (hasScopeExport)
        assert(
          files.some((name) => name.includes("scope_exclusions")),
          "Scope exclusions CSV is missing",
        );
      return { files, scopeExportAvailable: hasScopeExport };
    });

    await check("baseline details toggle", async () => {
      await page.evaluate(
        `document.querySelector('[data-target="quality"]').click();document.querySelector('.baseline').open=false;document.querySelector('.baseline summary').click()`,
      );
      assert(
        await page.evaluate(`document.querySelector('.baseline').open`),
        "Baseline details did not open",
      );
      await page.evaluate(
        `document.querySelector('.baseline summary').click()`,
      );
      assert(
        !(await page.evaluate(`document.querySelector('.baseline').open`)),
        "Baseline details did not close",
      );
    });

    await check("Reset restores local and shared UI state", async () => {
      await page.evaluate(
        `(()=>{const m=document.querySelector('[data-metric-selector="monthly"]');m.value='bias_pct';m.dispatchEvent(new Event('change',{bubbles:true}));const s=document.querySelector('[data-exception-search]');s.value='stale';s.dispatchEvent(new Event('input',{bubbles:true}));const l=document.querySelector('[data-exception-limit]');l.value='80';l.dispatchEvent(new Event('change',{bubbles:true}));const source=document.querySelector('[data-control="source"]');source.value='ml';source.dispatchEvent(new Event('change',{bubbles:true}))})()`,
      );
      await waitFor(
        page,
        `!document.querySelector('.loading').classList.contains('is-visible')`,
        "pre-reset change",
      );
      await page.evaluate(
        `document.querySelector('[data-action="reset"]').click()`,
      );
      await waitFor(
        page,
        `!document.querySelector('.loading').classList.contains('is-visible')`,
        "complete reset",
      );
      const state = JSON.parse(
        await page.evaluate(
          `JSON.stringify({monthly:document.querySelector('[data-metric-selector="monthly"]').value,search:document.querySelector('[data-exception-search]').value,limit:document.querySelector('[data-exception-limit]').value,source:document.querySelector('[data-control="source"]').value,tab:document.querySelector('.rail [aria-selected="true"]').dataset.target})`,
        ),
      );
      assert(
        state.monthly === "forecast_accuracy_pct" &&
          state.search === "" &&
          state.limit === "10" &&
          state.source === "tm" &&
          state.tab === "overview",
        `Reset left stale state: ${JSON.stringify(state)}`,
      );
      return state;
    });

    await check("collapsible navigation rail", async () => {
      await page.viewport(1440, 900);
      const initial = JSON.parse(
        await page.evaluate(
          `JSON.stringify({button:!!document.querySelector('[data-action="rail"]'),rail:document.querySelector('.rail').getBoundingClientRect().width,workspace:document.querySelector('.workspace').getBoundingClientRect().width})`,
        ),
      );
      assert(initial.button, "Navigation collapse button is missing");
      await page.evaluate(
        `document.querySelector('[data-action="rail"]').click()`,
      );
      await sleep(260);
      const collapsed = JSON.parse(
        await page.evaluate(
          `JSON.stringify({rail:document.querySelector('.rail').getBoundingClientRect().width,workspace:document.querySelector('.workspace').getBoundingClientRect().width,names:getComputedStyle(document.querySelector('.tab__name')).display,expanded:document.querySelector('[data-action="rail"]').getAttribute('aria-expanded'),label:document.querySelector('[data-action="rail"]').getAttribute('aria-label'),overflowX:document.documentElement.scrollWidth-innerWidth})`,
        ),
      );
      assert(
        collapsed.rail < initial.rail &&
          collapsed.workspace > initial.workspace,
        "Collapsed rail did not release workspace width",
      );
      assert(
        collapsed.names === "none" &&
          collapsed.expanded === "false" &&
          /expand/i.test(collapsed.label) &&
          collapsed.overflowX === 0,
        "Collapsed rail accessibility/layout contract failed",
      );
      assert(
        await page.evaluate(
          `localStorage.getItem('forecast-dashboard:rail-collapsed') === 'true'`,
        ),
        "Collapsed rail preference was not persisted",
      );
      for (const tab of TABS) {
        await page.evaluate(
          `document.querySelector('[data-target="${tab}"]').click()`,
        );
        assert(
          await page.evaluate(
            `document.querySelector('#pane-${tab}').classList.contains('is-active')`,
          ),
          `${tab} failed while rail was collapsed`,
        );
      }
      await page.evaluate(
        `document.querySelector('[data-action="rail"]').click()`,
      );
      await sleep(260);
      assert(
        await page.evaluate(
          `document.querySelector('.rail').getBoundingClientRect().width > ${collapsed.rail} && document.querySelector('[data-action="rail"]').getAttribute('aria-expanded') === 'true' && localStorage.getItem('forecast-dashboard:rail-collapsed') === 'false'`,
        ),
        "Rail did not expand again or persist its expanded state",
      );
      return { initial, collapsed };
    });

    const screenshots = [];
    const capture = async (name, label) => {
      const path = join(args.output, name);
      await page.screenshot(path);
      screenshots.push({ name, label, sha256: sha256(path) });
    };

    await check("zoom and responsive fixed-viewport states", async () => {
      await page.evaluate(
        `document.querySelector('[data-target="overview"]').click()`,
      );
      for (const scale of [1, 1.25, 1.5, 2]) {
        await page.send("Emulation.setPageScaleFactor", {
          pageScaleFactor: scale,
        });
        const layout = JSON.parse(
          await page.evaluate(
            `JSON.stringify({scale:visualViewport.scale,pageVertical:document.documentElement.scrollHeight-innerHeight,pageHorizontal:document.documentElement.scrollWidth-innerWidth,active:document.querySelector('.stage>.pane.is-active').getBoundingClientRect().toJSON()})`,
          ),
        );
        assert(
          layout.pageVertical === 0 && layout.pageHorizontal === 0,
          `Page scroll appeared at ${scale}× zoom`,
        );
      }
      await page.send("Emulation.setPageScaleFactor", { pageScaleFactor: 1 });
      await capture("desktop-expanded.png", "Desktop · expanded rail");
      await page.evaluate(
        `document.querySelector('[data-action="rail"]').click()`,
      );
      await sleep(260);
      await capture("desktop-collapsed.png", "Desktop · collapsed rail");
      await page.viewport(800, 700);
      const narrow = JSON.parse(
        await page.evaluate(
          `JSON.stringify({rail:document.querySelector('.rail').getBoundingClientRect().width,pageVertical:document.documentElement.scrollHeight-innerHeight,pageHorizontal:document.documentElement.scrollWidth-innerWidth,names:getComputedStyle(document.querySelector('.tab__name')).display})`,
        ),
      );
      assert(
        narrow.pageVertical === 0 &&
          narrow.pageHorizontal === 0 &&
          narrow.names === "none",
        "Narrow collapsed layout overflowed or exposed labels",
      );
      await capture("narrow-collapsed.png", "Narrow · collapsed rail");
      await page.evaluate(
        `document.querySelector('[data-action="rail"]').click()`,
      );
      await sleep(260);
      await capture("narrow-expanded.png", "Narrow · responsive rail");
      return narrow;
    });

    await check("all buttons classified and operable", async () => {
      const buttons = JSON.parse(
        await page.evaluate(
          `JSON.stringify([...document.querySelectorAll('button')].map((button)=>({text:button.textContent.trim(),action:button.dataset.action||null,target:button.dataset.target||null,subtab:button.dataset.subtabTarget||null,exportKind:button.dataset.exportKind||null,modeAction:button.dataset.modeAction||null,disabled:button.disabled})))`,
        ),
      );
      const unclassified = buttons.filter(
        (button) =>
          !button.action &&
          !button.target &&
          !button.subtab &&
          !button.exportKind &&
          !button.modeAction,
      );
      assert(
        unclassified.length === 0,
        `Unclassified buttons: ${JSON.stringify(unclassified)}`,
      );
      assert(
        buttons.every((button) => !button.disabled),
        "Unexpected disabled button detected",
      );
      return { count: buttons.length };
    });

    await check("no console, page, network, or HTTP failures", () => {
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
    });

    const report = {
      generatedAt: new Date().toISOString(),
      baseUrl,
      checks,
      failures,
      controlInventory,
      screenshots,
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
      `# Exhaustive dashboard functionality validation\n\n- Result: ${failures.length ? "FAIL" : "PASS"}\n- Generated: ${report.generatedAt}\n- Checks: ${checks.filter((item) => item.status === "pass").length} passed / ${checks.length}\n- Shared controls exercised: ${exercised.size} / ${expectedControlNames.length}\n- Screenshots: ${screenshots.length}\n- Failures: ${failures.length ? failures.map((failure) => `\n  - ${failure}`).join("") : "none"}\n`,
    );
    writeFileSync(join(args.output, "index.html"), gallery(report));
    rmSync(downloadDir, { recursive: true, force: true });
    if (failures.length)
      throw new Error(
        `Exhaustive validation found ${failures.length} failure(s):\n${failures.join("\n")}`,
      );
    process.stdout.write(
      "EXHAUSTIVE DASHBOARD FUNCTIONALITY VALIDATION PASSED\n",
    );
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
