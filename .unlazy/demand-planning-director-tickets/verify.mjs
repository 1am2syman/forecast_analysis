import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";

const mode = process.argv[2];
const root = process.cwd();

function parseJson(text, source) {
  try {
    return JSON.parse(text);
  } catch (error) {
    throw new Error(`Invalid JSON in ${source}: ${error.message}`, {
      cause: error,
    });
  }
}

const definitions = parseJson(
  readFileSync(
    `${root}/.unlazy/demand-planning-director-tickets/definitions.json`,
    "utf8",
  ),
  "definitions.json",
);
const manifest = parseJson(
  readFileSync(
    `${root}/.unlazy/demand-planning-director-tickets/manifest.json`,
    "utf8",
  ),
  "manifest.json",
);

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function ghJson(args) {
  const result = spawnSync("gh", args, {
    cwd: root,
    encoding: "utf8",
    maxBuffer: 10 * 1024 * 1024,
  });
  if (result.status !== 0) {
    throw new Error(
      `gh ${args.join(" ")} failed: ${result.stderr || result.stdout}`,
    );
  }
  return parseJson(result.stdout, `gh ${args.join(" ")}`);
}

function getIssue(record) {
  return ghJson([
    "issue",
    "view",
    String(record.number),
    "--json",
    "number,title,body,state,labels,url",
  ]);
}

function verifyCount() {
  assert(
    definitions.length === 24,
    `Expected 24 definitions, got ${definitions.length}`,
  );
  assert(
    manifest.issues.length === 24,
    `Expected 24 published issues, got ${manifest.issues.length}`,
  );
  const indexes = new Set(manifest.issues.map((issue) => issue.index));
  assert(indexes.size === 24, "Published issue indexes are not unique");
  for (let index = 1; index <= 24; index += 1) {
    assert(indexes.has(index), `Missing published issue index ${index}`);
  }
  console.log("TICKET COUNT PASSED");
}

function verifyShape() {
  for (const record of manifest.issues) {
    const issue = getIssue(record);
    assert(issue.state === "OPEN", `#${issue.number} is not open`);
    for (const heading of [
      "## What to build",
      "## Acceptance criteria",
      "## Blocked by",
    ]) {
      assert(
        issue.body.includes(heading),
        `#${issue.number} missing ${heading}`,
      );
    }
    const labels = new Set(issue.labels.map((label) => label.name));
    assert(
      labels.has("enhancement"),
      `#${issue.number} missing enhancement label`,
    );
    assert(
      labels.has("ready-for-agent"),
      `#${issue.number} missing ready-for-agent label`,
    );
    assert(
      (issue.body.match(/- \[ \]/g) || []).length >= 2,
      `#${issue.number} has too few acceptance criteria`,
    );
  }
  console.log("TICKET SHAPE PASSED");
}

function verifyEdges() {
  const byIndex = new Map(manifest.issues.map((issue) => [issue.index, issue]));
  for (const record of manifest.issues) {
    const issue = getIssue(record);
    const definition = definitions.find((item) => item.index === record.index);
    assert(definition, `Missing definition for issue index ${record.index}`);
    assert(
      JSON.stringify(record.blockedByIndexes) ===
        JSON.stringify(definition.blockedBy),
      `Blocker manifest mismatch for #${record.number}`,
    );
    for (const blockerIndex of definition.blockedBy) {
      const blocker = byIndex.get(blockerIndex);
      assert(
        blocker,
        `#${record.number} references unpublished blocker index ${blockerIndex}`,
      );
      assert(
        blocker.number < record.number,
        `#${record.number} blocker #${blocker.number} was not published first`,
      );
      assert(
        issue.body.includes(`#${blocker.number}`),
        `#${record.number} body omits blocker #${blocker.number}`,
      );
      const edge = record.nativeDependencyEdges.find(
        (item) => item.blockerIndex === blockerIndex,
      );
      assert(
        edge,
        `#${record.number} has no recorded dependency result for blocker ${blockerIndex}`,
      );
      assert(
        edge.created || edge.fallback,
        `#${record.number} has neither native edge nor text fallback`,
      );
    }
    if (definition.blockedBy.length === 0) {
      assert(
        issue.body.includes("None — can start immediately"),
        `#${record.number} missing no-blocker declaration`,
      );
    }
  }
  console.log("TICKET EDGES PASSED");
}

function normalizeTitle(title) {
  return title
    .replace(/^\[Director review\]\s*/i, "")
    .replace(/^\d+\s*[—-]\s*/, "")
    .trim()
    .toLowerCase();
}

function verifyUniqueness() {
  const all = ghJson([
    "issue",
    "list",
    "--state",
    "all",
    "--limit",
    "200",
    "--json",
    "number,title",
  ]);
  const titleGroups = new Map();
  for (const issue of all) {
    const normalized = normalizeTitle(issue.title);
    const group = titleGroups.get(normalized) || [];
    group.push(issue.number);
    titleGroups.set(normalized, group);
  }
  for (const record of manifest.issues) {
    const group = titleGroups.get(normalizeTitle(record.title));
    assert(
      group?.length === 1 && group[0] === record.number,
      `Duplicate normalized title for #${record.number}`,
    );
  }
  const preExisting = all
    .filter((issue) => issue.number <= 2)
    .map((issue) => normalizeTitle(issue.title));
  for (const record of manifest.issues) {
    assert(
      !preExisting.includes(normalizeTitle(record.title)),
      `#${record.number} duplicates a pre-existing dashboard issue`,
    );
  }
  console.log("TICKET UNIQUENESS PASSED");
}

function verifyUrls() {
  for (const record of manifest.issues) {
    assert(
      /^https:\/\/github\.com\/1am2syman\/forecast_analysis\/issues\/\d+$/.test(
        record.url,
      ),
      `Invalid URL for index ${record.index}`,
    );
    const issue = getIssue(record);
    assert(
      issue.url === record.url,
      `Manifest URL mismatch for #${record.number}`,
    );
    for (const edge of record.nativeDependencyEdges) {
      assert(
        edge.created || edge.fallback === "Blocked by section in issue body",
        `Unrecorded dependency fallback for #${record.number}`,
      );
    }
  }
  console.log("TICKET URLS PASSED");
}

const checks = {
  count: verifyCount,
  shape: verifyShape,
  edges: verifyEdges,
  uniqueness: verifyUniqueness,
  urls: verifyUrls,
};
assert(checks[mode], `Unknown verification mode: ${mode}`);
checks[mode]();
