# Ticket orchestration plan

## Contract

- Repository: `1am2syman/forecast_analysis`
- Issues: `#3` through `#26`
- Dependency source: `.unlazy/demand-planning-director-tickets/manifest.json`
- Implementation agent: Pi, provider `cliproxyapi`, model `gpt-5.6-luna`, thinking `max`
- Review agent: Pi, provider `cliproxyapi`, model `gpt-5.6-sol`, thinking `high`
- Provider/model substitutions are forbidden.
- Each issue receives an isolated worktree and a dedicated Herdr tab.
- A ticket is GREEN only when its acceptance criteria pass, automated checks pass, and Sol reports no blocking findings.
- Sol findings return to the same Luna agent; review repeats until GREEN.
- Downstream tickets start only after every declared blocker is GREEN and integrated.
- Shared integration branch: `orchestrator/issues-3-26`.
- Current dirty working tree is not modified by ticket agents; an orchestration snapshot captures it as the worktree base.

## State model

`WAITING -> READY -> IMPLEMENTING -> REVIEWING -> GREEN -> INTEGRATED -> CLOSED`

A failed review transitions `REVIEWING -> IMPLEMENTING` with the exact Sol findings.

## Initial ready set

- #3 Define metric governance, targets, and tolerance contracts
- #4 Make analysis scopes saveable and shareable
- #5 Replace portfolio dropdowns with hierarchy-aware search and multi-select
- #6 Establish a chart readability and interaction standard
- #7 Add enterprise identity, permissions, and audit governance

## Integration policy

Tickets are merged into the orchestration branch in dependency order. Before review, each ticket branch rebases or merges the latest orchestration branch so Sol reviews the state that will actually compose. After integration, root regression checks run before downstream dispatch.

## Status log

See `status.log`; append events, never rewrite history.
