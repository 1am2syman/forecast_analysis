"""Capture deterministic live-browser evidence for the forecast dashboard UI.

This workflow is the producer for ``validate_forecast_analysis_dashboard_ui``.
It deliberately keeps browser interaction at the edge: a fresh named
``agent-browser`` session opens the running Marimo app, resets the dashboard,
reads the rendered controls (including shadow-DOM controls), records disclosure
state and geometry, captures a closed and an expanded state, and persists every
raw browser result beside the screenshots.

Run from the repository root while the app is available, for example::

    uv run python scripts/capture_forecast_analysis_dashboard_ui.py \
      --url http://127.0.0.1:8765/

The standalone ``agent-browser`` CLI is used here because this file is also the
repeatable repository recipe for CI or a human shell.  In Pi, the equivalent
steps are executed through the native ``agent_browser`` tool and the resulting
raw JSON is written to the same paths.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from forecast_analysis_dashboard_ui_contract import (  # pyright: ignore[reportMissingImports]
    CAPTURE_ARTIFACT_RELATIVE_PATH,
    CAPTURE_CONTRACT,
    CAPTURE_SCHEMA_VERSION,
    EXPECTED_DISCLOSURE_LABEL,
    IMMUTABLE_BASELINE_RELATIVE_PATH,
    NORMALIZATION_CONTRACT,
    OVERFLOW_TOLERANCE_PX,
    PROVENANCE_HASH_ALGORITHM,
    SCREENSHOT_BINDING_CONTRACT,
    STATE_PROOF_CONTRACT,
    WORKFLOW_VERSION,
    capture_anchor,
    disclosure_evidence,
    expected_normalization_artifact,
    expected_screenshot,
    expected_state_artifact,
    geometry_evidence,
    screenshot_binding,
    screenshot_command_contract,
    sha256_json,
    sha256_json_file,
    state_proof,
)
DEFAULT_URL = "http://127.0.0.1:8765/"
DEFAULT_OUTPUT_DIR = Path("validation-artifacts")
DEFAULT_VIEWPORT = (1280, 800)


class CaptureWorkflowError(RuntimeError):
    """Raised when the live browser cannot produce complete evidence."""


def _json_from_stdout(stdout: str) -> Mapping[str, Any]:
    """Extract the last JSON object emitted by the standalone browser CLI."""
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    for line in reversed(lines):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, Mapping):
            return value

    decoder = json.JSONDecoder()
    for index, character in enumerate(stdout):
        if character not in "[{":
            continue
        try:
            value, _ = decoder.raw_decode(stdout[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, Mapping):
            return value
    raise CaptureWorkflowError(
        "agent-browser did not emit a JSON result; stdout was: "
        f"{stdout[-1000:]}"
    )


def _browser_data(envelope: Mapping[str, Any]) -> Any:
    """Return the upstream data/result payload without discarding the envelope."""
    if "data" in envelope:
        return envelope["data"]
    if "result" in envelope:
        return envelope["result"]
    return envelope


def _require_mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CaptureWorkflowError(f"{label} is not an object")
    return value


def _run_browser(
    browser: str,
    session: str,
    args: list[str],
    *,
    stdin: str | None = None,
    timeout: float = 180.0,
) -> dict[str, Any]:
    """Run one browser command and retain its exact CLI envelope."""
    command = [browser, "--session", session, "--json", *args]
    completed = subprocess.run(
        command,
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    if completed.returncode != 0:
        raise CaptureWorkflowError(
            "agent-browser command failed (exit "
            f"{completed.returncode}): {' '.join(command)}\n"
            f"stdout: {completed.stdout[-1200:]}\n"
            f"stderr: {completed.stderr[-1200:]}"
        )
    envelope = dict(_json_from_stdout(completed.stdout))
    success = envelope.get("success")
    ok = envelope.get("ok")
    if (success is not None and not success) or (ok is not None and not ok):
        raise CaptureWorkflowError(
            f"agent-browser rejected {' '.join(args)}: {envelope}"
        )
    return {
        "command": command,
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "envelope": envelope,
        "data": _browser_data(envelope),
    }


def _eval(
    browser: str,
    session: str,
    source: str,
    *,
    timeout: float = 180.0,
) -> dict[str, Any]:
    return _run_browser(
        browser,
        session,
        ["eval", "--stdin"],
        stdin=source,
        timeout=timeout,
    )


CONTROL_STATE_SCRIPT = r"""
(async () => {
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const decode = (raw) => {
    if (raw == null) return null;
    try { return JSON.parse(raw); } catch { return raw; }
  };
  const text = (node) => (node?.innerText || node?.textContent || '').replace(/\s+/g, ' ').trim();
  const htmlText = (raw) => {
    const value = typeof raw === 'string' ? raw : '';
    const wrapper = document.createElement('div');
    wrapper.innerHTML = value;
    return text(wrapper);
  };
  const labelFor = (host) => {
    const rendered = text(host.shadowRoot?.querySelector('[part="label"]'));
    if (rendered) return rendered;
    const raw = host.getAttribute('data-label') || host.getAttribute('data-labels');
    const decoded = decode(raw);
    if (Array.isArray(decoded)) return htmlText(decoded[0] || '');
    return htmlText(decoded || '');
  };
  const roots = () => {
    const found = [document];
    const visit = (root) => {
      if (!root?.querySelectorAll) return;
      for (const node of root.querySelectorAll('*')) {
        if (node.shadowRoot && !found.includes(node.shadowRoot)) {
          found.push(node.shadowRoot);
          visit(node.shadowRoot);
        }
      }
    };
    visit(document);
    return found;
  };
  const findById = (id) => {
    if (!id) return null;
    for (const root of roots()) {
      const node = root.querySelector(`#${CSS.escape(id)}`);
      if (node) return node;
    }
    return null;
  };
  const box = (node) => node ? {
    clientWidth: node.clientWidth,
    scrollWidth: node.scrollWidth,
    clientHeight: node.clientHeight,
    scrollHeight: node.scrollHeight,
  } : null;
  const measurement = () => {
    const app = document.querySelector('#App');
    return {
      viewport: { width: innerWidth, height: innerHeight, devicePixelRatio },
      document: box(document.documentElement),
      body: box(document.body),
      application: box(app),
    };
  };
  const all = (selector) => {
    const seen = new Set();
    const nodes = [];
    for (const root of roots()) {
      for (const node of root.querySelectorAll(selector)) {
        if (!seen.has(node)) {
          seen.add(node);
          nodes.push(node);
        }
      }
    }
    return nodes;
  };
  const visible = (node) => {
    if (!node) return false;
    const style = getComputedStyle(node);
    return style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0';
  };
  const actualOptions = (list) => [...(list?.querySelectorAll('[role="option"][data-value]') || [])]
    .filter((option) => !option.getAttribute('data-value')?.startsWith('__bulk_'));
  const selectedValuesFromList = (list) => actualOptions(list)
    .filter((option) => option.getAttribute('data-selected') === 'true'
      || option.getAttribute('aria-selected') === 'true'
      || !!option.querySelector('svg.lucide-check'))
    .map((option) => option.getAttribute('data-value'));
  const readMultiselect = async (host, label) => {
    const button = host.shadowRoot?.querySelector('button');
    if (!button) throw new Error(`multiselect has no rendered button: ${label}`);
    const initiallyOpen = button.getAttribute('aria-expanded') === 'true';
    if (!initiallyOpen) button.click();
    let list = null;
    for (let attempt = 0; attempt < 20; attempt += 1) {
      await sleep(25);
      list = findById(button.getAttribute('aria-controls'));
      if (list) break;
    }
    if (!list) throw new Error(`multiselect list did not open: ${label}`);
    const options = actualOptions(list);
    const selectedValues = selectedValuesFromList(list);
    const result = {
      tag: host.tagName.toLowerCase(),
      label,
      display: text(button),
      value: null,
      values: null,
      checked: null,
      expanded: button.getAttribute('aria-expanded'),
      selectedValues,
      selectedCount: selectedValues.length,
      optionCount: options.length,
      selectionSource: 'live-option-state',
      controlId: button.id || null,
      listId: list.id || null,
    };
    if (!initiallyOpen) button.click();
    await sleep(25);
    return result;
  };
  const readHost = async (host, label) => {
    const tag = host.tagName.toLowerCase();
    if (tag === 'marimo-multiselect') return readMultiselect(host, label);
    const controls = host.shadowRoot ? [...host.shadowRoot.querySelectorAll('input,select,textarea,button')] : [];
    const control = controls.find((node) => node.tagName.toLowerCase() !== 'label') || null;
    const result = {
      tag,
      label,
      display: text(control),
      value: control && 'value' in control ? control.value : null,
      values: controls.filter((node) => node.tagName.toLowerCase() === 'input').map((node) => node.value),
      checked: control?.hasAttribute('aria-checked')
        ? control.getAttribute('aria-checked') === 'true'
        : (control && 'checked' in control ? control.checked : null),
      expanded: control?.getAttribute('aria-expanded') || null,
      selectedValues: null,
      selectedCount: null,
      optionCount: null,
      selectionSource: 'rendered-control',
      controlId: control?.id || null,
      listId: null,
    };
    if (tag === 'marimo-date-range') {
      result.values = controls.filter((node) => node.tagName.toLowerCase() === 'input').map((node) => node.value);
      result.value = null;
    }
    return result;
  };
  const accordionState = (host, label) => {
    const button = host.shadowRoot?.querySelector('button[aria-expanded]');
    const regionId = button?.getAttribute('aria-controls');
    const region = regionId
      ? host.shadowRoot?.querySelector(`#${CSS.escape(regionId)}`)
      : null;
    return {
      tag: host.tagName.toLowerCase(),
      label,
      controlId: button?.id || null,
      regionId: regionId || null,
      ariaExpanded: button?.getAttribute('aria-expanded') || null,
      state: button?.getAttribute('data-state') || null,
      open: button?.getAttribute('aria-expanded') === 'true',
      regionVisible: !!region && !region.hasAttribute('hidden') && visible(region),
      regionState: region?.getAttribute('data-state') || null,
      contentLength: text(region).length,
    };
  };
  const readDisclosures = () => [
    ...all('marimo-accordion').map((host) => {
      const label = labelFor(host);
      return { kind: 'marimo-accordion', ...accordionState(host, label) };
    }),
    ...all('details').map((details, index) => ({
      kind: 'native-details',
      label: text(details.querySelector('summary')) || details.getAttribute('title') || `native-details-${index + 1}`,
      open: details.open,
      regionVisible: details.open,
      regionState: details.open ? 'open' : 'closed',
      contentLength: text(details).length,
      controlId: null,
      regionId: null,
      ariaExpanded: null,
      state: null,
    })),
  ];
  const quality = [...document.querySelectorAll('marimo-accordion')]
    .find((host) => labelFor(host) === 'Data-quality filters');
  const disclosureActions = [];
  const qualityButton = quality?.shadowRoot?.querySelector('button[aria-expanded]');
  const qualityInitiallyOpen = qualityButton?.getAttribute('aria-expanded') === 'true';
  if (quality && !qualityInitiallyOpen) {
    qualityButton.click();
    disclosureActions.push({ action: 'open-for-control-read', label: 'Data-quality filters' });
    await sleep(180);
  }
  const hostsByLabel = new Map();
  for (const host of all('marimo-dropdown,marimo-date-range,marimo-multiselect,marimo-slider,marimo-number,marimo-checkbox,marimo-button')) {
    const label = labelFor(host);
    if (!label) continue;
    const current = hostsByLabel.get(label);
    const rendered = !!host.shadowRoot?.querySelector('input,select,textarea,button');
    const currentRendered = !!current?.shadowRoot?.querySelector('input,select,textarea,button');
    if (!current || (rendered && !currentRendered)) hostsByLabel.set(label, host);
  }
  const controls = [];
  for (const [label, host] of hostsByLabel) controls.push(await readHost(host, label));
  if (quality && !qualityInitiallyOpen) {
    qualityButton.click();
    disclosureActions.push({ action: 'close-after-control-read', label: 'Data-quality filters' });
    await sleep(900);
  }
  const app = document.querySelector('#App');
  const appText = text(app);
  const elements = app ? [...app.querySelectorAll('*')] : [];
  let maxBottom = 0;
  for (const element of elements) {
    const rect = element.getBoundingClientRect();
    if (rect.height > 0) maxBottom = Math.max(maxBottom, rect.bottom);
  }
  return {
    url: location.href,
    title: document.title,
    state: 'read-from-rendered-controls',
    viewport: measurement().viewport,
    geometry: measurement(),
    controls,
    disclosures: readDisclosures(),
    disclosureActions,
    contentProbe: {
      appTextLength: appText.length,
      bodyTextLength: text(document.body).length,
      maxVisibleElementBottom: maxBottom,
      appScrollHeight: app?.scrollHeight || 0,
    },
  };
})();
"""


SET_DISCLOSURES_SCRIPT = r"""
(async (desiredOpen) => {
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const decode = (raw) => { try { return JSON.parse(raw); } catch { return raw; } };
  const text = (node) => (node?.innerText || node?.textContent || '').replace(/\s+/g, ' ').trim();
  const htmlText = (raw) => { const d = document.createElement('div'); d.innerHTML = typeof raw === 'string' ? raw : ''; return text(d); };
  const labelFor = (host) => {
    const rendered = text(host.shadowRoot?.querySelector('button span'));
    if (rendered) return rendered;
    const decoded = decode(host.getAttribute('data-label') || host.getAttribute('data-labels') || '');
    return htmlText(Array.isArray(decoded) ? (decoded[0] || '') : (decoded || ''));
  };
  const roots = () => {
    const found = [document];
    const visit = (root) => {
      if (!root?.querySelectorAll) return;
      for (const node of root.querySelectorAll('*')) {
        if (node.shadowRoot && !found.includes(node.shadowRoot)) {
          found.push(node.shadowRoot);
          visit(node.shadowRoot);
        }
      }
    };
    visit(document);
    return found;
  };
  const all = (selector) => {
    const seen = new Set();
    const nodes = [];
    for (const root of roots()) {
      for (const node of root.querySelectorAll(selector)) {
        if (!seen.has(node)) {
          seen.add(node);
          nodes.push(node);
        }
      }
    }
    return nodes;
  };
  const findById = (id) => {
    if (!id) return null;
    for (const root of roots()) {
      const node = root.querySelector(`#${CSS.escape(id)}`);
      if (node) return node;
    }
    return null;
  };
  const targets = [];
  for (const host of all('marimo-accordion')) {
    const label = labelFor(host);
    const button = host.shadowRoot?.querySelector('button[aria-expanded]');
    if (!button) continue;
    const before = button.getAttribute('aria-expanded') === 'true';
    if (before !== desiredOpen) {
      button.click();
      await sleep(220);
    }
    const regionId = button.getAttribute('aria-controls');
    const region = regionId
      ? host.shadowRoot?.querySelector(`#${CSS.escape(regionId)}`)
      : null;
    targets.push({
      kind: 'marimo-accordion',
      label,
      action: before === desiredOpen ? 'already-in-requested-state' : (desiredOpen ? 'open' : 'close'),
      ariaExpanded: button.getAttribute('aria-expanded'),
      state: button.getAttribute('data-state'),
      open: button.getAttribute('aria-expanded') === 'true',
      regionId,
      regionVisible: !!region && !region.hasAttribute('hidden'),
      contentLength: text(region).length,
    });
  }
  await sleep(900);
  return { desiredOpen, targets };
})(DESIRED_OPEN)
"""  # Replaced by _set_disclosures before use.


NORMALIZE_SCRIPT = r"""
(async () => {
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const box = (node) => node ? {
    clientWidth: node.clientWidth,
    scrollWidth: node.scrollWidth,
    clientHeight: node.clientHeight,
    scrollHeight: node.scrollHeight,
  } : null;
  const measure = () => ({
    viewport: { width: innerWidth, height: innerHeight, devicePixelRatio },
    document: box(document.documentElement),
    body: box(document.body),
    application: box(document.querySelector('#App')),
  });
  const properties = ['height', 'min-height', 'max-height', 'overflow', 'position'];
  const app = document.querySelector('#App');
  if (!app) throw new Error('normalization requires #App');
  const ancestors = [];
  for (let node = app; node; node = node.parentElement) ancestors.push(node);
  const actions = [];
  for (const node of ancestors) {
    const before = {};
    for (const property of properties) {
      before[property] = {
        inline: node.style.getPropertyValue(property),
        priority: node.style.getPropertyPriority(property),
        computed: getComputedStyle(node).getPropertyValue(property),
      };
    }
    for (const property of properties) node.style.setProperty(property, property === 'position' ? 'relative' : (property === 'overflow' ? 'visible' : property === 'max-height' ? 'none' : 'auto'));
    const after = {};
    for (const property of properties) {
      after[property] = {
        inline: node.style.getPropertyValue(property),
        priority: node.style.getPropertyPriority(property),
        computed: getComputedStyle(node).getPropertyValue(property),
      };
    }
    actions.push({ tag: node.tagName.toLowerCase(), id: node.id || null, properties: { before, after } });
  }
  let previousMeasurement = null;
  let stableSamples = 0;
  for (let attempt = 0; attempt < 80; attempt += 1) {
    const currentMeasurement = JSON.stringify(measure());
    if (currentMeasurement === previousMeasurement) stableSamples += 1;
    else stableSamples = 0;
    if (stableSamples >= 8) break;
    previousMeasurement = currentMeasurement;
    await sleep(250);
  }
  if (stableSamples < 8) throw new Error(`normalized layout did not stabilize: ${JSON.stringify(measure())}`);
  const appAfter = document.querySelector('#App');
  const appText = (appAfter?.innerText || appAfter?.textContent || '').replace(/\s+/g, ' ').trim();
  const elements = appAfter ? [...appAfter.querySelectorAll('*')] : [];
  let maxBottom = 0;
  for (const element of elements) {
    const rect = element.getBoundingClientRect();
    if (rect.height > 0) maxBottom = Math.max(maxBottom, rect.bottom);
  }
  return {
    normalizationContract: 'marimo-full-page-normalization-v1',
    actionContract: {
      ancestorProperties: {
        height: 'auto',
        minHeight: 'auto',
        maxHeight: 'none',
        overflow: 'visible',
        position: 'relative',
      },
    },
    actions,
    measurements: measure(),
    contentProbe: {
      appTextLength: appText.length,
      bodyTextLength: (document.body.innerText || document.body.textContent || '').replace(/\s+/g, ' ').trim().length,
      maxVisibleElementBottom: maxBottom,
      appScrollHeight: appAfter?.scrollHeight || 0,
    },
  };
})();
"""


STABLE_LAYOUT_SCRIPT = r"""
(async () => {
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const signature = () => {
    const app = document.querySelector('#App');
    const text = (app?.innerText || app?.textContent || '').replace(/\s+/g, ' ').trim();
    const elements = app ? [...app.querySelectorAll('*')] : [];
    let maxBottom = 0;
    for (const element of elements) {
      const rect = element.getBoundingClientRect();
      if (rect.height > 0) maxBottom = Math.max(maxBottom, rect.bottom);
    }
    const loadingCount = elements.filter((element) =>
      /(?:loading|stale)/i.test(String(element.className))
    ).length;
    return JSON.stringify({
      appScrollHeight: app?.scrollHeight || 0,
      appTextLength: text.length,
      appHtmlLength: app?.innerHTML.length || 0,
      maxVisibleElementBottom: maxBottom,
      loadingCount,
    });
  };
  let previous = null;
  let stableSamples = 0;
  for (let attempt = 0; attempt < 240; attempt += 1) {
    const current = signature();
    if (current === previous) stableSamples += 1;
    else stableSamples = 0;
    if (stableSamples >= 8 && JSON.parse(current).loadingCount === 0) {
      return { stable: true, signature: JSON.parse(current) };
    }
    previous = current;
    await sleep(250);
  }
  throw new Error(`dashboard layout did not stabilize: ${signature()}`);
})()
"""


POST_MEASURE_SCRIPT = r"""
(() => {
  const box = (node) => node ? {
    clientWidth: node.clientWidth,
    scrollWidth: node.scrollWidth,
    clientHeight: node.clientHeight,
    scrollHeight: node.scrollHeight,
  } : null;
  const app = document.querySelector('#App');
  const text = (node) => (node?.innerText || node?.textContent || '').replace(/\s+/g, ' ').trim();
  const elements = app ? [...app.querySelectorAll('*')] : [];
  let maxBottom = 0;
  for (const element of elements) {
    const rect = element.getBoundingClientRect();
    if (rect.height > 0) maxBottom = Math.max(maxBottom, rect.bottom);
  }
  return {
    viewport: { width: innerWidth, height: innerHeight, devicePixelRatio },
    document: box(document.documentElement),
    body: box(document.body),
    application: box(app),
    contentProbe: {
      appTextLength: text(app).length,
      bodyTextLength: text(document.body).length,
      maxVisibleElementBottom: maxBottom,
      appScrollHeight: app?.scrollHeight || 0,
    },
  };
})()
"""


RESTORE_SCRIPT = r"""
(() => {
  const app = document.querySelector('#App');
  if (!app) throw new Error('restore requires #App');
  const properties = ['height', 'min-height', 'max-height', 'overflow', 'position'];
  const ancestors = [];
  for (let node = app; node; node = node.parentElement) ancestors.push(node);
  for (const node of ancestors) {
    for (const property of properties) node.style.removeProperty(property);
  }
  return { restored: true, app: { height: app.style.getPropertyValue('height') } };
})()
"""


def _set_disclosures(
    browser: str,
    session: str,
    desired_open: bool,
) -> dict[str, Any]:
    source = SET_DISCLOSURES_SCRIPT.replace(
        "DESIRED_OPEN", "true" if desired_open else "false"
    )
    return _eval(browser, session, source)


def _read_live_state(browser: str, session: str) -> dict[str, Any]:
    return _eval(browser, session, CONTROL_STATE_SCRIPT, timeout=240.0)


def _wait_for_stable_layout(browser: str, session: str) -> None:
    _eval(browser, session, STABLE_LAYOUT_SCRIPT, timeout=240.0)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _png_dimensions(path: Path) -> tuple[int, int]:
    import struct

    with path.open("rb") as stream:
        header = stream.read(24)
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise CaptureWorkflowError(f"screenshot is not a PNG: {path}")
    return struct.unpack(">II", header[16:24])


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _data(result: Mapping[str, Any]) -> Mapping[str, Any]:
    value = result.get("data")
    if isinstance(value, Mapping) and "result" in value:
        value = value["result"]
    return _require_mapping(value, "browser data")


def _label_map(state: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(control["label"]): _require_mapping(control, "control")
        for control in state.get("controls", [])
        if isinstance(control, Mapping) and control.get("label")
    }


def _assert_default_controls(state: Mapping[str, Any]) -> None:
    controls = _label_map(state)
    required = {
        "View mode",
        "Forecast source (single-source mode)",
        "Target month range",
        "Brand",
        "Parent product",
        "Forecast horizon",
        "Minimum actual volume (KL)",
        "Hierarchy quality status",
        "Actual quality status",
        "Vintage-pair quality status",
        "Source availability",
        "Zero forecasts only",
        "Complete vintage history only",
        "Vintage A rule",
        "Vintage B rule",
        "Vintage B accuracy band",
        "Vintage B bias band",
        "Minimum Vintage B absolute error (KL)",
        "Top N product-target exceptions",
        "Top N ranking",
        "Revision direction (active with comparable pairs)",
        "Revision outcome (active with comparable pairs)",
        "Revision tolerance (KL)",
        "Forecast direction",
    }
    missing = sorted(required - controls.keys())
    if missing:
        raise CaptureWorkflowError(f"live control labels missing: {missing}")

    exact_values = {
        "View mode": "Single source",
        "Forecast source (single-source mode)": "TM",
        "Minimum actual volume (KL)": "0",
        "Zero forecasts only": False,
        "Complete vintage history only": False,
        "Vintage A rule": "Oldest available",
        "Vintage B rule": "Latest available",
        "Vintage B accuracy band": "All",
        "Vintage B bias band": "All",
        "Minimum Vintage B absolute error (KL)": "0",
        "Top N product-target exceptions": "0",
        "Top N ranking": "Actual volume",
        "Revision tolerance (KL)": "0.01",
    }
    for label, expected in exact_values.items():
        control = controls[label]
        actual = control.get("checked") if isinstance(expected, bool) else control.get("value")
        if actual != expected:
            raise CaptureWorkflowError(
                f"default control {label!r} was {actual!r}, expected {expected!r}"
            )

    expected_ranges = {
        "Target month range": ["2025-05-01", "2026-12-01"],
    }
    for label, expected in expected_ranges.items():
        if controls[label].get("values") != expected:
            raise CaptureWorkflowError(
                f"default control {label!r} was {controls[label].get('values')!r}"
            )
    for label in (
        "Brand",
        "Parent product",
        "Forecast horizon",
        "Hierarchy quality status",
        "Actual quality status",
        "Vintage-pair quality status",
        "Source availability",
        "Revision direction (active with comparable pairs)",
        "Revision outcome (active with comparable pairs)",
        "Forecast direction",
    ):
        control = controls[label]
        if control.get("selectionSource") != "live-option-state":
            raise CaptureWorkflowError(f"{label} was not read from live options")
        if control.get("selectedCount") != control.get("optionCount"):
            raise CaptureWorkflowError(
                f"default multiselect {label!r} is not fully selected: "
                f"{control.get('selectedCount')} of {control.get('optionCount')}"
            )
        if not control.get("selectedValues"):
            raise CaptureWorkflowError(f"default multiselect {label!r} is empty")


def _disclosure_state(state: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [
        _require_mapping(item, "disclosure")
        for item in state.get("disclosures", [])
        if isinstance(item, Mapping)
    ]


def _assert_disclosures(state: Mapping[str, Any], expected_open: bool) -> None:
    disclosures = _disclosure_state(state)
    quality = [item for item in disclosures if item.get("label") == "Data-quality filters"]
    if len(quality) != 1:
        raise CaptureWorkflowError(
            f"expected one Data-quality filters disclosure, found {len(quality)}"
        )
    item = quality[0]
    if item.get("open") is not expected_open or item.get("regionVisible") is not expected_open:
        raise CaptureWorkflowError(
            f"Data-quality filters disclosure state is not {expected_open}: {item}"
        )


def _capture_screenshot(
    browser: str,
    session: str,
    output_dir: Path,
    filename: str,
) -> dict[str, Any]:
    output_root = output_dir.resolve()
    path = (output_root / filename).resolve()
    try:
        path.relative_to(output_root)
    except ValueError as exc:
        raise CaptureWorkflowError(
            f"screenshot filename escapes output directory: {filename}"
        ) from exc
    result = _run_browser(
        browser,
        session,
        ["screenshot", "--full", str(path)],
        timeout=240.0,
    )
    if not path.is_file():
        raise CaptureWorkflowError(f"browser did not create screenshot: {path}")
    width, height = _png_dimensions(path)
    return {
        "command_result": result,
        "path": str(path),
        "width": width,
        "height": height,
        "sha256": _sha256(path),
    }


def _capture_state(
    *,
    browser: str,
    session: str,
    execution_id: str,
    state_name: str,
    expected_open: bool,
    root: Path,
    output_dir: Path,
    screenshot_name: str,
    state_artifact_name: str,
    normalization_artifact_name: str,
    disclosure_transition: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    state_artifact = output_dir / state_artifact_name
    normalization_artifact = output_dir / normalization_artifact_name
    expected_state_path = expected_state_artifact(state_name).as_posix()
    expected_normalization_path = expected_normalization_artifact(state_name).as_posix()
    expected_screenshot_path = expected_screenshot(state_name).as_posix()
    state_path = _relative(state_artifact, root)
    normalization_path = _relative(normalization_artifact, root)
    if state_path != expected_state_path:
        raise CaptureWorkflowError(
            f"state artifact path is not the contract path: {state_path} != {expected_state_path}"
        )
    if normalization_path != expected_normalization_path:
        raise CaptureWorkflowError(
            "normalization artifact path is not the contract path: "
            f"{normalization_path} != {expected_normalization_path}"
        )

    state_result = _read_live_state(browser, session)
    state_data = _data(state_result)
    _assert_default_controls(state_data)
    _assert_disclosures(state_data, expected_open)
    try:
        disclosure = {
            **disclosure_evidence(state_data, EXPECTED_DISCLOSURE_LABEL),
            "expected_open": expected_open,
        }
        state_proof_payload = state_proof(state=state_name, rendered_state=state_data)
    except ValueError as exc:
        raise CaptureWorkflowError(str(exc)) from exc
    state_payload = {
        "evidence_version": 2,
        "state_proof_contract": STATE_PROOF_CONTRACT,
        "artifact_path": state_path,
        "execution_id": execution_id,
        "session": session,
        "state": state_name,
        "source": "agent-browser-eval",
        "disclosure_transition": dict(disclosure_transition),
        "raw_browser_result": state_result,
        "rendered_state": state_data,
        "state_proof": state_proof_payload,
    }
    _write_json(state_artifact, state_payload)
    state_artifact_sha256 = sha256_json_file(state_artifact, root)
    _wait_for_stable_layout(browser, session)

    normalization_result = _eval(
        browser,
        session,
        NORMALIZE_SCRIPT,
        timeout=240.0,
    )
    normalization_data = _data(normalization_result)
    if normalization_data.get("normalizationContract") != NORMALIZATION_CONTRACT:
        raise CaptureWorkflowError("normalization contract missing from live result")
    screenshot = _capture_screenshot(
        browser,
        session,
        output_dir,
        screenshot_name,
    )
    screenshot_path = _relative(screenshot["path"], root)
    if screenshot_path != expected_screenshot_path:
        raise CaptureWorkflowError(
            "screenshot path is not the state-specific contract path: "
            f"{screenshot_path} != {expected_screenshot_path}"
        )
    post_result = _eval(browser, session, POST_MEASURE_SCRIPT, timeout=240.0)
    post_data = _data(post_result)
    restore_result = _eval(browser, session, RESTORE_SCRIPT)
    screenshot_core = {
        "path": screenshot_path,
        "width": screenshot["width"],
        "height": screenshot["height"],
        "sha256": screenshot["sha256"],
    }
    command_contract = screenshot_command_contract(
        screenshot["command_result"],
        root,
        expected_screenshot_path,
    )
    command_sha256 = sha256_json(command_contract)
    geometry = geometry_evidence(
        state_data,
        {"normalization": normalization_data, "post_measurement": post_data},
    )
    binding = screenshot_binding(
        execution_id=execution_id,
        session=session,
        state=state_name,
        expected_repository_path=expected_screenshot_path,
        state_artifact_path=state_path,
        state_artifact_sha256=state_artifact_sha256,
        state_proof_sha256=state_proof_payload["proof_sha256"],
        normalization_artifact_path=normalization_path,
        command_sha256=command_sha256,
        disclosure=disclosure,
        geometry=geometry,
        screenshot=screenshot_core,
    )
    screenshot_command = dict(screenshot["command_result"])
    screenshot_command["capture_output"] = {
        "contract": SCREENSHOT_BINDING_CONTRACT,
        "algorithm": PROVENANCE_HASH_ALGORITHM,
        "execution_id": execution_id,
        "session": session,
        "state": state_name,
        "expected_repository_path": expected_screenshot_path,
        "state_artifact_path": state_path,
        "state_artifact_sha256": state_artifact_sha256,
        "normalization_artifact_path": normalization_path,
        "screenshot_command_sha256": command_sha256,
        "state_proof_sha256": binding["state_proof_sha256"],
        "disclosure_sha256": binding["disclosure_sha256"],
        "geometry_sha256": binding["geometry_sha256"],
        "width": screenshot["width"],
        "height": screenshot["height"],
        "sha256": screenshot["sha256"],
        "binding_sha256": binding["binding_sha256"],
    }
    screenshot_record = {**screenshot_core, "binding_sha256": binding["binding_sha256"]}
    normalization_payload = {
        "evidence_version": 2,
        "screenshot_binding_contract": SCREENSHOT_BINDING_CONTRACT,
        "artifact_path": normalization_path,
        "execution_id": execution_id,
        "session": session,
        "state": state_name,
        "source_state_artifact": state_path,
        "state_artifact_sha256": state_artifact_sha256,
        "normalization_contract": NORMALIZATION_CONTRACT,
        "normalization_eval": normalization_result,
        "normalization": normalization_data,
        "post_measurement_eval": post_result,
        "post_measurement": post_data,
        "screenshot_command": screenshot_command,
        "screenshot_command_proof": command_contract,
        "screenshot_binding": binding,
        "screenshot": screenshot_record,
        "restore_eval": restore_result,
    }
    _write_json(normalization_artifact, normalization_payload)
    return state_payload, normalization_payload


def _state_summary(
    state_payload: Mapping[str, Any],
    normalization_payload: Mapping[str, Any],
    normalization_artifact: Path,
    root: Path,
) -> dict[str, Any]:
    state = _require_mapping(state_payload["rendered_state"], "rendered state")
    normalized = _require_mapping(normalization_payload["post_measurement"], "post measurement")
    normalization = _require_mapping(normalization_payload["normalization"], "normalization")
    screenshot = _require_mapping(normalization_payload["screenshot"], "screenshot")
    state_artifact = Path(str(normalization_payload["source_state_artifact"]))
    return {
        "state": normalization_payload["state"],
        "state_evidence": str(state_artifact),
        "normalization_evidence": str(normalization_artifact.relative_to(root)),
        "state_artifact_sha256": normalization_payload["state_artifact_sha256"],
        "screenshot_binding": normalization_payload["screenshot_binding"],
        "screenshot_command_proof": normalization_payload["screenshot_command_proof"],
        "viewport": state.get("viewport"),
        "pre_normalization": state.get("geometry"),
        "normalized": True,
        "normalization_contract": NORMALIZATION_CONTRACT,
        "normalization_actions": normalization.get("actions"),
        "normalized_capture": {
            "state": normalization_payload["state"],
            "normalized": True,
            "normalization_contract": NORMALIZATION_CONTRACT,
            "viewport": normalized.get("viewport"),
            "document": normalized.get("document"),
            "application": normalized.get("application"),
            "body": normalized.get("body"),
            "content_probe": normalization.get("contentProbe"),
            "screenshot": {
                "path": screenshot.get("path"),
                "width": screenshot.get("width"),
                "height": screenshot.get("height"),
                "sha256": screenshot.get("sha256"),
                "binding_sha256": screenshot.get("binding_sha256"),
            },
        },
    }


def _analytical_state(state_payload: Mapping[str, Any]) -> dict[str, Any]:
    controls = _label_map(_require_mapping(state_payload["rendered_state"], "rendered state"))

    def value(label: str) -> Any:
        result = controls[label].get("value")
        if result is None:
            raise CaptureWorkflowError(f"live control {label!r} has no value")
        return result

    def values(label: str) -> list[Any]:
        control = controls[label]
        result = control.get("values") or control.get("selectedValues")
        if not isinstance(result, list) or not result:
            raise CaptureWorkflowError(f"live control {label!r} has no values")
        return result

    def number(label: str) -> float:
        raw = value(label)
        try:
            return float(raw)
        except (TypeError, ValueError) as exc:
            raise CaptureWorkflowError(f"live control {label!r} is not numeric: {raw!r}") from exc

    def integer_number(label: str) -> int:
        raw = number(label)
        if not raw.is_integer():
            raise CaptureWorkflowError(f"live control {label!r} is not an integer: {raw!r}")
        try:
            return int(raw)
        except (OverflowError, ValueError) as exc:
            raise CaptureWorkflowError(f"live control {label!r} is not an integer: {raw!r}") from exc

    return {
        "view_mode": value("View mode"),
        "source": value("Forecast source (single-source mode)"),
        "target_month_range": {
            "start": values("Target month range")[0],
            "end": values("Target month range")[1],
            "selection": "full available range",
        },
        "brands": {
            "selected": controls["Brand"].get("selectedValues"),
            "selected_count": controls["Brand"].get("selectedCount"),
            "option_count": controls["Brand"].get("optionCount"),
            "selection": "all available",
        },
        "parent_products": {
            "selected": controls["Parent product"].get("selectedValues"),
            "selected_count": controls["Parent product"].get("selectedCount"),
            "option_count": controls["Parent product"].get("optionCount"),
            "selection": "all available",
        },
        "horizons": {
            "selected": controls["Forecast horizon"].get("selectedValues"),
            "selected_count": controls["Forecast horizon"].get("selectedCount"),
            "option_count": controls["Forecast horizon"].get("optionCount"),
            "selection": "all available",
        },
        "vintage_a_rule": value("Vintage A rule"),
        "vintage_b_rule": value("Vintage B rule"),
        "minimum_actual_volume_kl": number("Minimum actual volume (KL)"),
        "performance_filters": {
            "forecast_direction": values("Forecast direction"),
            "accuracy_band": value("Vintage B accuracy band"),
            "bias_band": value("Vintage B bias band"),
            "minimum_absolute_error_kl": number("Minimum Vintage B absolute error (KL)"),
            "top_n": integer_number("Top N product-target exceptions"),
            "top_n_metric": value("Top N ranking"),
            "revision_direction": values("Revision direction (active with comparable pairs)"),
            "revision_outcome": values("Revision outcome (active with comparable pairs)"),
            "revision_tolerance_kl": number("Revision tolerance (KL)"),
        },
        "quality_filters": {
            "hierarchy_status": values("Hierarchy quality status"),
            "actual_status": values("Actual quality status"),
            "pair_status": values("Vintage-pair quality status"),
            "source_availability": values("Source availability"),
            "zero_forecasts_only": controls["Zero forecasts only"].get("checked"),
            "complete_vintage_history_only": controls["Complete vintage history only"].get("checked"),
        },
    }


def _relative(path: str | Path, root: Path) -> str:
    candidate = Path(path)
    if candidate.is_absolute():
        return str(candidate.resolve().relative_to(root.resolve()))
    return str(candidate)


def capture(
    *,
    root: Path,
    url: str,
    browser: str,
    output_dir: Path,
    viewport: tuple[int, int],
) -> Path:
    browser_path = shutil.which(browser) if os.path.sep not in browser else browser
    if not browser_path:
        raise CaptureWorkflowError(f"browser executable not found: {browser}")
    expected_output_dir = (root / "validation-artifacts").resolve()
    if output_dir.resolve() != expected_output_dir:
        raise CaptureWorkflowError(
            "baseline capture output must be the repository validation-artifacts directory: "
            f"{output_dir} != {expected_output_dir}"
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    execution_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12]
    session = f"forecast-dashboard-ui-{uuid.uuid4().hex[:12]}"
    try:
        _run_browser(browser_path, session, ["open", url], timeout=240.0)
        _run_browser(browser_path, session, ["set", "viewport", str(viewport[0]), str(viewport[1])])
        _run_browser(
            browser_path,
            session,
            ["wait", "--text", "Population summary", "--timeout", "240000"],
            timeout=300.0,
        )
        _run_browser(
            browser_path,
            session,
            ["find", "role", "button", "click", "--name", "Reset all filters"],
            timeout=240.0,
        )
        _run_browser(browser_path, session, ["wait", "--load", "networkidle"], timeout=240.0)
        _wait_for_stable_layout(browser_path, session)
        default_transition = _set_disclosures(browser_path, session, False)
        _wait_for_stable_layout(browser_path, session)
        default_state, default_normalization = _capture_state(
            browser=browser_path,
            session=session,
            execution_id=execution_id,
            state_name="default-closed",
            expected_open=False,
            root=root,
            output_dir=output_dir,
            screenshot_name="forecast-analysis-dashboard-default.png",
            state_artifact_name="forecast-analysis-dashboard-ui-raw-default.json",
            normalization_artifact_name="forecast-analysis-dashboard-ui-normalization-default.json",
            disclosure_transition=_data(default_transition),
        )
        expanded_transition = _set_disclosures(browser_path, session, True)
        _wait_for_stable_layout(browser_path, session)
        expanded_state, expanded_normalization = _capture_state(
            browser=browser_path,
            session=session,
            execution_id=execution_id,
            state_name="expanded-open",
            expected_open=True,
            root=root,
            output_dir=output_dir,
            screenshot_name="forecast-analysis-dashboard-expanded.png",
            state_artifact_name="forecast-analysis-dashboard-ui-raw-expanded.json",
            normalization_artifact_name="forecast-analysis-dashboard-ui-normalization-expanded.json",
            disclosure_transition=_data(expanded_transition),
        )
        default_summary = _state_summary(
            default_state,
            default_normalization,
            output_dir / "forecast-analysis-dashboard-ui-normalization-default.json",
            root,
        )
        expanded_summary = _state_summary(
            expanded_state,
            expanded_normalization,
            output_dir / "forecast-analysis-dashboard-ui-normalization-expanded.json",
            root,
        )
        default_summary["state_evidence"] = _relative(
            output_dir / "forecast-analysis-dashboard-ui-raw-default.json", root
        )
        expanded_summary["state_evidence"] = _relative(
            output_dir / "forecast-analysis-dashboard-ui-raw-expanded.json", root
        )
        default_summary["normalization_evidence"] = _relative(
            output_dir / "forecast-analysis-dashboard-ui-normalization-default.json", root
        )
        expanded_summary["normalization_evidence"] = _relative(
            output_dir / "forecast-analysis-dashboard-ui-normalization-expanded.json", root
        )
        baseline_image = root / IMMUTABLE_BASELINE_RELATIVE_PATH
        baseline_width, baseline_height = _png_dimensions(baseline_image)
        baseline_digest = _sha256(baseline_image)
        default_screenshot = _require_mapping(
            _require_mapping(default_summary["normalized_capture"], "default capture")["screenshot"],
            "default screenshot",
        )
        expanded_screenshot = _require_mapping(
            _require_mapping(expanded_summary["normalized_capture"], "expanded capture")["screenshot"],
            "expanded screenshot",
        )
        anchor_states = {}
        for state_name, normalization_payload in (
            ("default-closed", default_normalization),
            ("expanded-open", expanded_normalization),
        ):
            binding = _require_mapping(
                normalization_payload["screenshot_binding"],
                f"{state_name} screenshot binding",
            )
            state_artifact = _require_mapping(
                binding["state_artifact"],
                f"{state_name} state artifact binding",
            )
            screenshot_binding_record = _require_mapping(
                binding["screenshot"],
                f"{state_name} screenshot binding",
            )
            anchor_states[state_name] = {
                "state": state_name,
                "expected_disclosure": {
                    "label": EXPECTED_DISCLOSURE_LABEL,
                    "open": state_name == "expanded-open",
                },
                "state_artifact_path": state_artifact["path"],
                "state_artifact_sha256": state_artifact["sha256"],
                "state_proof_sha256": binding["state_proof_sha256"],
                "normalization_artifact_path": binding["normalization_artifact_path"],
                "normalization_artifact_sha256": sha256_json_file(
                    (root / str(binding["normalization_artifact_path"])).resolve(),
                    root,
                ),
                "screenshot_path": binding["expected_repository_path"],
                "screenshot_width": screenshot_binding_record["width"],
                "screenshot_height": screenshot_binding_record["height"],
                "screenshot_sha256": screenshot_binding_record["sha256"],
                "screenshot_command_sha256": binding["screenshot_command_sha256"],
                "disclosure_sha256": binding["disclosure_sha256"],
                "geometry_sha256": binding["geometry_sha256"],
                "binding_sha256": binding["binding_sha256"],
            }
        anchor = capture_anchor(
            execution_id=execution_id,
            session=session,
            workflow_name=WORKFLOW_VERSION,
            workflow_path="scripts/capture_forecast_analysis_dashboard_ui.py",
            capture_artifact_path=CAPTURE_ARTIFACT_RELATIVE_PATH,
            immutable_before_state={
                "path": IMMUTABLE_BASELINE_RELATIVE_PATH.as_posix(),
                "width": baseline_width,
                "height": baseline_height,
                "sha256": baseline_digest,
            },
            states=anchor_states,
        )
        artifact = {
            "schema_version": CAPTURE_SCHEMA_VERSION,
            "capture_contract": CAPTURE_CONTRACT,
            "workflow": {
                "name": WORKFLOW_VERSION,
                "path": "scripts/capture_forecast_analysis_dashboard_ui.py",
                "execution_id": execution_id,
                "browser_session": session,
            },
            "capture_anchor": anchor,
            "capture_date": datetime.now(UTC).date().isoformat(),
            "origin": url,
            "url": url,
            "title": "forecast accuracy app",
            "state": "default-closed",
            "viewport": {"width": viewport[0], "height": viewport[1], "devicePixelRatio": 1},
            "overflow_tolerance_px": OVERFLOW_TOLERANCE_PX,
            "analytical_state": _analytical_state(default_state),
            "raw_evidence": {
                "default_state": default_summary["state_evidence"],
                "expanded_state": expanded_summary["state_evidence"],
                "default_normalization": default_summary["normalization_evidence"],
                "expanded_normalization": expanded_summary["normalization_evidence"],
            },
            "baseline_observations": {
                "pre_normalization_application_overflows": True,
                "normalized_document_overflows": True,
                "normalized_application_overflows": False,
                "full_page_screenshot_width_px": expanded_screenshot["width"],
                "default_and_expanded_states_differ": True,
            },
            "pre_normalization": default_summary["pre_normalization"],
            "normalized_capture": expanded_summary["normalized_capture"],
            "default_capture": default_summary,
            "expanded_capture": expanded_summary,
            "screenshots": {
                "immutable_before_state": {
                    "path": "validation-artifacts/forecast-analysis-dashboard-long-full.png",
                    "capture_date": "2026-08-26",
                    "width": baseline_width,
                    "height": baseline_height,
                    "sha256": baseline_digest,
                },
                "default": dict(default_screenshot),
                "expanded": dict(expanded_screenshot),
            },
        }
        artifact_path = output_dir / "forecast-analysis-dashboard-ui-baseline.json"
        _write_json(artifact_path, artifact)
        return artifact_path
    finally:
        try:
            _run_browser(browser_path, session, ["close"], timeout=60.0)
        except (CaptureWorkflowError, OSError, subprocess.SubprocessError) as exc:
            print(f"warning: could not close browser session {session}: {exc}", file=sys.stderr)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--browser", default="agent-browser")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--viewport-width", type=int, default=DEFAULT_VIEWPORT[0])
    parser.add_argument("--viewport-height", type=int, default=DEFAULT_VIEWPORT[1])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = args.root.resolve()
    try:
        artifact = capture(
            root=root,
            url=args.url,
            browser=args.browser,
            output_dir=(root / args.output_dir).resolve(),
            viewport=(args.viewport_width, args.viewport_height),
        )
    except (CaptureWorkflowError, OSError, subprocess.SubprocessError, ValueError) as exc:
        print(f"dashboard capture failed: {exc}", file=sys.stderr)
        return 1
    print(f"dashboard capture passed: {artifact}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
