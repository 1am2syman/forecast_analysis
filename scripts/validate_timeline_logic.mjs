#!/usr/bin/env node

import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const timeline = require(
  resolve(fileURLToPath(new URL("../dashboard/timeline.js", import.meta.url))),
);
const edgeCasesOnly = process.argv.includes("--edge-cases");

function months(start, count) {
  const startNumber = timeline.monthNumber(start);
  return Array.from({ length: count }, (_, index) =>
    timeline.monthFromNumber(startNumber + index),
  );
}

function validateCore() {
  const available = months("2023-01-01", 36);
  assert.deepEqual(timeline.rangeForPreset(available, 6, "month"), {
    start: "2025-07-01",
    end: "2025-12-01",
  });
  assert.equal(timeline.inclusiveMonthCount("2025-07-01", "2025-12-01"), 6);
  assert.deepEqual(
    timeline.rangeForPreset(available, 12, "quarter", "2025-11-01"),
    { start: "2024-10-01", end: "2025-09-01" },
  );
  assert.equal(timeline.quarterLabel("2025-09-01"), "Q3 2025");
  assert.equal(
    timeline.matchingPreset(available, "2025-01-01", "2025-12-01", "month"),
    12,
  );
  assert.deepEqual(
    timeline.indexRange(available, "2025-03-01", "2025-08-01"),
    { start: 26, end: 31 },
  );
  assert.deepEqual(timeline.rangeFromIndices(available, 26, 31), {
    start: "2025-03-01",
    end: "2025-08-01",
  });
  assert.deepEqual(timeline.moveWindow(available, 12, 17, 3), {
    start: 15,
    end: 20,
  });
  console.log("timeline data correctness validation passed");
}

function validateEdges() {
  assert.deepEqual(
    timeline.normalizeMonths(["bad", "2025-02-01", "2025-01-01", "2025-02-01"]),
    ["2025-01-01", "2025-02-01"],
  );
  assert.deepEqual(
    timeline.rangeForPreset(months("2025-10-01", 3), 12, "month"),
    { start: "2025-10-01", end: "2025-12-01" },
  );
  assert.deepEqual(
    timeline.clampRange(months("2025-01-01", 6), "2025-05-01", "2025-02-01"),
    { start: "2025-02-01", end: "2025-02-01" },
  );
  assert.deepEqual(
    timeline.rangeForPreset(
      months("2024-11-01", 8),
      6,
      "quarter",
      "2025-06-01",
    ),
    { start: "2025-01-01", end: "2025-06-01" },
  );
  assert.equal(
    timeline.latestCompleteQuarterEnd(["2025-01-01", "2025-02-01"], null),
    "2025-02-01",
  );
  assert.equal(timeline.inclusiveMonthCount("2025-03-01", "2025-02-01"), 0);
  assert.deepEqual(timeline.clampRange([], null, null), {
    start: null,
    end: null,
  });
  assert.deepEqual(timeline.rangeFromIndices(["2025-01-01"], 9, -2), {
    start: "2025-01-01",
    end: "2025-01-01",
  });
  assert.deepEqual(timeline.moveWindow(months("2025-01-01", 6), 1, 3, -9), {
    start: 0,
    end: 2,
  });
  assert.deepEqual(timeline.moveWindow(months("2025-01-01", 6), 1, 3, 99), {
    start: 3,
    end: 5,
  });
  assert.deepEqual(
    timeline.rangeForPreset(
      ["2025-01-01", "2025-03-01", "2025-06-01"],
      3,
      "month",
    ),
    { start: "2025-06-01", end: "2025-06-01" },
  );
  console.log("timeline edge-case validation passed");
}

if (edgeCasesOnly) validateEdges();
else validateCore();
