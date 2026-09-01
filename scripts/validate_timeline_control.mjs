#!/usr/bin/env node

import { spawn, spawnSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { get as httpGet } from "node:http";
import { createServer } from "node:net";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { setTimeout as sleep } from "node:timers/promises";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const args = {
  output: resolve(ROOT, "validation-artifacts/timeline-planner"),
  screenshotsOnly: false,
};
for (let index = 2; index < process.argv.length; index += 1) {
  if (process.argv[index] === "--output")
    args.output = resolve(ROOT, process.argv[++index]);
  else if (process.argv[index] === "--screenshots-only")
    args.screenshotsOnly = true;
  else throw new Error(`Unknown argument: ${process.argv[index]}`);
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
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      server.close(() => resolvePort(address.port));
    });
  });
}

async function waitForUrl(url, timeout = 75_000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    try {
      const status = await new Promise((resolveStatus, reject) => {
        const request = httpGet(url, (response) => {
          response.resume();
          response.once("end", () => resolveStatus(response.statusCode || 0));
        });
        request.once("error", reject);
      });
      if (status >= 200 && status < 300) return;
    } catch {}
    await sleep(200);
  }
  throw new Error(`Timed out waiting for ${url}`);
}

class Page {
  constructor(url) {
    this.socket = new WebSocket(url);
    this.pending = new Map();
    this.nextId = 0;
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
      } else if (
        message.method === "Runtime.consoleAPICalled" &&
        ["error", "warning"].includes(message.params.type)
      ) {
        this.errors.push(
          message.params.args
            .map((arg) => arg.value ?? arg.description ?? "")
            .join(" "),
        );
      } else if (
        message.method === "Network.loadingFailed" &&
        !message.params.canceled
      ) {
        this.errors.push(message.params.errorText);
      } else if (
        message.method === "Network.responseReceived" &&
        message.params.response.status >= 400
      ) {
        this.errors.push(
          `${message.params.response.status} ${message.params.response.url}`,
        );
      }
    };
    await this.send("Page.enable");
    await this.send("Runtime.enable");
    await this.send("Network.enable");
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
    if (result.exceptionDetails)
      throw new Error(
        result.exceptionDetails.exception?.description ||
          result.exceptionDetails.text,
      );
    return result.result?.value;
  }
  viewport(width, height) {
    return this.send("Emulation.setDeviceMetricsOverride", {
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

async function createPage(port) {
  const response = await fetch(
    `http://127.0.0.1:${port}/json/new?about:blank`,
    { method: "PUT" },
  );
  const target = await response.json();
  const page = new Page(target.webSocketDebuggerUrl);
  await page.connect();
  return page;
}

async function waitFor(page, expression, label, timeout = 30_000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (await page.evaluate(expression)) return;
    await sleep(100);
  }
  throw new Error(`Timed out waiting for ${label}`);
}

for (const command of ["uv", "chromium"])
  assert(commandExists(command), `Required command missing: ${command}`);
if (!args.screenshotsOnly)
  rmSync(args.output, { recursive: true, force: true });
mkdirSync(args.output, { recursive: true });
const serverPort = await freePort();
const debugPort = await freePort();
const profile = join("/tmp", `forecast-timeline-${randomUUID()}`);
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
    `--user-data-dir=${profile}`,
    "about:blank",
  ],
  { stdio: ["ignore", "ignore", "pipe"] },
);
let page;
try {
  const baseUrl = `http://127.0.0.1:${serverPort}/`;
  await waitForUrl(`${baseUrl}api/health`);
  await waitForUrl(`http://127.0.0.1:${debugPort}/json/version`, 20_000);
  page = await createPage(debugPort);
  await page.viewport(1440, 900);
  await page.send("Page.navigate", { url: baseUrl });
  await waitFor(
    page,
    `document.querySelector('[data-status]')?.textContent.includes('canonical dataset ready')`,
    "dashboard bootstrap",
    75_000,
  );
  await page.evaluate(
    `document.querySelector('[data-action="scope"]').click()`,
  );
  await waitFor(
    page,
    `!document.querySelector('#scope-drawer').hidden`,
    "open filter pane",
  );

  const screenshots = [];
  for (const viewport of [
    { name: "desktop", width: 1440, height: 900 },
    { name: "wide", width: 1680, height: 1000 },
    { name: "compact", width: 800, height: 700 },
  ]) {
    await page.viewport(viewport.width, viewport.height);
    await sleep(150);
    const geometry = await page.evaluate(`(() => {
      const timeline = document.querySelector('[data-timeline-control]');
      const drawer = document.querySelector('#scope-drawer');
      const buttons = [...timeline.querySelectorAll('button')];
      const rect = timeline.getBoundingClientRect();
      return {
        visible: rect.width > 0 && rect.height > 0,
        timelineOverflow: timeline.scrollWidth - timeline.clientWidth,
        drawerOverflow: drawer.scrollWidth - drawer.clientWidth,
        buttonsVisible: buttons.every((button) => { const r = button.getBoundingClientRect(); return r.width > 0 && r.height > 0; }),
        clippedRight: rect.right > innerWidth + 1,
        clippedLeft: rect.left < -1,
      };
    })()`);
    assert(
      geometry.visible && geometry.buttonsVisible,
      `${viewport.name}: timeline controls are not visible`,
    );
    assert(
      geometry.timelineOverflow <= 1 && geometry.drawerOverflow <= 1,
      `${viewport.name}: horizontal overflow detected`,
    );
    assert(
      !geometry.clippedLeft && !geometry.clippedRight,
      `${viewport.name}: timeline is clipped`,
    );
    const name = `${viewport.name}-filter-timeline.png`;
    await page.screenshot(join(args.output, name));
    screenshots.push({ ...viewport, name, geometry });
  }

  if (!args.screenshotsOnly) {
    await page.viewport(1440, 900);
    await page.evaluate(`(() => {
      window.__timelineRequests = [];
      const original = window.fetch.bind(window);
      window.fetch = async (...fetchArgs) => {
        const body = fetchArgs[1]?.body;
        if (body && String(fetchArgs[0]).includes('api/view/compact')) window.__timelineRequests.push(JSON.parse(body));
        return original(...fetchArgs);
      };
    })()`);
    const requestCount = () => `window.__timelineRequests.length`;
    let before = await page.evaluate(requestCount());
    await page.evaluate(
      `document.querySelector('[data-timeline-months="6"]').click()`,
    );
    await waitFor(page, `${requestCount()} > ${before}`, "6M request");
    let request = await page.evaluate(`window.__timelineRequests.at(-1)`);
    assert(
      await page.evaluate(
        `ForecastTimeline.inclusiveMonthCount('${request.target_start}', '${request.target_end}') === 6`,
      ),
      "6M preset did not produce six inclusive months",
    );
    await page.screenshot(join(args.output, "desktop-6m-selected.png"));
    screenshots.push({
      name: "desktop-6m-selected.png",
      width: 1440,
      height: 900,
      state: "6M selected",
    });
    await page.evaluate(`document.querySelector('[data-control="source"]').focus()`);
    for (let index = 0; index < 5; index += 1) {
      await page.send("Input.dispatchKeyEvent", { type: "keyDown", key: "Tab", code: "Tab", windowsVirtualKeyCode: 9 });
      await page.send("Input.dispatchKeyEvent", { type: "keyUp", key: "Tab", code: "Tab", windowsVirtualKeyCode: 9 });
    }
    await page.screenshot(join(args.output, "desktop-keyboard-focus.png"));
    screenshots.push({
      name: "desktop-keyboard-focus.png",
      width: 1440,
      height: 900,
      state: "Keyboard focus visible",
    });

    const sliderState = await page.evaluate(`(() => ({
      startDisabled: document.querySelector('[data-timeline-start-slider]').disabled,
      endDisabled: document.querySelector('[data-timeline-end-slider]').disabled,
      start: Number(document.querySelector('[data-timeline-start-slider]').value),
      end: Number(document.querySelector('[data-timeline-end-slider]').value),
      selectionWidth: document.querySelector('[data-timeline-selection]').getBoundingClientRect().width,
    }))()`);
    assert(!sliderState.startDisabled && !sliderState.endDisabled, "Both range handles must always remain active");
    assert(sliderState.end - sliderState.start === 5, "6M preset did not reposition both slider ends");
    assert(sliderState.selectionWidth > 0, "Selected range track is not visible");

    before = await page.evaluate(requestCount());
    await page.evaluate(`(() => {
      const slider = document.querySelector('[data-timeline-start-slider]');
      slider.value = Number(slider.value) + 1;
      slider.dispatchEvent(new Event('input', {bubbles:true}));
      slider.dispatchEvent(new Event('change', {bubbles:true}));
    })()`);
    await waitFor(page, `${requestCount()} > ${before}`, "manual start-handle request");
    const shifted = await page.evaluate(`window.__timelineRequests.at(-1)`);
    assert(shifted.target_start > request.target_start && shifted.target_end === request.target_end, "Start handle did not independently update the range");
    assert(await page.evaluate(`![...document.querySelectorAll('[data-timeline-months]')].some((button) => button.classList.contains('is-active'))`), "Manual unmatched range should clear preset selection");

    before = await page.evaluate(requestCount());
    await page.evaluate(
      `document.querySelector('[data-timeline-grain="quarter"]').click(); document.querySelector('[data-timeline-months="12"]').click()`,
    );
    await waitFor(page, `${requestCount()} > ${before}`, "4Q request");
    request = await page.evaluate(`window.__timelineRequests.at(-1)`);
    assert(
      [3, 6, 9, 12].includes(Number(request.target_end.slice(5, 7))),
      "Quarter horizon did not end on a calendar-quarter boundary",
    );
    await page.screenshot(join(args.output, "desktop-quarter-selected.png"));
    screenshots.push({
      name: "desktop-quarter-selected.png",
      width: 1440,
      height: 900,
      state: "Quarter and 4Q selected",
    });

    before = await page.evaluate(requestCount());
    await page.evaluate(`(() => {
      const start = document.querySelector('[data-timeline-start-slider]');
      start.value = Number(start.value) + 1;
      start.dispatchEvent(new Event('input', {bubbles:true}));
      start.dispatchEvent(new Event('change', {bubbles:true}));
    })()`);
    await waitFor(page, `${requestCount()} > ${before}`, "partial-quarter monthly request");
    request = await page.evaluate(`window.__timelineRequests.at(-1)`);
    assert(![1, 4, 7, 10].includes(Number(request.target_start.slice(5, 7))), "Quarter view incorrectly forced manual movement to a quarter boundary");
    assert(await page.evaluate(`document.querySelector('[data-timeline-hint]').textContent.includes('Monthly precision retained')`), "Partial-quarter context is not explained");

    const semantics = await page.evaluate(`(() => ({
      grainPressed: document.querySelector('[data-timeline-grain="quarter"]').getAttribute('aria-pressed'),
      startLabel: document.querySelector('[data-timeline-start-slider]').getAttribute('aria-label'),
      endLabel: document.querySelector('[data-timeline-end-slider]').getAttribute('aria-label'),
      windowLabel: document.querySelector('[data-timeline-selection]').getAttribute('aria-label'),
      nativeButtons: [...document.querySelectorAll('[data-timeline-control] button')].every((button) => button.type === 'button'),
      dateFieldsVisible: [...document.querySelectorAll('[data-timeline-custom-fields] .compact-field')].every((field) => field.getBoundingClientRect().height > 0),
    }))()`);
    assert(
      semantics.grainPressed === "true",
      "Quarter selected state is not exposed",
    );
    assert(semantics.startLabel === "Start month" && semantics.endLabel === "End month" && semantics.windowLabel?.includes("Move selected"), "Dual-slider accessible labels are incomplete");
    assert(semantics.nativeButtons && semantics.dateFieldsVisible, "Timeline semantics are incomplete");
    before = await page.evaluate(requestCount());
    const exactRange = await page.evaluate(`(() => {
      const start = document.querySelector('[data-control="target_start"]');
      const end = document.querySelector('[data-control="target_end"]');
      start.value = start.options[Math.min(2, start.options.length - 1)].value;
      end.value = end.options[Math.min(5, end.options.length - 1)].value;
      start.dispatchEvent(new Event('change', {bubbles:true}));
      end.dispatchEvent(new Event('change', {bubbles:true}));
      return {start: start.value, end: end.value};
    })()`);
    await waitFor(
      page,
      `${requestCount()} > ${before}`,
      "custom exact-period request",
    );
    request = await page.evaluate(`window.__timelineRequests.at(-1)`);
    assert(
      request.target_start === exactRange.start &&
        request.target_end === exactRange.end,
      "Custom dates were not preserved in the API request",
    );
    await page.screenshot(join(args.output, "desktop-custom-period.png"));
    screenshots.push({
      name: "desktop-custom-period.png",
      width: 1440,
      height: 900,
      state: "Exact fields synchronized with handles",
    });

    const beforeWindow = await page.evaluate(`(() => ({
      start: Number(document.querySelector('[data-timeline-start-slider]').value),
      end: Number(document.querySelector('[data-timeline-end-slider]').value),
      selection: (() => { const r = document.querySelector('[data-timeline-selection]').getBoundingClientRect(); return {x: r.left + r.width / 2, y: r.top + r.height / 2}; })(),
      railWidth: document.querySelector('[data-timeline-rail]').getBoundingClientRect().width,
      steps: Number(document.querySelector('[data-timeline-end-slider]').max),
    }))()`);
    before = await page.evaluate(requestCount());
    await page.send("Input.dispatchMouseEvent", { type: "mousePressed", x: beforeWindow.selection.x, y: beforeWindow.selection.y, button: "left", clickCount: 1 });
    await page.send("Input.dispatchMouseEvent", { type: "mouseMoved", x: beforeWindow.selection.x + beforeWindow.railWidth / beforeWindow.steps, y: beforeWindow.selection.y, button: "left" });
    await page.send("Input.dispatchMouseEvent", { type: "mouseReleased", x: beforeWindow.selection.x + beforeWindow.railWidth / beforeWindow.steps, y: beforeWindow.selection.y, button: "left", clickCount: 1 });
    await waitFor(page, `${requestCount()} > ${before}`, "dragged window movement request");
    const afterWindow = await page.evaluate(`(() => ({start: Number(document.querySelector('[data-timeline-start-slider]').value), end: Number(document.querySelector('[data-timeline-end-slider]').value)}))()`);
    assert(afterWindow.start === beforeWindow.start + 1 && afterWindow.end === beforeWindow.end + 1, "Selected window did not drag intact");

    before = await page.evaluate(requestCount());
    await page.evaluate(
      `document.querySelector('[data-action="reset"]').click()`,
    );
    await waitFor(
      page,
      `${requestCount()} > ${before}`,
      "timeline reset request",
    );
    await waitFor(
      page,
      `document.querySelector('[data-timeline-months="all"]').classList.contains('is-active')`,
      "timeline reset state",
    );
    assert(
      page.errors.length === 0,
      `Browser errors: ${page.errors.join(" | ")}`,
    );
  }

  const report = {
    generatedAt: new Date().toISOString(),
    screenshots,
    screenshotsOnly: args.screenshotsOnly,
    browserErrors: page.errors,
  };
  writeFileSync(
    join(args.output, "timeline-validation.json"),
    JSON.stringify(report, null, 2),
  );
  process.stdout.write(
    args.screenshotsOnly
      ? "timeline screenshot capture passed\n"
      : "timeline UX validation passed\n",
  );
} finally {
  page?.close();
  if (server.exitCode === null) server.kill("SIGTERM");
  if (chrome.exitCode === null) chrome.kill("SIGTERM");
  await sleep(300);
  rmSync(profile, {
    recursive: true,
    force: true,
    maxRetries: 5,
    retryDelay: 100,
  });
}
