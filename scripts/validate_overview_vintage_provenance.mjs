#!/usr/bin/env node
import assert from "node:assert/strict";
import { mkdirSync, writeFileSync } from "node:fs";
import { setTimeout as sleep } from "node:timers/promises";

// Uses the existing visible browser and dashboard; never starts a fallback server.
const phase = process.argv[2] || "after";
assert(["before", "after"].includes(phase));
const output = `validation-artifacts/overview-vintage-provenance/${phase}`;
mkdirSync(output, { recursive: true });
const target = await (
  await fetch("http://127.0.0.1:9222/json/new?about:blank", { method: "PUT" })
).json();
const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  socket.onopen = resolve;
  socket.onerror = reject;
});
let sequence = 0;
const pending = new Map();
const errors = [];
socket.onmessage = ({ data }) => {
  let message;
  try {
    message = JSON.parse(String(data));
  } catch (error) {
    errors.push(String(error));
    return;
  }
  if (message.id) {
    const item = pending.get(message.id);
    pending.delete(message.id);
    if (message.error) item.reject(new Error(message.error.message));
    else item.resolve(message.result);
  } else if (message.method === "Runtime.exceptionThrown")
    errors.push(message.params.exceptionDetails);
};
const send = (method, params = {}) =>
  new Promise((resolve, reject) => {
    const id = ++sequence;
    pending.set(id, { resolve, reject });
    socket.send(JSON.stringify({ id, method, params }));
  });
const evaluate = async (expression) => {
  const result = await send("Runtime.evaluate", {
    expression,
    returnByValue: true,
    awaitPromise: true,
  });
  if (result.exceptionDetails)
    throw new Error(JSON.stringify(result.exceptionDetails));
  return result.result.value;
};
const waitFor = async (expression) => {
  for (let i = 0; i < 300; i++) {
    if (await evaluate(expression)) return;
    await sleep(200);
  }
  throw new Error(`State timed out: ${expression}`);
};
const click = async (selector) => {
  assert(
    await evaluate(
      `Boolean(document.querySelector(${JSON.stringify(selector)}))`,
    ),
    selector,
  );
  await evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);
  await sleep(150);
};
const report = [];
async function capture(name, width, height) {
  await evaluate("document.fonts.ready");
  await sleep(180);
  const geometry = await evaluate(`(() => {
    const visible = [...document.querySelectorAll('.vintage-selector, #overview-chart-dialog, #overview-guide-dialog')].filter(n => !n.hidden);
    return {overflow:document.documentElement.scrollWidth-innerWidth, overlays:visible.map(n=>{const r=n.getBoundingClientRect();return {name:n.id||n.className,left:r.left,top:r.top,right:r.right,bottom:r.bottom};})};
  })()`);
  assert.equal(geometry.overflow, 0, `${name}: page overflow`);
  for (const rect of geometry.overlays)
    assert(
      rect.left >= -1 &&
        rect.top >= -1 &&
        rect.right <= width + 1 &&
        rect.bottom <= height + 1,
      `${name}: overlay outside viewport ${JSON.stringify(rect)}`,
    );
  const image = await send("Page.captureScreenshot", { format: "png" });
  const file = `${output}/${width}x${height}-${name}.png`;
  writeFileSync(file, Buffer.from(image.data, "base64"));
  report.push({ file, geometry });
}
async function select(ids) {
  if (await evaluate(`document.querySelector('.vintage-selector').hidden`))
    await click("[data-vintage-selector-trigger]");
  while (true) {
    const changed = await evaluate(`(() => {
      const wanted = new Set(${JSON.stringify(ids)});
      const input = [...document.querySelectorAll('[data-vintage-option]')].find(n => n.checked !== wanted.has(n.value));
      if (!input) return null;
      input.checked = wanted.has(input.value);
      const expected = [...document.querySelectorAll('[data-vintage-option]:checked')].map(n=>n.value);
      input.dispatchEvent(new Event('change',{bubbles:true}));
      return expected;
    })()`);
    if (changed === null) break;
    await waitFor(
      `JSON.stringify(window.__overviewPayload?.request.accuracy_vintage_ids) === ${JSON.stringify(JSON.stringify(changed))} && !document.querySelector('.loading')?.classList.contains('is-visible')`,
    );
  }
  await click('[data-vintage-selector-trigger][aria-expanded="true"]');
}
async function checkData(root, kind) {
  const data = await evaluate(`(() => {
    const payload=window.__overviewPayload, vp=payload.accuracy_vintages;
    const root=document.querySelector(${JSON.stringify(root)});
    const selected=[...vp.options.filter(s=>s.selected),vp.latest];
    const primary=[...vp.options,vp.latest].find(s=>s.id===vp.overview.primary.id);
    const rows=primary.rows.filter(r=>r.eligible_parents>0);
    const paths=[...root.querySelectorAll('path[data-vintage-id]')];
    return {primary:primary.id, metrics:vp.overview.metrics, selected:selected.map(s=>({id:s.id,rows:s.rows.filter(r=>r.eligible_parents>0)})), rows,
      bias:[...root.querySelectorAll('[data-tooltip-bias-raw]')].map(n=>({month:n.dataset.targetMonth,value:Number(n.dataset.tooltipBiasRaw),label:n.getAttribute('aria-label')})),
      lines:paths.map(n=>({id:n.dataset.vintageId,values:JSON.parse(n.dataset.volumeValues||'null'),color:getComputedStyle(n).stroke})),
      actual:JSON.parse(root.querySelector('[data-volume-role="actual"]')?.dataset.volumeValues||'null'),
      biasAxisOverlap:[...root.querySelectorAll('.bias-strip__bar text')].some(label=>{const a=label.getBoundingClientRect();return [...root.querySelectorAll('.chart__labels > text')].some(axis=>{const b=axis.getBoundingClientRect();return a.left<b.right&&a.right>b.left&&a.top<b.bottom&&a.bottom>b.top;});}),
      kpi:[...document.querySelectorAll('[data-kpis] .kpi')].find(n=>n.querySelector('.kpi__label-long')?.textContent==='Bias')?.querySelector('.kpi__val')?.textContent,
      accuracyColors:[...document.querySelectorAll('[data-overview-chart] path[data-vintage-id]')].map(n=>({id:n.dataset.vintageId,color:getComputedStyle(n).stroke})),
      legendColors:[...document.querySelectorAll(${JSON.stringify(kind === "volume" ? "[data-volume-chart-legend] .key" : "[data-overview-chart]")})].map(n=>getComputedStyle(n).backgroundColor)
    };
  })()`);
  if (phase === "after") {
    const header = await evaluate(`(() => {
      const title=document.querySelector('#volume-chart-title'), frame=title.closest('.frame'), action=frame.querySelector('.chart-expand');
      const t=title.getBoundingClientRect(),a=action.getBoundingClientRect(),f=frame.getBoundingClientRect();
      const legend=frame.querySelector('[data-volume-chart-legend]'),l=legend.getBoundingClientRect();
      return {titleHeight:t.height,lineHeight:parseFloat(getComputedStyle(title).lineHeight),actionInside:a.right<=f.right&&a.left>=f.left,legendBelow:getComputedStyle(legend).display==='none'||l.top>=t.bottom};
    })()`);
    assert(
      header.titleHeight <= header.lineHeight * 2,
      "volume title squeezed into more than two lines",
    );
    assert(
      header.actionInside && header.legendBelow,
      "volume legend crowds title or fullscreen control",
    );
    assert.equal(data.kpi, `${Number(data.metrics.bias_pct).toFixed(1)}%`);
    assert.deepEqual(
      data.lines.map((s) => s.id),
      data.selected.map((s) => s.id),
    );
    for (const series of data.selected) {
      assert.deepEqual(
        series.rows.map((r) => [
          r.snop_month,
          r.eligible_parents,
          r.actual_denominator_kl,
        ]),
        data.rows.map((r) => [
          r.snop_month,
          r.eligible_parents,
          r.actual_denominator_kl,
        ]),
      );
    }
    if (kind === "accuracy") {
      const tooltip = await evaluate(`(() => {
        const point=document.querySelector(${JSON.stringify(root)}+' [data-tooltip-bias-raw]');
        point.dispatchEvent(new PointerEvent('pointerover',{bubbles:true,clientX:500,clientY:300}));
        const text=document.querySelector('.chart-tooltip').textContent;
        point.dispatchEvent(new PointerEvent('pointerout',{bubbles:true}));
        return {text,label:point.dataset.tooltipBiasLabel};
      })()`);
      assert(
        tooltip.text.includes(tooltip.label),
        "visible tooltip omits primary bias label",
      );
      assert.equal(
        data.biasAxisOverlap,
        false,
        "bias labels overlap month axis",
      );
      assert.deepEqual(
        data.bias.map((r) => [r.month, r.value]),
        data.rows.map((r) => [r.snop_month, r.bias_pct]),
      );
      assert(
        data.bias.every(
          (r) =>
            !r.label.includes("latest forecast bias") ||
            data.primary === "latest_available",
        ),
      );
    } else {
      for (const line of data.lines) {
        assert.deepEqual(
          line.values,
          data.selected
            .find((s) => s.id === line.id)
            .rows.map((r) => r.forecast_kl),
        );
        const expectedColor = data.accuracyColors.find(
          (s) => s.id === line.id,
        ).color;
        assert.equal(line.color, expectedColor);
        assert(
          data.legendColors.includes(expectedColor),
          `legend missing ${expectedColor}`,
        );
      }
      assert.deepEqual(
        data.actual,
        data.rows.map((r) => r.actual_denominator_kl),
      );
    }
  }
  return data;
}
try {
  await send("Page.enable");
  await send("Runtime.enable");
  await send("Page.addScriptToEvaluateOnNewDocument", {
    source: `(() => {
    const original=window.fetch.bind(window);
    window.fetch=async(...args)=>{const response=await original(...args);const url=String(args[0]);
      if(url.includes('api/bootstrap')||url.includes('api/view/compact')) window.__overviewPayload=await response.clone().json();
      return response;};
  })()`,
  });
  for (const [width, height] of [
    [1280, 720],
    [1920, 1080],
  ]) {
    await send("Emulation.setDeviceMetricsOverride", {
      width,
      height,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await send("Page.navigate", { url: "http://127.0.0.1:8766/#overview" });
    await waitFor(
      `window.__overviewPayload && document.querySelector('[data-status]')?.textContent.includes('canonical dataset ready')`,
    );
    const ids = await evaluate(
      "window.__overviewPayload.accuracy_vintages.options.map(s=>s.id)",
    );
    const states = [
      ["default-m5", [ids[0]]],
      ["multiple", [ids[0], ids[1], ids[2]]],
      ["promoted-oldest", [ids[1], ids[2]]],
      ["single-other", [ids[2]]],
      ["latest-only", []],
    ];
    for (const [name, selected] of states) {
      await select(selected);
      const accuracy = await checkData("[data-overview-chart]", "accuracy");
      const volume = await checkData("[data-overview-volume-chart]", "volume");
      await capture(name, width, height);
      report.at(-1).data = { accuracy, volume };
      await evaluate(
        `document.querySelector('[data-overview-volume-chart]').closest('.frame').scrollIntoView({block:'start'})`,
      );
      await capture(`${name}-volume-context`, width, height);
      await evaluate(
        `document.querySelector('[data-overview-chart]').closest('.frame').scrollIntoView({block:'start'}); document.querySelector('[data-kpis]').scrollIntoView({block:'start'})`,
      );
      await click("[data-vintage-selector-trigger]");
      await waitFor(`!document.querySelector('.vintage-selector').hidden`);
      await capture(`${name}-popover`, width, height);
      if (phase === "after") {
        const colors = await evaluate(
          `(() => Object.fromEntries([...document.querySelectorAll('[data-vintage-option]')].map(n=>[n.value,getComputedStyle(n.nextElementSibling).getPropertyValue('--series-color').trim()])))()`,
        );
        for (const line of accuracy.lines.filter(
          (s) => s.id !== "latest_available",
        )) {
          const hex = colors[line.id];
          const rgb = `rgb(${[1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)).join(", ")})`;
          assert.equal(line.color, rgb, "selector color must match chart");
        }
      }
      await click('[data-vintage-selector-trigger][aria-expanded="true"]');
      for (const kind of ["accuracy", "volume"]) {
        await click(`[data-chart-fullscreen="${kind}"]`);
        await waitFor(
          `!document.querySelector('#overview-chart-dialog').hidden`,
        );
        await checkData(".chart-dialog__body", kind);
        await capture(`${name}-${kind}-fullscreen`, width, height);
        await click('[data-action="overview-fullscreen-close"]');
      }
    }
    for (const guide of ["accuracy-chart", "volume-chart"]) {
      await click(
        `[data-overview-guide="${guide}"][data-action="overview-guide-open"]`,
      );
      await waitFor(`!document.querySelector('#overview-guide-dialog').hidden`);
      await capture(`${guide}-guide`, width, height);
      await click('[data-action="overview-guide-close"]');
    }
  }
  assert.deepEqual(errors, [], "browser runtime errors");
  assert.equal(report.length, 54);
  writeFileSync(`${output}/report.json`, JSON.stringify(report, null, 2));
  console.log(
    `OVERVIEW PROVENANCE ${phase === "after" ? "VALIDATION PASSED" : "BASELINE CAPTURED"}: ${report.length} screenshots`,
  );
} finally {
  socket.close();
}
