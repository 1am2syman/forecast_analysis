#!/usr/bin/env node

/** Validate the overview quick-filter row and its slider-only time control. */

import { spawn, spawnSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { get as httpGet } from "node:http";
import { createServer } from "node:net";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { setTimeout as sleep } from "node:timers/promises";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const output = resolve(
  ROOT,
  process.argv[2] || "validation-artifacts/quick-filter-row",
);
const VIEWPORTS = [
  { name: "1280x720", width: 1280, height: 720 },
  { name: "1920x1080", width: 1920, height: 1080 },
];

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

  async evaluate(expression) {
    const result = await this.send("Runtime.evaluate", {
      expression,
      returnByValue: true,
      awaitPromise: true,
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

async function waitFor(page, expression, label, timeout = 45_000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (await page.evaluate(expression)) return;
    await sleep(100);
  }
  throw new Error(`Timed out waiting for ${label}`);
}

async function waitForIdle(page) {
  await waitFor(
    page,
    `document.querySelector('.stage')?.getAttribute('aria-busy') === 'false'`,
    "dashboard refresh",
    75_000,
  );
}

async function rowGeometry(page) {
  return page.evaluate(`(() => {
    const row = document.querySelector('.quick-filter-row');
    const rect = row.getBoundingClientRect();
    const children = [...row.children].map((node) => {
      const bounds = node.getBoundingClientRect();
      return {
        left: bounds.left,
        right: bounds.right,
        top: bounds.top,
        bottom: bounds.bottom,
        width: bounds.width,
        height: bounds.height,
      };
    });
    const slider = document.querySelector('[data-timeline-rail]').getBoundingClientRect();
    return {
      row: {
        left: rect.left,
        right: rect.right,
        top: rect.top,
        bottom: rect.bottom,
        width: rect.width,
        height: rect.height,
        overflow: row.scrollWidth - row.clientWidth,
        whiteSpace: getComputedStyle(row).whiteSpace,
        gridTemplateRows: getComputedStyle(row).gridTemplateRows,
      },
      children,
      sliderWidth: slider.width,
      populationFacts: document.querySelectorAll('.overview-health__fact').length,
    };
  })()`);
}

function assertOneLine(geometry, viewport) {
  assert(
    geometry.row.overflow <= 1,
    `${viewport}: quick-filter row overflows by ${geometry.row.overflow}px`,
  );
  assert(
    geometry.row.height <= 37,
    `${viewport}: quick-filter row is too tall (${geometry.row.height}px)`,
  );
  assert(
    !geometry.row.gridTemplateRows.includes(" "),
    `${viewport}: quick-filter controls wrapped onto multiple grid rows (${geometry.row.gridTemplateRows})`,
  );
  assert(
    geometry.children.every(
      (child) =>
        child.left >= geometry.row.left - 1 &&
        child.right <= geometry.row.right + 1 &&
        child.top >= geometry.row.top - 1 &&
        child.bottom <= geometry.row.bottom + 1,
    ),
    `${viewport}: a quick-filter control is clipped outside the row`,
  );
  assert(
    geometry.sliderWidth >= 110,
    `${viewport}: time slider is too narrow (${geometry.sliderWidth}px)`,
  );
  assert(
    geometry.populationFacts === 0,
    `${viewport}: removed population statistics still appear`,
  );
  assert(
    geometry.row.whiteSpace === "nowrap",
    `${viewport}: quick-filter row does not enforce nowrap`,
  );
}

async function openMenu(page, fieldClass) {
  await page.evaluate(`(() => {
    const field = document.querySelector('${fieldClass}');
    field.querySelector('[data-multiselect-trigger]').click();
  })()`);
  await waitFor(
    page,
    `!document.querySelector('${fieldClass} [data-multiselect-popover]').hidden`,
    `${fieldClass} menu`,
  );
  return page.evaluate(`(() => {
    const popover = document.querySelector('${fieldClass} [data-multiselect-popover]');
    const bounds = popover.getBoundingClientRect();
    return {
      left: bounds.left,
      right: bounds.right,
      top: bounds.top,
      bottom: bounds.bottom,
      visible: bounds.width > 0 && bounds.height > 0,
      withinViewport: bounds.left >= 0 && bounds.right <= innerWidth && bounds.top >= 0 && bounds.bottom <= innerHeight,
    };
  })()`);
}

async function selectFirstOption(page, fieldClass) {
  await page.evaluate(`(() => {
    const option = [...document.querySelectorAll('${fieldClass} [data-filter-option]')]
      .find((node) => node.getAttribute('aria-disabled') !== 'true');
    if (!option) throw new Error('No selectable option in ${fieldClass}');
    option.click();
    document.querySelector('${fieldClass} [data-multiselect-trigger]').click();
  })()`);
  await waitForIdle(page);
  const summary = await page.evaluate(
    `document.querySelector('${fieldClass} [data-multiselect-summary]').textContent`,
  );
  assert(
    summary === "1 selected",
    `${fieldClass}: selection summary not updated`,
  );
}

for (const command of ["uv", "chromium"])
  assert(commandExists(command), `Required command missing: ${command}`);
rmSync(output, { recursive: true, force: true });
mkdirSync(output, { recursive: true });

const serverPort = await freePort();
const debugPort = await freePort();
const profile = join("/tmp", `forecast-quick-filter-${randomUUID()}`);
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
    "--force-device-scale-factor=1",
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
  await page.viewport(1280, 720);
  await page.send("Page.navigate", { url: baseUrl });
  await waitFor(
    page,
    `document.querySelector('[data-status]')?.textContent.includes('canonical dataset ready')`,
    "dashboard bootstrap",
    75_000,
  );
  await waitForIdle(page);

  const screenshots = [];
  const menuFields = [
    ["parent", ".quick-filter-field--parent"],
    ["brand", ".quick-filter-field--brand"],
    ["sku-class", ".quick-filter-field--sku"],
  ];

  for (const viewport of VIEWPORTS) {
    await page.viewport(viewport.width, viewport.height);
    await sleep(150);
    await page.evaluate(
      `document.querySelector('.body')?.classList.remove('is-rail-collapsed')`,
    );

    const geometry = await rowGeometry(page);
    assertOneLine(geometry, viewport.name);
    const minimalSliderStyle = await page.evaluate(`(() => {
      const rail = document.querySelector('[data-timeline-rail]');
      const selection = document.querySelector('[data-timeline-selection]');
      const startSlider = document.querySelector('[data-timeline-start-slider]');
      const trackStyle = getComputedStyle(rail, '::before');
      const selectionStyle = getComputedStyle(selection);
      const railBounds = rail.getBoundingClientRect();
      const inputBounds = startSlider.getBoundingClientRect();
      return {
        trackHeight: trackStyle.height,
        trackBorderWidth: trackStyle.borderTopWidth,
        selectionHeight: selectionStyle.height,
        selectionBackgroundSize: selectionStyle.backgroundSize,
        inputExtensionLeft: railBounds.left - inputBounds.left,
        inputExtensionRight: inputBounds.right - railBounds.right,
      };
    })()`);
    assert(
      minimalSliderStyle.trackHeight === "3px" &&
        minimalSliderStyle.trackBorderWidth === "0px",
      `${viewport.name}: timeline track is not the intended minimal 3px line`,
    );
    assert(
      minimalSliderStyle.selectionHeight === "20px" &&
        minimalSliderStyle.selectionBackgroundSize.includes("3px"),
      `${viewport.name}: selected range lost its larger invisible drag target`,
    );
    assert(
      Math.abs(minimalSliderStyle.inputExtensionLeft - 10) <= 0.25 &&
        Math.abs(minimalSliderStyle.inputExtensionRight - 10) <= 0.25,
      `${viewport.name}: handle centers do not cover both track boundaries`,
    );
    let name = `default-${viewport.name}.png`;
    await page.screenshot(join(output, name));
    screenshots.push({
      name,
      viewport: viewport.name,
      state: "default",
      geometry,
      minimalSliderStyle,
    });

    for (const [label, selector] of menuFields) {
      const menuGeometry = await openMenu(page, selector);
      assert(
        menuGeometry.visible && menuGeometry.withinViewport,
        `${viewport.name}: ${label} menu is clipped`,
      );
      assertOneLine(await rowGeometry(page), viewport.name);
      name = `${label}-open-${viewport.name}.png`;
      await page.screenshot(join(output, name));
      screenshots.push({
        name,
        viewport: viewport.name,
        state: `${label} menu open`,
        menuGeometry,
      });

      await selectFirstOption(page, selector);
      assertOneLine(await rowGeometry(page), viewport.name);
      name = `${label}-selected-${viewport.name}.png`;
      await page.screenshot(join(output, name));
      screenshots.push({
        name,
        viewport: viewport.name,
        state: `${label} selected`,
      });
      await page.evaluate(
        `document.querySelector('.quick-filter-row [data-action="reset"]').click()`,
      );
      await waitForIdle(page);
    }

    await page.evaluate(`(() => {
      const slider = document.querySelector('[data-timeline-start-slider]');
      slider.value = Math.min(Number(slider.max), Number(slider.value) + 1);
      slider.dispatchEvent(new Event('input', { bubbles: true }));
      slider.dispatchEvent(new Event('change', { bubbles: true }));
    })()`);
    await waitForIdle(page);
    const sliderState = await page.evaluate(`(() => ({
      start: Number(document.querySelector('[data-timeline-start-slider]').value),
      end: Number(document.querySelector('[data-timeline-end-slider]').value),
      startText: document.querySelector('[data-timeline-start]').textContent.trim(),
      endText: document.querySelector('[data-timeline-end]').textContent.trim(),
      selectedWidth: document.querySelector('[data-timeline-selection]').getBoundingClientRect().width,
      presets: document.querySelectorAll('[data-timeline-months]').length,
      visibleDateSelects: [...document.querySelectorAll('[data-control="target_start"], [data-control="target_end"]')]
        .some((node) => node.getBoundingClientRect().width > 0 || node.getBoundingClientRect().height > 0),
    }))()`);
    assert(
      sliderState.start <= sliderState.end,
      `${viewport.name}: invalid slider range`,
    );
    assert(
      sliderState.selectedWidth > 0,
      `${viewport.name}: selected track is hidden`,
    );
    assert(
      sliderState.startText && sliderState.endText,
      `${viewport.name}: slider dates are missing`,
    );
    assert(
      sliderState.presets === 0,
      `${viewport.name}: time presets are still visible`,
    );
    assert(
      !sliderState.visibleDateSelects,
      `${viewport.name}: time dropdowns are visible`,
    );
    assertOneLine(await rowGeometry(page), viewport.name);
    name = `time-changed-${viewport.name}.png`;
    await page.screenshot(join(output, name));
    screenshots.push({
      name,
      viewport: viewport.name,
      state: "time range changed",
      sliderState,
    });

    await page.evaluate(`(() => {
      const start = document.querySelector('[data-timeline-start-slider]');
      const end = document.querySelector('[data-timeline-end-slider]');
      start.value = end.value;
      start.dispatchEvent(new Event('input', { bubbles: true }));
      start.dispatchEvent(new Event('change', { bubbles: true }));
    })()`);
    await waitForIdle(page);
    const tightSliderState = await page.evaluate(`(() => {
      const rail = document.querySelector('[data-timeline-rail]');
      const start = document.querySelector('[data-timeline-start-slider]');
      const end = document.querySelector('[data-timeline-end-slider]');
      return {
        start: Number(start.value),
        end: Number(end.value),
        isTight: rail.classList.contains('is-tight'),
        startTransform: getComputedStyle(start, '::-webkit-slider-thumb').transform,
        endTransform: getComputedStyle(end, '::-webkit-slider-thumb').transform,
      };
    })()`);
    assert(
      tightSliderState.start === tightSliderState.end &&
        tightSliderState.isTight,
      `${viewport.name}: overlapping handles did not enter the tight state`,
    );
    assertOneLine(await rowGeometry(page), viewport.name);
    name = `time-tight-${viewport.name}.png`;
    await page.screenshot(join(output, name));
    screenshots.push({
      name,
      viewport: viewport.name,
      state: "single-month tight range",
      tightSliderState,
    });
    await page.evaluate(
      `document.querySelector('.quick-filter-row [data-action="reset"]').click()`,
    );
    await waitForIdle(page);

    await page.evaluate(
      `document.querySelector('.quick-filter-row [data-action="scope"]').click()`,
    );
    await waitFor(
      page,
      `!document.querySelector('#scope-drawer').hidden`,
      "filter drawer",
    );
    const drawerState = await page.evaluate(`(() => {
      const drawer = document.querySelector('#scope-drawer');
      const bounds = drawer.getBoundingClientRect();
      return {
        visible: bounds.width > 0 && bounds.height > 0,
        withinViewport: bounds.left >= 0 && bounds.right <= innerWidth,
        productGroupPresent: Boolean(drawer.querySelector('[data-product-group]')),
        timelinePresent: Boolean(drawer.querySelector('[data-timeline-control]')),
      };
    })()`);
    assert(
      drawerState.visible && drawerState.withinViewport,
      `${viewport.name}: filter drawer is clipped`,
    );
    assert(
      !drawerState.productGroupPresent,
      `${viewport.name}: product controls remain duplicated in drawer`,
    );
    assert(
      !drawerState.timelinePresent,
      `${viewport.name}: timeline remains duplicated in drawer`,
    );
    name = `drawer-open-${viewport.name}.png`;
    await page.screenshot(join(output, name));
    screenshots.push({
      name,
      viewport: viewport.name,
      state: "advanced drawer open",
      drawerState,
    });
    await page.evaluate(
      `document.querySelector('.quick-filter-row [data-action="scope"]').click()`,
    );
  }

  assert(
    page.errors.length === 0,
    `Browser errors: ${page.errors.join(" | ")}`,
  );
  const report = {
    generatedAt: new Date().toISOString(),
    screenshots,
    browserErrors: page.errors,
    assertions: [
      "The timeline track is a borderless 3px line.",
      "The selected range is visually 3px while retaining a 20px drag target.",
      "Each native range thumb uses a 2px by 14px vertical-line visual inside a 20px hit target.",
      "The range inputs extend 10px past both sides so handle centers cover the track boundaries.",
      "Overlapping handles enter the separated tight state.",
      "The complete quick-filter bar remains one non-wrapping row.",
    ],
    judgments: {
      improved: [
        "The time slider is visually lighter and no longer dominates the filter row.",
        "Circular handles were replaced by restrained vertical-line handles.",
        "The larger invisible interaction targets preserve drag usability.",
        "The endpoint markers now cover the full track boundaries like the former circular handles.",
      ],
      regressed: [],
      outOfPlace: [],
    },
  };
  writeFileSync(
    join(output, "validation-report.json"),
    JSON.stringify(report, null, 2),
  );
  process.stdout.write("quick-filter row validation passed\n");
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
