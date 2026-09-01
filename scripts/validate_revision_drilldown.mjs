#!/usr/bin/env node

/** Focused Chromium contract for the Comparison → Revision drill-down. */

import { spawn, spawnSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { createServer } from "node:net";
import { get as httpGet } from "node:http";
import { randomUUID } from "node:crypto";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { setTimeout as sleep } from "node:timers/promises";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const SCREENSHOT_DIR = join(ROOT, "validation-artifacts", "screenshots");
const assert = (condition, message) => {
  if (!condition) throw new Error(message);
};
const commandExists = (command) =>
  spawnSync("sh", ["-c", `command -v ${command}`], { encoding: "utf8" })
    .status === 0;
const freePort = () =>
  new Promise((resolvePort, reject) => {
    const server = createServer();
    server.unref();
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      server.close(() => resolvePort(address.port));
    });
  });
const waitForUrl = async (url) => {
  const deadline = Date.now() + 75_000;
  while (Date.now() < deadline) {
    try {
      const status = await new Promise((resolveStatus, reject) => {
        const request = httpGet(url, (response) => {
          response.resume();
          response.once("end", () => resolveStatus(response.statusCode));
        });
        request.once("error", reject);
      });
      if (status >= 200 && status < 300) return;
    } catch {}
    await sleep(250);
  }
  throw new Error(`Timed out waiting for ${url}`);
};
const terminate = (process) => {
  if (!process || process.exitCode !== null) return;
  process.kill("SIGTERM");
};

class CdpPage {
  constructor(webSocketUrl) {
    this.socket = new WebSocket(webSocketUrl);
    this.pending = new Map();
    this.nextId = 0;
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
      } catch {
        return;
      }
      if (!message.id || !this.pending.has(message.id)) return;
      const pending = this.pending.get(message.id);
      this.pending.delete(message.id);
      if (message.error) pending.reject(new Error(message.error.message));
      else pending.resolve(message.result);
    };
  }
  send(method, params = {}) {
    return new Promise((resolveResult, rejectResult) => {
      const id = ++this.nextId;
      this.pending.set(id, { resolve: resolveResult, reject: rejectResult });
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
        result.exceptionDetails.text || "Browser evaluation failed",
      );
    return result.result?.value;
  }
  async screenshot(path) {
    const result = await this.send("Page.captureScreenshot", { format: "png" });
    writeFileSync(path, Buffer.from(result.data, "base64"));
  }
  close() {
    this.socket.close();
  }
}

async function main() {
  assert(
    commandExists("uv") && commandExists("chromium"),
    "uv and chromium are required",
  );
  const serverPort = await freePort();
  const debugPort = await freePort();
  const profile = join("/tmp", `revision-drilldown-${randomUUID()}`);
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
  const browser = spawn(
    "chromium",
    [
      `--remote-debugging-port=${debugPort}`,
      `--user-data-dir=${profile}`,
      "--headless=new",
      "--no-sandbox",
      "about:blank",
    ],
    { stdio: "ignore" },
  );
  try {
    await waitForUrl(`http://127.0.0.1:${serverPort}/api/health`);
    await waitForUrl(`http://127.0.0.1:${debugPort}/json/version`);
    const targetResponse = await fetch(
      `http://127.0.0.1:${debugPort}/json/new?about:blank`,
      { method: "PUT" },
    );
    const target = await targetResponse.json();
    const page = new CdpPage(target.webSocketDebuggerUrl);
    await page.connect();
    await page.send("Runtime.enable");
    await page.send("Page.enable");
    await page.send("Emulation.setDeviceMetricsOverride", {
      width: 800,
      height: 700,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await page.send("Page.navigate", {
      url: `http://127.0.0.1:${serverPort}/#comparison`,
    });
    const wait = async (expression, message) => {
      const deadline = Date.now() + 75_000;
      while (Date.now() < deadline) {
        if (await page.evaluate(expression)) return;
        await sleep(150);
      }
      throw new Error(`Timed out: ${message}`);
    };
    await wait(
      "document.querySelector('[data-revision-panel] .outcome__drilldown') && !document.querySelector('#pane-comparison').classList.contains('is-stale')",
      "revision panel",
    );
    const outcomeLayoutExpression = `JSON.stringify({icons:document.querySelectorAll('[data-drilldown-category]').length,rows:document.querySelectorAll('.revision-drilldown-row').length,stripOverflow:document.querySelector('.outcome-strip').scrollWidth-document.querySelector('.outcome-strip').clientWidth,layout:[...document.querySelectorAll('.outcome')].map(outcome=>{const label=outcome.querySelector('b');const button=outcome.querySelector('.outcome__drilldown');const icon=button.querySelector('svg');const value=outcome.querySelector('strong');const labelRect=label.getBoundingClientRect();const buttonRect=button.getBoundingClientRect();const iconRect=icon.getBoundingClientRect();const valueRect=value.getBoundingClientRect();const style=getComputedStyle(button);const rightEdges=[labelRect.right,valueRect.right,buttonRect.right,iconRect.right];return {category:button.dataset.drilldownCategory,overlaps:buttonRect.left<valueRect.right&&buttonRect.right>valueRect.left&&buttonRect.top<valueRect.bottom&&buttonRect.bottom>valueRect.top,rightEdgeSpread:Math.max(...rightEdges)-Math.min(...rightEdges),verticalOrder:labelRect.bottom<=valueRect.top+1&&valueRect.bottom<=buttonRect.top+1,background:style.backgroundColor,borderTopWidth:style.borderTopWidth}})})`;
    const initial = await page.evaluate(outcomeLayoutExpression);
    await page.send("Emulation.setDeviceMetricsOverride", {
      width: 1440,
      height: 900,
      deviceScaleFactor: 1,
      mobile: false,
    });
    const wide = await page.evaluate(outcomeLayoutExpression);
    await page.send("Emulation.setDeviceMetricsOverride", {
      width: 800,
      height: 700,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await page.evaluate(
      "document.querySelector('[data-drilldown-category=improved]').click()",
    );
    await wait(
      "!document.querySelector('.revision-drilldown-popover').hidden && document.querySelectorAll('.revision-drilldown-row').length > 0",
      "drill-down popover",
    );
    const opened = await page.evaluate(
      `JSON.stringify({role:document.querySelector('.revision-drilldown-popover').getAttribute('role'),rows:document.querySelectorAll('.revision-drilldown-row').length,columns:document.querySelectorAll('.revision-drilldown-head [role=columnheader]').length,text:document.querySelector('.revision-drilldown-popover').textContent,triggerTag:document.querySelector('[data-drilldown-category=improved]').tagName,triggerTabIndex:document.querySelector('[data-drilldown-category=improved]').tabIndex,rowTags:[...document.querySelectorAll('.revision-drilldown-row')].map(row=>row.tagName)})`,
    );
    await page.send("Input.dispatchKeyEvent", {
      type: "keyDown",
      key: "Escape",
      code: "Escape",
      windowsVirtualKeyCode: 27,
    });
    await page.send("Input.dispatchKeyEvent", {
      type: "keyUp",
      key: "Escape",
      code: "Escape",
      windowsVirtualKeyCode: 27,
    });
    await wait(
      "document.querySelector('.revision-drilldown-popover').hidden",
      "keyboard-closed drill-down popover",
    );
    await page.evaluate(
      "document.querySelector('[data-drilldown-category=improved]').click()",
    );
    await wait(
      "!document.querySelector('.revision-drilldown-popover').hidden && document.querySelectorAll('.revision-drilldown-row').length > 0",
      "reopened drill-down popover",
    );
    const initialScatterCount = await page.evaluate(
      "document.querySelectorAll('.chart--revision-scatter .scatter__point').length",
    );
    const initialRadii = await page.evaluate(
      `JSON.stringify([...document.querySelectorAll('.chart--revision-scatter .scatter__point')].map(point=>Number(point.getAttribute('r'))))`,
    );
    const firstCode = await page.evaluate(
      "document.querySelector('.revision-drilldown-row').dataset.drilldownParentCode",
    );
    await page.evaluate(
      "document.querySelector('.revision-drilldown-row').click()",
    );
    await wait(
      `document.querySelector('[data-revision-panel] .revision-selection-bar:not([hidden])') && document.querySelectorAll('.chart--revision-scatter .scatter__point').length === ${initialScatterCount} && document.querySelectorAll('.chart--revision-scatter .scatter__point--selected').length === 1`,
      "single-parent scatter focus",
    );
    const single = await page.evaluate(
      `JSON.stringify({selected:document.querySelectorAll('.revision-drilldown-row.is-selected').length,selectionText:document.querySelector('.revision-selection-bar').textContent,scatter:document.querySelectorAll('.chart--revision-scatter .scatter__point').length,focused:document.querySelectorAll('.chart--revision-scatter .scatter__point--selected').length,context:document.querySelectorAll('.chart--revision-scatter .scatter__point--context').length,selectedOpacity:getComputedStyle(document.querySelector('.chart--revision-scatter .scatter__point--selected')).opacity,contextOpacity:getComputedStyle(document.querySelector('.chart--revision-scatter .scatter__point--context')).opacity,history:document.querySelectorAll('.chart--revision-history .revision-history__endpoint').length,kpi:document.querySelector('.comparison-kpis .kpi strong')?.textContent})`,
    );
    mkdirSync(SCREENSHOT_DIR, { recursive: true });
    await page.screenshot(
      join(SCREENSHOT_DIR, "comparison-drilldown-focus-800x700.png"),
    );
    const secondCode = await page.evaluate(
      "document.querySelectorAll('.revision-drilldown-row')[1]?.dataset.drilldownParentCode",
    );
    await page.evaluate(
      "document.querySelectorAll('.revision-drilldown-row')[1].dispatchEvent(new MouseEvent('click',{bubbles:true,shiftKey:true}))",
    );
    await wait(
      `document.querySelectorAll('.revision-drilldown-row.is-selected').length === 2 && document.querySelectorAll('.chart--revision-scatter .scatter__point').length === ${initialScatterCount} && document.querySelectorAll('.chart--revision-scatter .scatter__point--selected').length === 2`,
      "shift multi-selection focus",
    );
    const multi = await page.evaluate(
      "JSON.stringify({selected:[...document.querySelectorAll('.revision-drilldown-row.is-selected')].map(row=>row.dataset.drilldownParentCode),scatter:document.querySelectorAll('.chart--revision-scatter .scatter__point').length,focused:document.querySelectorAll('.chart--revision-scatter .scatter__point--selected').length,context:document.querySelectorAll('.chart--revision-scatter .scatter__point--context').length})",
    );
    const responsiveFocus = [];
    for (const [width, height] of [
      [1440, 900],
      [640, 700],
    ]) {
      await page.send("Emulation.setDeviceMetricsOverride", {
        width,
        height,
        deviceScaleFactor: 1,
        mobile: false,
      });
      await sleep(100);
      responsiveFocus.push([
        `${width}×${height}`,
        await page.evaluate(
          `JSON.stringify((()=>{const popover=document.querySelector('.revision-drilldown-popover').getBoundingClientRect();const frame=document.querySelector('.revision-layout .frame:nth-child(2)').getBoundingClientRect();const chart=document.querySelector('.chart--revision-scatter').getBoundingClientRect();return {documentOverflow:document.documentElement.scrollWidth-document.documentElement.clientWidth,popoverWithin:popover.left>=0&&popover.right<=innerWidth&&popover.top>=0&&popover.bottom<=innerHeight,chartWithinFrame:chart.left>=frame.left-1&&chart.right<=frame.right+1,frame:{left:frame.left,right:frame.right,width:frame.width},chart:{left:chart.left,right:chart.right,width:chart.width},selected:document.querySelectorAll('.chart--revision-scatter .scatter__point--selected').length,context:document.querySelectorAll('.chart--revision-scatter .scatter__point--context').length}})())`,
        ),
      ]);
      await page.screenshot(
        join(
          SCREENSHOT_DIR,
          `comparison-drilldown-focus-${width}x${height}.png`,
        ),
      );
    }
    await page.send("Emulation.setDeviceMetricsOverride", {
      width: 800,
      height: 700,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await page.evaluate(
      "document.querySelector('[data-drilldown-clear]').click()",
    );
    await wait(
      `document.querySelectorAll('.revision-drilldown-row.is-selected').length === 0 && document.querySelectorAll('.chart--revision-scatter .scatter__point').length > 2`,
      "clear selection",
    );
    const cleared = await page.evaluate(
      "JSON.stringify({selected:document.querySelectorAll('.revision-drilldown-row.is-selected').length,scatter:document.querySelectorAll('.chart--revision-scatter .scatter__point').length})",
    );
    page.close();
    for (const [viewport, result] of [
      ["800×700", initial],
      ["1440×900", wide],
    ]) {
      const parsed = JSON.parse(result);
      assert(
        parsed.icons === 4,
        `Expected four drill-down icons at ${viewport}: ${result}`,
      );
      assert(
        parsed.stripOverflow === 0 &&
          parsed.layout.every(
            (item) =>
              !item.overlaps &&
              item.rightEdgeSpread <= 1 &&
              item.verticalOrder &&
              item.background === "rgba(0, 0, 0, 0)" &&
              item.borderTopWidth === "0px",
          ),
        `Outcome label, value, and control layout regressed at ${viewport}: ${result}`,
      );
    }
    assert(
      JSON.parse(opened).role === "dialog" &&
        JSON.parse(opened).rows > 0 &&
        JSON.parse(opened).columns === 5 &&
        JSON.parse(opened).triggerTag === "BUTTON" &&
        JSON.parse(opened).triggerTabIndex === 0 &&
        JSON.parse(opened).rowTags.every((tag) => tag === "BUTTON"),
      `Popover contract failed: ${opened}`,
    );
    assert(
      initialScatterCount > 2 &&
        JSON.parse(initialRadii).every((radius) => radius === 7.2),
      `Default scatter bubble size is not 50% larger: count=${initialScatterCount} radii=${initialRadii}`,
    );
    assert(
      JSON.parse(single).selected === 1 &&
        JSON.parse(single).scatter === initialScatterCount &&
        JSON.parse(single).focused === 1 &&
        JSON.parse(single).context === initialScatterCount - 1 &&
        Number(JSON.parse(single).contextOpacity) <
          Number(JSON.parse(single).selectedOpacity) &&
        JSON.parse(single).selectionText.includes("visible for context") &&
        JSON.parse(single).history >= 1 &&
        JSON.parse(single).kpi,
      `Single selection focus failed for ${firstCode}: ${single}`,
    );
    assert(
      JSON.parse(multi).selected.length === 2 &&
        JSON.parse(multi).selected.includes(firstCode) &&
        JSON.parse(multi).selected.includes(secondCode) &&
        JSON.parse(multi).scatter === initialScatterCount &&
        JSON.parse(multi).focused === 2 &&
        JSON.parse(multi).context === initialScatterCount - 2,
      `Shift selection focus failed: ${multi}`,
    );
    for (const [viewport, result] of responsiveFocus) {
      const parsed = JSON.parse(result);
      assert(
        parsed.documentOverflow === 0 &&
          parsed.popoverWithin &&
          parsed.chartWithinFrame &&
          parsed.selected === 2 &&
          parsed.context === initialScatterCount - 2,
        `Responsive focus layout regressed at ${viewport}: ${result}`,
      );
    }
    assert(
      JSON.parse(cleared).selected === 0 && JSON.parse(cleared).scatter > 2,
      `Clear selection failed: ${cleared}`,
    );
    console.log("REVISION DRILLDOWN BROWSER VALIDATION PASSED");
  } finally {
    terminate(browser);
    terminate(server);
  }
}

main().catch((error) => {
  console.error(error.stack || error.message || String(error));
  process.exitCode = 1;
});
