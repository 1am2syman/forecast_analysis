#!/usr/bin/env node

/**
 * Release-quality browser and screenshot validation for dashboard/index.html.
 *
 * No npm dependencies: the harness launches Python's static server and Chromium,
 * drives Chrome through CDP using Node's native WebSocket, captures deterministic
 * screenshots, OCRs the rendered UI, and writes machine-readable evidence.
 */

import { createServer } from "node:net";
import { get as httpGet } from "node:http";
import { spawn, spawnSync } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import {
  existsSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { setTimeout as sleep } from "node:timers/promises";

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(SCRIPT_DIR, "..");
const DASHBOARD_DIR = join(ROOT, "dashboard");
const DEFAULT_OUTPUT = join(
  ROOT,
  "validation-artifacts/static-dashboard-shell",
);
const TAB_IDS = ["overview", "trends", "comparison", "history", "quality"];
const TAB_HEADINGS = {
  overview: "Performance at a glance",
  trends: "How accuracy moves",
  comparison: "TM vs ML, and how revisions land",
  history: "Product vintage history",
  quality: "What the population hides",
};
const VIEWPORTS = [
  { name: "desktop", width: 1440, height: 900 },
  { name: "short", width: 1440, height: 720 },
  { name: "narrow", width: 800, height: 700 },
];

function parseArgs(argv) {
  const args = { output: DEFAULT_OUTPUT };
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i] === "--output") {
      args.output = resolve(ROOT, argv[i + 1]);
      i += 1;
    } else if (argv[i] === "--help") {
      process.stdout.write(
        "Usage: node scripts/validate_static_dashboard_ui.mjs [--output DIR]\n",
      );
      process.exit(0);
    } else {
      throw new Error(`Unknown argument: ${argv[i]}`);
    }
  }
  return args;
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function parseJson(value, label) {
  try {
    return JSON.parse(value);
  } catch (error) {
    throw new Error(`${label} returned invalid JSON: ${error.message}`, {
      cause: error,
    });
  }
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
      const port =
        typeof address === "object" && address ? address.port : undefined;
      server.close(() => resolvePort(port));
    });
  });
}

function requestStatus(url) {
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
    request.setTimeout(2_000, () =>
      request.destroy(new Error("request timed out")),
    );
  });
}

async function waitForUrl(url, timeoutMs = 15_000) {
  const deadline = Date.now() + timeoutMs;
  let lastError;
  while (Date.now() < deadline) {
    try {
      const status = await requestStatus(url);
      if (status >= 200 && status < 300) return status;
      lastError = new Error(`${url} returned ${status}`);
    } catch (error) {
      lastError = error;
    }
    await sleep(150);
  }
  throw new Error(`Timed out waiting for ${url}: ${lastError}`);
}

function terminate(process) {
  if (!process || process.killed) return;
  process.kill("SIGTERM");
  setTimeout(() => {
    if (!process.killed) process.kill("SIGKILL");
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
      const message = parseJson(String(event.data), "CDP message");
      if (message.id && this.pending.has(message.id)) {
        const { resolveCommand, rejectCommand } = this.pending.get(message.id);
        this.pending.delete(message.id);
        if (message.error) rejectCommand(new Error(message.error.message));
        else resolveCommand(message.result);
        return;
      }
      if (message.method === "Runtime.consoleAPICalled") {
        if (
          message.params.type === "error" ||
          message.params.type === "warning"
        ) {
          this.consoleErrors.push(
            message.params.args
              .map((arg) => arg.value ?? arg.description ?? "")
              .join(" "),
          );
        }
      } else if (message.method === "Runtime.exceptionThrown") {
        this.pageErrors.push(message.params.exceptionDetails.text);
      } else if (message.method === "Network.loadingFailed") {
        if (!message.params.canceled) {
          this.networkFailures.push(
            `${message.params.errorText}: ${message.params.requestId}`,
          );
        }
      } else if (message.method === "Network.responseReceived") {
        const { response } = message.params;
        if (response.status >= 400) {
          this.httpErrors.push(`${response.status} ${response.url}`);
        }
      }
    };
  }

  send(method, params = {}) {
    return new Promise((resolveCommand, rejectCommand) => {
      const id = ++this.nextId;
      this.pending.set(id, { resolveCommand, rejectCommand });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }

  async evaluate(expression, { awaitPromise = false } = {}) {
    const result = await this.send("Runtime.evaluate", {
      expression,
      returnByValue: true,
      awaitPromise,
    });
    if (result.exceptionDetails) {
      throw new Error(result.exceptionDetails.text);
    }
    return result.result?.value;
  }

  async setViewport(width, height) {
    await this.send("Emulation.setDeviceMetricsOverride", {
      width,
      height,
      deviceScaleFactor: 1,
      mobile: false,
    });
  }

  async setReducedMotion(reduce) {
    await this.send("Emulation.setEmulatedMedia", {
      features: [
        {
          name: "prefers-reduced-motion",
          value: reduce ? "reduce" : "no-preference",
        },
      ],
    });
  }

  async navigate(url) {
    await this.send("Page.navigate", { url });
    await sleep(1_100);
    await this.evaluate("document.fonts.ready", { awaitPromise: true });
  }

  async screenshot(path, clip) {
    const params = { format: "png" };
    if (clip) params.clip = clip;
    const result = await this.send("Page.captureScreenshot", params);
    writeFileSync(path, Buffer.from(result.data, "base64"));
  }

  close() {
    this.socket.close();
  }
}

function parseRgb(value) {
  const hex = value.match(/^#([\da-f]{3}|[\da-f]{6})$/i);
  if (hex) {
    const normalized =
      hex[1].length === 3
        ? hex[1]
            .split("")
            .map((digit) => `${digit}${digit}`)
            .join("")
        : hex[1];
    return [0, 2, 4].map((index) =>
      Number.parseInt(normalized.slice(index, index + 2), 16),
    );
  }
  const rgb = value.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
  assert(rgb, `Could not parse color: ${value}`);
  return rgb.slice(1, 4).map(Number);
}

function relativeLuminance([red, green, blue]) {
  const channels = [red, green, blue].map((value) => {
    const channel = value / 255;
    return channel <= 0.04045
      ? channel / 12.92
      : ((channel + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

function contrastRatio(foreground, background) {
  const first = relativeLuminance(parseRgb(foreground));
  const second = relativeLuminance(parseRgb(background));
  return (Math.max(first, second) + 0.05) / (Math.min(first, second) + 0.05);
}

function pngDimensions(path) {
  const buffer = readFileSync(path);
  assert(buffer.toString("ascii", 1, 4) === "PNG", `${path} is not a PNG`);
  return {
    width: buffer.readUInt32BE(16),
    height: buffer.readUInt32BE(20),
  };
}

function sha256(path) {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

function internalHtmlToken(value) {
  const token = String(value);
  assert(/^[\w .×,/:-]+$/u.test(token), `Unexpected gallery token: ${token}`);
  return token;
}

function ocr(path) {
  const result = spawnSync("tesseract", [path, "stdout", "--psm", "11"], {
    encoding: "utf8",
    maxBuffer: 2 * 1024 * 1024,
  });
  assert(result.status === 0, `Tesseract failed for ${path}: ${result.stderr}`);
  return result.stdout.replace(/\s+/g, " ").trim();
}

function imageEntropy(path) {
  const result = spawnSync("identify", ["-format", "%[entropy]", path], {
    encoding: "utf8",
  });
  assert(result.status === 0, `ImageMagick identify failed for ${path}`);
  return Number(result.stdout.trim());
}

function imageDistance(first, second) {
  const result = spawnSync(
    "compare",
    ["-metric", "RMSE", first, second, "null:"],
    { encoding: "utf8" },
  );
  assert(
    result.status === 0 || result.status === 1,
    `ImageMagick compare failed`,
  );
  const match = result.stderr.match(/\(([^)]+)\)/);
  return match ? Number(match[1]) : 0;
}

function makeContactSheet(output, paths, columns, tile) {
  const result = spawnSync(
    "montage",
    [
      ...paths,
      "-background",
      "#edf3f1",
      "-geometry",
      `${tile}+8+8`,
      "-tile",
      `${columns}x`,
      output,
    ],
    { encoding: "utf8" },
  );
  assert(result.status === 0, `Failed to create ${output}: ${result.stderr}`);
}

async function getNewPage(debugPort) {
  const target = await fetch(
    `http://127.0.0.1:${debugPort}/json/new?about:blank`,
    { method: "PUT" },
  ).then((response) => response.json());
  const page = new CdpPage(target.webSocketDebuggerUrl);
  await page.connect();
  await Promise.all([
    page.send("Page.enable"),
    page.send("Runtime.enable"),
    page.send("Network.enable"),
    page.send("Log.enable"),
    page.send("Accessibility.enable"),
  ]);
  return page;
}

async function semanticAudit(page) {
  return parseJson(
    await page.evaluate(`(() => {
      const tabs = Array.from(document.querySelectorAll('[role="tab"]'));
      const panes = Array.from(document.querySelectorAll('[role="tabpanel"]'));
      const selected = tabs.filter((tab) => tab.getAttribute('aria-selected') === 'true');
      const visiblePanes = panes.filter((pane) => getComputedStyle(pane).display !== 'none');
      const tabContracts = tabs.map((tab) => ({
        id: tab.dataset.target,
        controls: tab.getAttribute('aria-controls'),
        controlsExists: Boolean(document.getElementById(tab.getAttribute('aria-controls'))),
        labelledPane: document.getElementById(tab.getAttribute('aria-controls'))?.getAttribute('aria-labelledby'),
      }));
      return JSON.stringify({
        title: document.title,
        lang: document.documentElement.lang,
        tabs: tabs.length,
        panes: panes.length,
        selected: selected.map((tab) => tab.dataset.target),
        visiblePanes: visiblePanes.map((pane) => pane.id),
        tabContracts,
        headings: Array.from(document.querySelectorAll('h1, h2, h3')).map((h) => h.textContent.trim()),
        demoValues: document.querySelectorAll('[data-demo-value]').length,
        svgCharts: document.querySelectorAll('svg.chart').length,
        skeletons: document.querySelectorAll('.skel').length,
        placeholderText: Array.from(document.querySelectorAll('body *')).filter((el) => /placeholder|to be wired/i.test(el.textContent || '')).length,
        enabledExports: Array.from(document.querySelectorAll('[data-export]:not(:disabled)')).length,
        scopeControls: document.querySelectorAll('[data-scope-control]').length,
        metricSelectorOptions: Object.fromEntries(Array.from(document.querySelectorAll('[data-metric-selector]')).map((select) => [select.dataset.metricSelector, Array.from(select.options).map((option) => option.textContent.trim())])),
        comparisonModes: document.querySelectorAll('[data-subtabs="comparison"] [data-subtab-target]').length,
        historyModes: document.querySelectorAll('[data-subtabs="history"] [data-subtab-target]').length,
        qualityCategories: document.querySelectorAll('[data-subtabs="quality"] [data-subtab-target]').length,
        exceptionRows: document.querySelectorAll('[data-exception-text]').length,
        qualityExceptions: document.querySelectorAll('.quality-exceptions article').length,
        qualityStatuses: document.querySelectorAll('.quality-status').length,
        stabilityMetrics: document.querySelectorAll('.stability article div').length,
        stateOptions: Array.from(document.querySelector('[data-demo-state]').options).map((option) => option.value),
        absoluteErrorText: document.querySelector('[data-metric="absolute-error"]')?.textContent.replace(/s+/g, ' ').trim(),
        errorImprovementText: document.querySelector('[data-metric="error-improvement"]')?.textContent.replace(/s+/g, ' ').trim(),
        populationLedger: document.querySelector('.scopebar')?.textContent.replace(/s+/g, ' ').trim(),
        sourceComparisonText: document.querySelector('[data-subpanel="comparison:sources"]')?.textContent.replace(/s+/g, ' ').trim(),
        landmarks: {
          header: Boolean(document.querySelector('header.topbar')),
          nav: Boolean(document.querySelector('nav[aria-label="Dashboard sections"]')),
          main: Boolean(document.querySelector('main')),
          footer: Boolean(document.querySelector('footer.statusbar')),
        },
      });
    })()`),
    "semantic audit",
  );
}

async function accessibilityAudit(page) {
  const tree = await page.send("Accessibility.getFullAXTree");
  const nodes = tree.nodes ?? [];
  const tabs = nodes
    .filter((node) => node.role?.value === "tab")
    .map((node) => node.name?.value)
    .filter(Boolean);
  const buttons = nodes
    .filter((node) => node.role?.value === "button")
    .map((node) => node.name?.value)
    .filter(Boolean);
  const targets = parseJson(
    await page.evaluate(`JSON.stringify(Array.from(document.querySelectorAll('button:not(:disabled)')).map((button) => {
      const rect = button.getBoundingClientRect();
      return { name: button.getAttribute('aria-label') || button.textContent.trim(), width: rect.width, height: rect.height };
    }).filter((target) => target.width > 0 && target.height > 0))`),
    "accessibility target sizes",
  );
  return { tabs, buttons, targets };
}

async function layoutAudit(page, tabId, viewport) {
  return parseJson(
    await page.evaluate(`(() => {
      document.querySelector('#tab-${tabId}').click();
      const pane = document.querySelector('#pane-${tabId}');
      const root = document.documentElement;
      const rail = document.querySelector('.rail');
      const visible = Array.from(pane.querySelectorAll('*')).filter((el) => {
        const style = getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
      });
      const allowedClip = (el) => Boolean(el.closest('svg')) || el.matches('.tab__meta, .statusbar__seg--mono, .population strong, .product-summary strong, .audit-table__head > *, .audit-table__row > *, .kpi__cap');
      const clipped = visible.filter((el) => !allowedClip(el) && (el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1));
      const outside = visible.filter((el) => {
        const rect = el.getBoundingClientRect();
        return rect.left < -1 || rect.right > innerWidth + 1 || rect.top < -1 || rect.bottom > innerHeight + 1;
      });
      const paneRect = pane.getBoundingClientRect();
      const lastVisibleChild = Array.from(pane.children).filter((child) => getComputedStyle(child).display !== 'none').at(-1);
      const last = lastVisibleChild?.getBoundingClientRect();
      return JSON.stringify({
        viewport: { width: innerWidth, height: innerHeight },
        tab: '${tabId}',
        activeTab: document.querySelector('.tab.is-active')?.dataset.target,
        activePane: document.querySelector('.pane.is-active')?.id,
        pageScroll: root.scrollHeight - root.clientHeight,
        horizontalOverflow: root.scrollWidth - root.clientWidth,
        paneScroll: pane.scrollHeight - pane.clientHeight,
        clipped: clipped.map((el) => ({
          element: el.className || el.tagName,
          clientWidth: el.clientWidth,
          scrollWidth: el.scrollWidth,
          clientHeight: el.clientHeight,
          scrollHeight: el.scrollHeight,
        })),
        outside: outside.map((el) => ({
          element: el.className || el.tagName,
          rect: (() => {
            const rect = el.getBoundingClientRect();
            return { left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom };
          })(),
        })),
        pane: { top: paneRect.top, bottom: paneRect.bottom },
        lastChildBottomGap: last ? Math.round(paneRect.bottom - last.bottom) : null,
        railWidth: Math.round(rail.getBoundingClientRect().width),
        tabNamesVisible: getComputedStyle(document.querySelector('.tab__name')).display !== 'none',
      });
    })()`),
    `layout audit ${viewport.name}/${tabId}`,
  );
}

async function interactionAudit(page) {
  const clickSequence = [];
  for (const tabId of TAB_IDS) {
    await page.evaluate(`document.querySelector('#tab-${tabId}').click()`);
    const active = parseJson(
      await page.evaluate(`JSON.stringify({
        tab: document.querySelector('.tab.is-active')?.dataset.target,
        pane: document.querySelector('.pane.is-active')?.id,
        hash: location.hash.slice(1),
      })`),
      `click state ${tabId}`,
    );
    clickSequence.push(active);
  }

  await page.evaluate(`document.querySelector('#tab-overview').click()`);
  await page.evaluate(`document.querySelector('#tab-overview').focus()`);
  await page.send("Input.dispatchKeyEvent", {
    type: "keyDown",
    key: "ArrowDown",
    code: "ArrowDown",
    windowsVirtualKeyCode: 40,
  });
  await page.send("Input.dispatchKeyEvent", {
    type: "keyUp",
    key: "ArrowDown",
    code: "ArrowDown",
    windowsVirtualKeyCode: 40,
  });
  const keyboardTarget = await page.evaluate(
    `document.querySelector('.tab.is-active')?.dataset.target`,
  );

  await page.send("Input.dispatchKeyEvent", {
    type: "keyDown",
    key: "End",
    code: "End",
    windowsVirtualKeyCode: 35,
  });
  await page.send("Input.dispatchKeyEvent", {
    type: "keyUp",
    key: "End",
    code: "End",
    windowsVirtualKeyCode: 35,
  });
  const endTarget = await page.evaluate(
    `document.querySelector('.tab.is-active')?.dataset.target`,
  );
  await page.send("Input.dispatchKeyEvent", {
    type: "keyDown",
    key: "Home",
    code: "Home",
    windowsVirtualKeyCode: 36,
  });
  await page.send("Input.dispatchKeyEvent", {
    type: "keyUp",
    key: "Home",
    code: "Home",
    windowsVirtualKeyCode: 36,
  });
  const homeTarget = await page.evaluate(
    `document.querySelector('.tab.is-active')?.dataset.target`,
  );

  await page.evaluate(
    `document.querySelector('[data-action="reset"]').click()`,
  );
  const resetState = parseJson(
    await page.evaluate(`JSON.stringify({
      tab: document.querySelector('.tab.is-active')?.dataset.target,
      focused: document.activeElement?.dataset?.target,
    })`),
    "reset state",
  );

  const filterState = parseJson(
    await page.evaluate(`(() => {
      const scopeButton = document.querySelector('[data-action="scope"]');
      scopeButton.click();
      const drawerOpened = !document.querySelector('#scope-drawer').hidden && scopeButton.getAttribute('aria-expanded') === 'true';
      const mode = document.querySelector('[data-scope-control="mode"]');
      mode.value = 'comparison';
      mode.dispatchEvent(new Event('change', { bubbles: true }));
      const sharedScopeChanged = document.querySelector('[data-scope-mode]').textContent === 'TM vs ML' && document.querySelector('[data-scope-source]').textContent === 'TM + ML';
      const drawerClosedByNavigation = (() => { document.querySelector('#tab-history').click(); return document.querySelector('#scope-drawer').hidden; })();
      document.querySelector('[data-subtabs="history"] [data-subtab-target="exceptions"]').click();
      const search = document.querySelector('[data-exception-search]');
      search.value = 'JUN-008';
      search.dispatchEvent(new Event('input', { bubbles: true }));
      const visibleAfterFilter = Array.from(document.querySelectorAll('[data-exception-text]')).filter((row) => !row.hidden).length;
      document.querySelector('[data-action="reset"]').click();
      return JSON.stringify({
        drawerOpened,
        sharedScopeChanged,
        drawerClosedByNavigation,
        visibleAfterFilter,
        scopeReset: document.querySelector('[data-scope-mode]').textContent === 'Single source' && document.querySelector('[data-scope-source]').textContent === 'TM',
        visibleAfterReset: Array.from(document.querySelectorAll('[data-exception-text]')).filter((row) => !row.hidden).length,
      });
    })()`),
    "shared filter and exception state",
  );

  const hashSequence = await page.evaluate(
    `(async () => {
      const pane = () => document.querySelector('.pane.is-active')?.id;
      const sequence = [pane()];
      location.hash = '#trends';
      await new Promise((resolve) => setTimeout(resolve, 100));
      sequence.push(pane());
      history.back();
      await new Promise((resolve) => setTimeout(resolve, 100));
      sequence.push(pane());
      location.hash = '#quality';
      await new Promise((resolve) => setTimeout(resolve, 100));
      sequence.push(pane());
      return sequence;
    })()`,
    { awaitPromise: true },
  );

  await page.evaluate(`document.querySelector('#tab-overview').click()`);
  await page.evaluate(`document.querySelector('#tab-comparison').focus()`);
  const focus = parseJson(
    await page.evaluate(`(() => {
      const style = getComputedStyle(document.querySelector('#tab-comparison'));
      return JSON.stringify({ outline: style.outline, offset: style.outlineOffset });
    })()`),
    "focus state",
  );

  const rect = parseJson(
    await page.evaluate(`(() => {
      const rect = document.querySelector('#tab-comparison').getBoundingClientRect();
      return JSON.stringify({ x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 });
    })()`),
    "hover target",
  );
  const beforeHover = await page.evaluate(
    `getComputedStyle(document.querySelector('#tab-comparison')).backgroundColor`,
  );
  await page.send("Input.dispatchMouseEvent", {
    type: "mouseMoved",
    x: Math.round(rect.x),
    y: Math.round(rect.y),
  });
  await sleep(180);
  const afterHover = await page.evaluate(
    `getComputedStyle(document.querySelector('#tab-comparison')).backgroundColor`,
  );
  const paneAfterHover = await page.evaluate(
    `document.querySelector('.pane.is-active')?.id`,
  );

  return {
    clickSequence,
    keyboardTarget,
    endTarget,
    homeTarget,
    resetState,
    filterState,
    hashSequence,
    focus,
    hover: { beforeHover, afterHover, paneAfterHover },
  };
}

async function motionAndFontAudit(page) {
  await page.setReducedMotion(false);
  const normalMotion = parseJson(
    await page.evaluate(`(() => {
      const lamp = getComputedStyle(document.querySelector('.topbar .lamp--live'));
      return JSON.stringify({ lamp: lamp.animationName });
    })()`),
    "normal motion state",
  );
  await page.setReducedMotion(true);
  const reducedMotion = parseJson(
    await page.evaluate(`(() => {
      const lamp = getComputedStyle(document.querySelector('.topbar .lamp--live'));
      return JSON.stringify({ lamp: lamp.animationName });
    })()`),
    "reduced motion state",
  );
  await page.evaluate(
    `Promise.all([
      "600 16px 'Chakra Petch'",
      "400 14px 'IBM Plex Sans'",
      "600 14px 'IBM Plex Sans'",
      "400 11px 'IBM Plex Mono'",
      "500 11px 'IBM Plex Mono'"
    ].map((font) => document.fonts.load(font, "Forecast performance")))`,
    { awaitPromise: true },
  );
  const fonts = parseJson(
    await page.evaluate(`JSON.stringify({
      chakra600: document.fonts.check("600 16px 'Chakra Petch'"),
      plexSans400: document.fonts.check("400 14px 'IBM Plex Sans'"),
      plexSans600: document.fonts.check("600 14px 'IBM Plex Sans'"),
      plexMono400: document.fonts.check("400 11px 'IBM Plex Mono'"),
      plexMono500: document.fonts.check("500 11px 'IBM Plex Mono'"),
    })`),
    "font state",
  );
  return { normalMotion, reducedMotion, fonts };
}

async function contrastAudit(page) {
  const colors = parseJson(
    await page.evaluate(`(() => {
      const root = getComputedStyle(document.documentElement);
      const get = (name) => root.getPropertyValue(name).trim();
      return JSON.stringify({
        text: get('--text'), muted: get('--muted'), faint: get('--faint'), faint2: get('--faint-2'),
        teal: get('--teal'), amber: get('--amber'), panel: get('--panel'), panel3: get('--panel-3'), bg2: get('--bg-2'),
      });
    })()`),
    "contrast colors",
  );
  const pairs = [
    ["text/panel", colors.text, colors.panel],
    ["muted/panel3", colors.muted, colors.panel3],
    ["faint/panel3", colors.faint, colors.panel3],
    ["faint2/panel3", colors.faint2, colors.panel3],
    ["teal/panel", colors.teal, colors.panel],
    ["amber/panel", colors.amber, colors.panel],
  ].map(([name, foreground, background]) => ({
    name,
    foreground,
    background,
    ratio: Number(contrastRatio(foreground, background).toFixed(2)),
  }));
  return { colors, pairs };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  for (const command of [
    "python3",
    "chromium",
    "tesseract",
    "identify",
    "compare",
    "montage",
  ]) {
    assert(commandExists(command), `Required command is missing: ${command}`);
  }
  for (const file of ["index.html", "styles.css", "app.js"]) {
    assert(existsSync(join(DASHBOARD_DIR, file)), `Missing dashboard/${file}`);
  }

  rmSync(args.output, { recursive: true, force: true });
  mkdirSync(args.output, { recursive: true });

  const serverPort = await freePort();
  const debugPort = await freePort();
  const profileDir = join("/tmp", `static-dashboard-chrome-${randomUUID()}`);
  const server = spawn(
    "python3",
    [
      "-m",
      "http.server",
      String(serverPort),
      "--bind",
      "127.0.0.1",
      "--directory",
      DASHBOARD_DIR,
    ],
    { stdio: ["ignore", "ignore", "pipe"] },
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
    const baseUrl = `http://127.0.0.1:${serverPort}/index.html`;
    await waitForUrl(baseUrl);
    await waitForUrl(`http://127.0.0.1:${debugPort}/json/version`);
    page = await getNewPage(debugPort);
    await page.setViewport(1440, 900);
    await page.setReducedMotion(true);
    await page.navigate(`${baseUrl}?validation=base#overview`);

    const semantic = await semanticAudit(page);
    const accessibility = await accessibilityAudit(page);
    assert(semantic.lang === "en", "Document language must be en");
    assert(
      semantic.tabs === 5 && semantic.panes === 5,
      "Expected five tabs and five panes",
    );
    assert(semantic.selected.length === 1, "Exactly one tab must be selected");
    assert(
      semantic.visiblePanes.length === 1,
      "Exactly one pane must be visible",
    );
    assert(
      semantic.tabContracts.every(
        (contract) =>
          contract.controlsExists &&
          contract.labelledPane === `tab-${contract.id}`,
      ),
      "Tab/pane ARIA contracts are incomplete",
    );
    assert(
      Object.values(semantic.landmarks).every(Boolean),
      "All page landmarks must exist",
    );
    assert(
      semantic.demoValues >= 16,
      "Synthetic values must furnish the dashboard",
    );
    assert(
      semantic.svgCharts >= 4,
      "Expected at least four finished SVG charts",
    );
    assert(semantic.skeletons === 0, "No skeleton placeholders may remain");
    assert(semantic.placeholderText === 0, "No placeholder copy may remain");
    assert(
      semantic.enabledExports >= 6,
      "Metric-faithful shell must expose filtered and category-specific exports",
    );
    assert(
      semantic.scopeControls >= 20,
      `Expected the shared primary, vintage, performance, and quality filter contract; found ${semantic.scopeControls}`,
    );
    assert(
      semantic.metricSelectorOptions.monthly?.length === 4 &&
        semantic.metricSelectorOptions.horizon?.length === 2 &&
        semantic.metricSelectorOptions.heatmap?.length === 7,
      `Trend metric selectors are incomplete: ${JSON.stringify(semantic.metricSelectorOptions)}`,
    );
    assert(
      semantic.comparisonModes === 2 && semantic.historyModes === 2,
      "Comparison and product investigation must expose distinct bounded subviews",
    );
    assert(
      semantic.qualityCategories === 4 &&
        semantic.qualityStatuses >= 13 &&
        semantic.qualityExceptions >= 8,
      "Quality shell must expose all four categories, status evidence, and raw exceptions",
    );
    assert(
      semantic.exceptionRows === 6,
      "Expected six synthetic forecast exception rows",
    );
    assert(
      semantic.stabilityMetrics === 8,
      "Expected range, volatility, revision count, and maximum revision for TM and ML",
    );
    assert(
      semantic.stateOptions.join("|") === "populated|empty|blocked|zero",
      `Expected populated, empty, blocked, and zero-denominator review states; got ${semantic.stateOptions.join("|")}`,
    );
    assert(
      semantic.absoluteErrorText.includes("2,696 KL") &&
        !semantic.absoluteErrorText.includes("21.6%"),
      `Absolute error must use KL rather than normalized percent: ${semantic.absoluteErrorText}`,
    );
    assert(
      semantic.errorImprovementText.includes("+613 KL") &&
        semantic.errorImprovementText.includes("improve"),
      `Error improvement must use signed KL semantics: ${semantic.errorImprovementText}`,
    );
    assert(
      /Actual 12,480 KL/.test(semantic.populationLedger) &&
        /Comparable 132/.test(semantic.populationLedger) &&
        /11,756 \/ 12,480 KL · 94.2%/.test(semantic.populationLedger),
      `Population ledger is incomplete: ${semantic.populationLedger}`,
    );
    assert(
      /TM only/.test(semantic.sourceComparisonText) &&
        /ML only/.test(semantic.sourceComparisonText) &&
        /ML − TM accuracy/.test(semantic.sourceComparisonText),
      "Source comparison must distinguish common metrics, source-only coverage, and deltas",
    );
    assert(
      accessibility.tabs.join(" | ") ===
        "Overview | Trends | Comparison | Product history | Data quality, attention",
      `Accessible tab names are incorrect: ${accessibility.tabs.join(" | ")}`,
    );
    assert(
      accessibility.buttons.some((name) => name.toLowerCase() === "reset"),
      `Reset button must have an accessible name; AX buttons=${JSON.stringify(accessibility.buttons)}`,
    );
    assert(
      accessibility.targets.every(
        (target) => target.width >= 24 && target.height >= 24,
      ),
      `Interactive targets below 24px: ${JSON.stringify(accessibility.targets)}`,
    );

    const interaction = await interactionAudit(page);
    assert(
      interaction.clickSequence.every(
        (state, index) =>
          state.tab === TAB_IDS[index] &&
          state.pane === `pane-${TAB_IDS[index]}` &&
          state.hash === TAB_IDS[index],
      ),
      "Click navigation did not activate every tab/pane/hash",
    );
    assert(
      interaction.keyboardTarget === "trends",
      "ArrowDown must move Overview to Trends",
    );
    assert(
      interaction.endTarget === "quality",
      "End must move to Data quality",
    );
    assert(interaction.homeTarget === "overview", "Home must move to Overview");
    assert(
      interaction.resetState.tab === "overview" &&
        interaction.resetState.focused === "overview",
      "Reset must activate and focus Overview",
    );
    assert(
      interaction.filterState.drawerOpened &&
        interaction.filterState.sharedScopeChanged &&
        interaction.filterState.drawerClosedByNavigation &&
        interaction.filterState.visibleAfterFilter === 1 &&
        interaction.filterState.scopeReset &&
        interaction.filterState.visibleAfterReset === 6,
      `Shared filters, exception search, or reset failed: ${JSON.stringify(interaction.filterState)}`,
    );
    assert(
      interaction.hashSequence.join(" -> ") ===
        "pane-overview -> pane-trends -> pane-overview -> pane-quality",
      `Hash/back navigation failed: ${interaction.hashSequence.join(" -> ")}`,
    );
    assert(
      interaction.focus.outline.includes("2px"),
      "Keyboard focus ring must be 2px",
    );
    assert(
      interaction.hover.beforeHover !== interaction.hover.afterHover,
      "Hover style must visibly change",
    );
    assert(
      interaction.hover.paneAfterHover === "pane-overview",
      "Hover must not switch panes",
    );

    const motionFonts = await motionAndFontAudit(page);
    assert(
      motionFonts.normalMotion.lamp === "breathe",
      "Status lamp animation must run normally",
    );
    assert(
      motionFonts.reducedMotion.lamp === "none",
      "Reduced motion must disable lamp animation",
    );
    assert(
      Object.values(motionFonts.fonts).every(Boolean),
      `All active font faces must load: ${JSON.stringify(motionFonts.fonts)}`,
    );

    const contrast = await contrastAudit(page);
    assert(
      contrast.pairs.every((pair) => pair.ratio >= 4.5),
      `Text contrast failed: ${contrast.pairs.map((pair) => `${pair.name}=${pair.ratio}`).join(", ")}`,
    );

    const layout = [];
    const screenshots = [];
    for (const viewport of VIEWPORTS) {
      await page.setViewport(viewport.width, viewport.height);
      await page.setReducedMotion(true);
      await page.navigate(`${baseUrl}?validation=${viewport.name}#overview`);
      for (const tabId of TAB_IDS) {
        const metrics = await layoutAudit(page, tabId, viewport);
        layout.push({ viewportName: viewport.name, ...metrics });
        assert(
          metrics.activeTab === tabId,
          `${viewport.name}/${tabId}: wrong active tab`,
        );
        assert(
          metrics.activePane === `pane-${tabId}`,
          `${viewport.name}/${tabId}: wrong active pane`,
        );
        assert(
          metrics.pageScroll === 0,
          `${viewport.name}/${tabId}: page scroll detected`,
        );
        assert(
          metrics.horizontalOverflow === 0,
          `${viewport.name}/${tabId}: horizontal overflow detected`,
        );
        assert(
          metrics.paneScroll === 0,
          `${viewport.name}/${tabId}: pane scroll detected`,
        );
        assert(
          metrics.clipped.length === 0,
          `${viewport.name}/${tabId}: clipped elements: ${JSON.stringify(metrics.clipped)}`,
        );
        assert(
          metrics.outside.length === 0,
          `${viewport.name}/${tabId}: elements outside viewport: ${JSON.stringify(metrics.outside)}`,
        );
        assert(
          metrics.lastChildBottomGap >= 20 && metrics.lastChildBottomGap <= 40,
          `${viewport.name}/${tabId}: bottom gap ${metrics.lastChildBottomGap}px is not balanced`,
        );
        if (viewport.name === "narrow") {
          assert(
            metrics.railWidth === 76,
            `${viewport.name}: rail must collapse to 76px`,
          );
          assert(
            !metrics.tabNamesVisible,
            `${viewport.name}: tab labels must collapse`,
          );
        } else {
          assert(
            metrics.railWidth === 232,
            `${viewport.name}: rail must remain 232px`,
          );
          assert(
            metrics.tabNamesVisible,
            `${viewport.name}: tab labels must remain visible`,
          );
        }
        const screenshotName = `${viewport.width}-${viewport.height}-${tabId}.png`;
        const screenshotPath = join(args.output, screenshotName);
        await page.screenshot(screenshotPath);
        screenshots.push({
          name: screenshotName,
          path: screenshotPath,
          viewport,
          tabId,
          expectedHeading: TAB_HEADINGS[tabId],
        });
      }
    }

    await page.setViewport(1440, 900);
    await page.setReducedMotion(true);
    await page.navigate(`${baseUrl}?validation=states#overview`);
    let focusedTarget = null;
    for (let press = 0; press < 8 && focusedTarget !== "overview"; press += 1) {
      await page.send("Input.dispatchKeyEvent", {
        type: "keyDown",
        key: "Tab",
        code: "Tab",
        windowsVirtualKeyCode: 9,
      });
      await page.send("Input.dispatchKeyEvent", {
        type: "keyUp",
        key: "Tab",
        code: "Tab",
        windowsVirtualKeyCode: 9,
      });
      focusedTarget = await page.evaluate(
        `document.activeElement?.dataset?.target ?? null`,
      );
    }
    assert(
      focusedTarget === "overview",
      "Tab sequence must reach the Overview tab",
    );
    const focusPath = join(args.output, "1440-900-focus-overview.png");
    await page.screenshot(focusPath);
    screenshots.push({
      name: "1440-900-focus-overview.png",
      path: focusPath,
      viewport: VIEWPORTS[0],
      tabId: "overview",
      expectedHeading: TAB_HEADINGS.overview,
    });

    const hoverRect = parseJson(
      await page.evaluate(`(() => {
        const rect = document.querySelector('#tab-comparison').getBoundingClientRect();
        return JSON.stringify({ x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 });
      })()`),
      "hover screenshot target",
    );
    await page.send("Input.dispatchMouseEvent", {
      type: "mouseMoved",
      x: Math.round(hoverRect.x),
      y: Math.round(hoverRect.y),
    });
    await sleep(180);
    const hoverPath = join(args.output, "1440-900-hover-comparison.png");
    await page.screenshot(hoverPath);
    screenshots.push({
      name: "1440-900-hover-comparison.png",
      path: hoverPath,
      viewport: VIEWPORTS[0],
      tabId: "overview",
      expectedHeading: TAB_HEADINGS.overview,
    });

    const rail = parseJson(
      await page.evaluate(`(() => {
        const rect = document.querySelector('.rail').getBoundingClientRect();
        return JSON.stringify({ x: rect.x, y: rect.y, width: rect.width, height: 430 });
      })()`),
      "rail screenshot clip",
    );
    const railPath = join(args.output, "1440-900-rail-detail.png");
    await page.screenshot(railPath, { ...rail, scale: 2 });
    screenshots.push({
      name: "1440-900-rail-detail.png",
      path: railPath,
      viewport: { width: 464, height: 860 },
      tabId: "rail",
      expectedHeading: "Overview",
    });

    assert(
      page.consoleErrors.length === 0,
      `Console errors: ${page.consoleErrors.join(" | ")}`,
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

    const baselineOverview = join(args.output, "1440-900-overview.png");
    assert(
      imageDistance(baselineOverview, focusPath) >= 0.0001,
      "Focus-visible screenshot must differ from the Overview baseline",
    );
    assert(
      imageDistance(baselineOverview, hoverPath) >= 0.0001,
      "Hover screenshot must differ from the Overview baseline",
    );

    const screenshotEvidence = screenshots.map((screenshot) => {
      const dimensions = pngDimensions(screenshot.path);
      assert(
        dimensions.width === screenshot.viewport.width &&
          dimensions.height === screenshot.viewport.height,
        `${screenshot.name}: expected ${screenshot.viewport.width}x${screenshot.viewport.height}, got ${dimensions.width}x${dimensions.height}`,
      );
      const entropy = imageEntropy(screenshot.path);
      assert(
        entropy >= 0.12,
        `${screenshot.name}: suspiciously blank (entropy ${entropy})`,
      );
      const text = ocr(screenshot.path);
      const normalized = text.toLowerCase();
      const headingWords = screenshot.expectedHeading
        .toLowerCase()
        .split(/\s+/)
        .filter((word) => word.length >= 4);
      const matchingWords = headingWords.filter((word) =>
        normalized.includes(word),
      );
      assert(
        matchingWords.length >= Math.min(2, headingWords.length),
        `${screenshot.name}: OCR did not find expected heading (${screenshot.expectedHeading}); OCR=${text}`,
      );
      return {
        name: screenshot.name,
        width: dimensions.width,
        height: dimensions.height,
        entropy: Number(entropy.toFixed(4)),
        sha256: sha256(screenshot.path),
        ocr: text,
      };
    });

    for (const viewport of VIEWPORTS) {
      const files = TAB_IDS.map((tabId) =>
        join(args.output, `${viewport.width}-${viewport.height}-${tabId}.png`),
      );
      for (let i = 1; i < files.length; i += 1) {
        const distance = imageDistance(files[i - 1], files[i]);
        assert(
          distance >= 0.01,
          `${viewport.name}: adjacent tab screenshots look duplicated`,
        );
      }
      makeContactSheet(
        join(args.output, `contact-sheet-${viewport.name}.png`),
        files,
        viewport.name === "narrow" ? 2 : 3,
        viewport.name === "narrow" ? "400x350" : "480x300",
      );
    }
    makeContactSheet(
      join(args.output, "contact-sheet-states.png"),
      [focusPath, hoverPath, railPath],
      3,
      "480x300",
    );

    const report = {
      generatedAt: new Date().toISOString(),
      dashboard: "dashboard/index.html",
      screenshots: screenshotEvidence,
      semantic,
      accessibility,
      interaction,
      motionFonts,
      contrast,
      layout,
      browserDiagnostics: {
        consoleErrors: page.consoleErrors,
        pageErrors: page.pageErrors,
        networkFailures: page.networkFailures,
        httpErrors: page.httpErrors,
      },
    };
    writeFileSync(
      join(args.output, "validation-report.json"),
      `${JSON.stringify(report, null, 2)}\n`,
    );

    const markdown = [
      "# Static dashboard UI validation",
      "",
      `Generated: ${report.generatedAt}`,
      "",
      "## Result",
      "",
      "**PASS** — all browser, interaction, accessibility, overflow, typography, contrast, OCR, and screenshot checks passed.",
      "",
      "## Coverage",
      "",
      `- ${TAB_IDS.length} tabs × ${VIEWPORTS.length} viewports = ${TAB_IDS.length * VIEWPORTS.length} primary screenshots`,
      "- Focus-visible, hover, and rail-detail states",
      "- Click, keyboard, reset, hash-change, and browser-back navigation",
      "- Zero page scroll, pane scroll, and horizontal overflow",
      "- Loaded font faces and reduced-motion behavior",
      "- WCAG text contrast ratios ≥ 4.5:1",
      "- OCR heading verification and nonblank/distinct screenshot checks",
      "- Console, page exception, network, and HTTP error checks",
      "",
      "## Contact sheets",
      "",
      "![Desktop tab matrix](contact-sheet-desktop.png)",
      "",
      "![Short laptop tab matrix](contact-sheet-short.png)",
      "",
      "![Collapsed rail tab matrix](contact-sheet-narrow.png)",
      "",
      "![Interaction states](contact-sheet-states.png)",
      "",
      "## Contrast",
      "",
      "| Pair | Ratio |",
      "| --- | ---: |",
      ...contrast.pairs.map((pair) => `| ${pair.name} | ${pair.ratio}:1 |`),
      "",
      "## Layout matrix",
      "",
      "| Viewport | Tab | Page scroll | Horizontal overflow | Pane scroll | Bottom gap |",
      "| --- | --- | ---: | ---: | ---: | ---: |",
      ...layout.map(
        (entry) =>
          `| ${entry.viewportName} | ${entry.tab} | ${entry.pageScroll}px | ${entry.horizontalOverflow}px | ${entry.paneScroll}px | ${entry.lastChildBottomGap}px |`,
      ),
      "",
    ].join("\n");
    writeFileSync(join(args.output, "validation-report.md"), markdown);

    const galleryGroups = [
      {
        title: "Contact sheets",
        files: [
          "contact-sheet-desktop.png",
          "contact-sheet-short.png",
          "contact-sheet-narrow.png",
          "contact-sheet-states.png",
        ],
      },
      ...VIEWPORTS.map((viewport) => ({
        title: `${viewport.width} × ${viewport.height}`,
        files: TAB_IDS.map(
          (tabId) => `${viewport.width}-${viewport.height}-${tabId}.png`,
        ),
      })),
      {
        title: "Interaction details",
        files: [
          "1440-900-focus-overview.png",
          "1440-900-hover-comparison.png",
          "1440-900-rail-detail.png",
        ],
      },
    ];
    const gallery = `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Static dashboard validation gallery</title>
  <style>
    :root { color-scheme: light; --bg:#edf3f1; --panel:#ffffff; --line:#c8d5d1; --text:#172421; --muted:#536762; --accent:#087f75; }
    * { box-sizing:border-box; }
    body { margin:0; padding:32px; font:14px/1.5 system-ui,sans-serif; color:var(--text); background:var(--bg); }
    header { max-width:1500px; margin:0 auto 32px; }
    h1,h2 { margin:0; }
    h1 { font-size:28px; }
    h2 { margin:30px 0 12px; font-size:17px; color:var(--accent); }
    p { color:var(--muted); }
    a { color:var(--accent); }
    main { max-width:1500px; margin:auto; }
    .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); gap:16px; }
    figure { margin:0; padding:10px; overflow:hidden; border:1px solid var(--line); border-radius:8px; background:var(--panel); }
    img { display:block; width:100%; height:auto; border:1px solid var(--line); }
    figcaption { padding:8px 2px 0; color:var(--muted); font-family:ui-monospace,monospace; font-size:12px; }
  </style>
</head>
<body>
  <header>
    <h1>Static dashboard validation gallery</h1>
    <p>18 deterministic screenshots. <a href="validation-report.html">Open the validation report</a> · <a href="validation-report.json">JSON evidence</a></p>
  </header>
  <main>
    ${galleryGroups
      .map(
        (group) =>
          `<section><h2>${internalHtmlToken(group.title)}</h2><div class="grid">${group.files
            .map(
              (file) =>
                `<figure><a href="${internalHtmlToken(file)}"><img src="${internalHtmlToken(file)}" alt="${internalHtmlToken(file)}" loading="lazy" /></a><figcaption>${internalHtmlToken(file)}</figcaption></figure>`,
            )
            .join("")}</div></section>`,
      )
      .join("")}
  </main>
</body>
</html>`;
    writeFileSync(join(args.output, "index.html"), gallery);
    writeFileSync(
      join(args.output, "validation-report.html"),
      `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Validation report</title><style>body{max-width:1100px;margin:40px auto;padding:0 20px;font:15px/1.55 system-ui,sans-serif;color:#172421;background:#edf3f1}table{border-collapse:collapse;width:100%;background:#fff}th,td{border:1px solid #c8d5d1;padding:8px;text-align:left}a{color:#087f75}code{font-family:ui-monospace,monospace}</style></head><body><p><a href="index.html">← Screenshot gallery</a></p><h1>Static dashboard UI validation</h1><p><strong>PASS</strong> — all browser, interaction, accessibility, overflow, typography, contrast, OCR, and screenshot checks passed.</p><h2>Coverage</h2><ul><li>5 tabs × 3 viewports = 15 primary screenshots</li><li>Focus-visible, hover, and rail-detail states</li><li>Click, Arrow, Home/End, reset, hash-change, and browser-back navigation</li><li>Zero page scroll, pane scroll, and horizontal overflow</li><li>Loaded fonts, reduced-motion behavior, WCAG contrast, and accessible names</li><li>Console, network, page exception, OCR, and distinctness checks</li></ul><h2>Contrast</h2><table><thead><tr><th>Pair</th><th>Ratio</th></tr></thead><tbody>${contrast.pairs.map((pair) => `<tr><td>${internalHtmlToken(pair.name)}</td><td>${pair.ratio}:1</td></tr>`).join("")}</tbody></table><h2>Layout</h2><table><thead><tr><th>Viewport</th><th>Tab</th><th>Page scroll</th><th>Horizontal overflow</th><th>Pane scroll</th><th>Bottom gap</th></tr></thead><tbody>${layout.map((entry) => `<tr><td>${internalHtmlToken(entry.viewportName)}</td><td>${internalHtmlToken(entry.tab)}</td><td>${entry.pageScroll}px</td><td>${entry.horizontalOverflow}px</td><td>${entry.paneScroll}px</td><td>${entry.lastChildBottomGap}px</td></tr>`).join("")}</tbody></table></body></html>`,
    );

    process.stdout.write(
      `Screenshots: ${screenshots.length}\nArtifacts: ${args.output}\nSTATIC DASHBOARD UI VALIDATION PASSED\n`,
    );
  } finally {
    page?.close();
    terminate(chrome);
    terminate(server);
    rmSync(profileDir, { recursive: true, force: true });
  }
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error.message}\n`);
  process.exitCode = 1;
});
