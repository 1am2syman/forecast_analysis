import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { spawnSync } from "node:child_process";

const root = process.cwd();
const definitionsPath = `${root}/.unlazy/demand-planning-director-tickets/definitions.json`;
const manifestPath = `${root}/.unlazy/demand-planning-director-tickets/manifest.json`;
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
  readFileSync(definitionsPath, "utf8"),
  definitionsPath,
);
const manifest = existsSync(manifestPath)
  ? parseJson(readFileSync(manifestPath, "utf8"), manifestPath)
  : { repository: "1am2syman/forecast_analysis", issues: [] };

function gh(args, { allowFailure = false } = {}) {
  const result = spawnSync("gh", args, {
    cwd: root,
    encoding: "utf8",
    maxBuffer: 10 * 1024 * 1024,
  });
  if (result.status !== 0 && !allowFailure) {
    throw new Error(
      `gh ${args.join(" ")} failed\n${result.stdout || ""}${result.stderr || ""}`,
    );
  }
  return result;
}

function saveManifest() {
  writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
}

function issueForIndex(index) {
  return manifest.issues.find((issue) => issue.index === index);
}

function bodyFor(definition) {
  const blockers = definition.blockedBy.length
    ? definition.blockedBy
        .map((index) => {
          const blocker = issueForIndex(index);
          if (!blocker) throw new Error(`Missing blocker ${index}`);
          return `- #${blocker.number} — ${blocker.title}`;
        })
        .join("\n")
    : "- None — can start immediately.";

  return `## What to build\n\n${definition.what}\n\n## Acceptance criteria\n\n${definition.criteria.map((criterion) => `- [ ] ${criterion}`).join("\n")}\n\n## Blocked by\n\n${blockers}\n\n---\n\nSource: \`docs/demand-planning-director-dashboard-review.md\``;
}

const labelResult = gh([
  "label",
  "create",
  "ready-for-agent",
  "--description",
  "Scoped and ready for an implementation agent",
  "--color",
  "0E8A16",
  "--force",
]);
if (labelResult.stdout.trim()) console.log(labelResult.stdout.trim());

const pending = new Map(
  definitions.map((definition) => [definition.index, definition]),
);
const publicationOrder = [];
while (pending.size) {
  const ready = [...pending.values()].filter((definition) =>
    definition.blockedBy.every((index) => !pending.has(index)),
  );
  if (!ready.length) {
    throw new Error(
      `Ticket dependency cycle: ${[...pending.keys()].join(", ")}`,
    );
  }
  ready.sort((a, b) => a.index - b.index);
  for (const definition of ready) {
    publicationOrder.push(definition);
    pending.delete(definition.index);
  }
}

for (const definition of publicationOrder) {
  const existing = issueForIndex(definition.index);
  if (existing) {
    console.log(`Reusing #${existing.number}: ${existing.title}`);
    continue;
  }

  const title = definition.title;
  const body = bodyFor(definition);
  const created = gh([
    "issue",
    "create",
    "--title",
    title,
    "--body",
    body,
    "--label",
    "enhancement",
    "--label",
    "ready-for-agent",
  ]);
  const url = created.stdout.trim();
  const number = Number(url.split("/").pop());
  const api = gh([
    "api",
    `repos/${manifest.repository}/issues/${number}`,
    "--jq",
    "{id: .id, number: .number, html_url: .html_url}",
  ]);
  const details = parseJson(api.stdout, `GitHub issue ${number} response`);
  const record = {
    index: definition.index,
    number,
    databaseId: details.id,
    title,
    url: details.html_url,
    blockedByIndexes: definition.blockedBy,
    blockedByIssues: definition.blockedBy.map(
      (index) => issueForIndex(index).number,
    ),
    nativeDependencyEdges: [],
  };
  manifest.issues.push(record);
  saveManifest();

  for (const blockerIndex of definition.blockedBy) {
    const blocker = issueForIndex(blockerIndex);
    const dependency = gh(
      [
        "api",
        "--method",
        "POST",
        `repos/${manifest.repository}/issues/${number}/dependencies/blocked_by`,
        "-F",
        `issue_id=${blocker.databaseId}`,
      ],
      { allowFailure: true },
    );
    record.nativeDependencyEdges.push({
      blockerIndex,
      blockerIssue: blocker.number,
      created: dependency.status === 0,
      fallback:
        dependency.status === 0 ? null : "Blocked by section in issue body",
      error:
        dependency.status === 0
          ? null
          : (dependency.stderr || dependency.stdout).trim().slice(0, 500),
    });
    saveManifest();
  }

  console.log(`Created #${number}: ${title}`);
}

manifest.publishedAt = new Date().toISOString();
saveManifest();
console.log(`PUBLISHED ${manifest.issues.length} DIRECTOR REVIEW TICKETS`);
