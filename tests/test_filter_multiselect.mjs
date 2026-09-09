#!/usr/bin/env node

import assert from "node:assert/strict";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const {
  fuzzyScore,
  rankOptions,
} = require("../dashboard/filter-multiselect.js");

const options = [
  { value: "brand-a", label: "Brand A" },
  { value: "brand-b", label: "Brand B", disabled: true },
  { value: "unclassified", label: "Unclassified" },
  {
    value: 703584,
    label: "703584 · PCNO ADV 300ml FT",
    searchText: "703584 PCNO ADV 300ml FT",
  },
];

assert.ok(fuzzyScore("brnd a", "Brand A") > 0, "one typo should match");
assert.equal(fuzzyScore("brnd a", "Brand B"), null, "all tokens must match");
assert.ok(
  fuzzyScore("unclass", "Unclassified") > 0,
  "partial token should match",
);
assert.ok(
  fuzzyScore("3584", "703584 PCNO ADV 300ml FT") > 0,
  "partial code should match",
);
assert.equal(fuzzyScore("cooling", "703584 PCNO ADV 300ml FT"), null);

assert.deepEqual(
  rankOptions(options, "brnd a").map((option) => option.value),
  ["brand-a"],
);
assert.deepEqual(
  rankOptions(options, "3584").map((option) => option.value),
  [703584],
);
assert.equal(
  rankOptions(options, "brand b")[0].disabled,
  true,
  "fuzzy search should preserve unavailable-option state for rendering",
);

const availabilityOptions = [
  { value: "disabled-a", label: "Alpha", disabled: true },
  { value: "enabled-z", label: "Zulu" },
  { value: "enabled-b", label: "Beta" },
  { value: "disabled-g", label: "Gamma", disabled: true },
];
assert.deepEqual(
  rankOptions(availabilityOptions, "").map((option) => option.value),
  ["enabled-b", "enabled-z", "disabled-a", "disabled-g"],
  "applicable options should appear before unavailable options",
);
assert.deepEqual(
  rankOptions(
    [
      { value: "disabled-lp", label: "BPCNO LP", disabled: true },
      { value: "enabled-sp", label: "BPCNO SP" },
    ],
    "bpcno",
  ).map((option) => option.value),
  ["enabled-sp", "disabled-lp"],
  "search relevance should rank within availability groups",
);

process.stdout.write("filter multiselect fuzzy matcher passed\n");
