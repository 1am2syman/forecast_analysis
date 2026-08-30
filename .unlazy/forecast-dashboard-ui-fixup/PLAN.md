# Forecast analysis dashboard UI fixup orchestration

## Fixed execution contract

Implement and close issues `01` through `07` in `.scratch/forecast-analysis-dashboard-ui-fixup/issues/` sequentially in dependency order.

## Roles

- `worker`: sole implementation writer; Pi provider `cliproxyapi`, model `gpt-5.6-luna`, thinking `max`.
- `reviewer`: read-only, ticket-scoped reviewer; Pi provider `cliproxyapi`, model `gpt-5.6-sol`, thinking `high`.
- orchestrator: creates one tab per ticket with panes labeled `worker` and `reviewer`, monitors context, coordinates review/rework, independently verifies, commits, marks the ticket closed, and closes the ticket tab.

The provider, model, and thinking levels are immutable.

## Ticket order and dependencies

1. `01-establish-visual-baseline-and-overflow-oracle.md`
2. `02-deliver-responsive-shell-and-filter-workbench.md` — needs 01
3. `03-deliver-single-source-performance-overview.md` — needs 02
4. `04-deliver-revision-and-source-comparison-experience.md` — needs 03
5. `05-deliver-product-history-and-exception-exploration.md` — needs 03 and is run after 04 to preserve sequential commits
6. `06-deliver-progressive-data-quality-diagnostics.md` — needs 02 and is run after 05 to preserve sequential commits
7. `07-complete-responsive-accessible-visual-release-gate.md` — needs 04, 05, and 06

## Per-ticket protocol

1. Create a fresh ticket tab in the current `forecast_analysis` workspace.
2. Split it into exactly two panes and label them `worker` and `reviewer`.
3. Start the worker with Luna/max and reviewer with Sol/high.
4. Give the worker only the current ticket, its dependencies, repository rules, and the requirement to keep changes focused and preserve analytical behavior.
5. When the worker reports ready, ask the reviewer for a strict acceptance-criterion and regression review. The reviewer must report only actionable in-scope defects and must not edit files.
6. Return every accepted finding to the worker. Repeat until the reviewer returns `ALL_GREEN` with no unresolved actionable finding.
7. Independently inspect the diff and run ticket-appropriate diagnostics and validation.
8. Change the ticket status to `closed`, check its acceptance boxes only when evidence exists, commit the complete ticket atomically, then close the tab.
9. Start the next ticket only after the prior ticket commit is complete.

## Context heartbeat

Monitor both agents every 60 seconds using the norm-tool conservative heartbeat policy:

- evaluate compaction economics only after the configured context floor;
- request an agent-confirmed safe boundary before non-emergency compaction;
- force compaction only at the emergency ceiling;
- distinguish formal task completion from transient idle state;
- resume unfinished assignments after compaction;
- send completion/blocking signals to the orchestrator pane.

Agents use stable formal task ids `forecast-dashboard-worker` and `forecast-dashboard-reviewer`; each ticket gets fresh sessions.

## Scope discipline

- Worker owns implementation; reviewer is read-only.
- Do not weaken analytical tests or change formulas, filters, downloads, or data semantics unless the current ticket explicitly requires it.
- Do not absorb unrelated pre-existing work into a ticket commit.
- Browser evidence must use deterministic named states and the repository's verified Marimo capture workflow.
- Each ticket commit must contain only that ticket's issue closure and implementation/evidence.
