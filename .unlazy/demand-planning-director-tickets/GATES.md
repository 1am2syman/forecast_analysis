# Gates: demand planning director improvement tickets

OWNS: .unlazy/demand-planning-director-tickets/**

Scope: Publish the approved 24-ticket director-review backlog to GitHub with complete acceptance criteria, ready-for-agent triage, and explicit blocking edges.

- [x] G1: Exactly 24 new GitHub issues are published and recorded in the manifest
  CHECK: node .unlazy/demand-planning-director-tickets/verify.mjs count
  EXPECT: TICKET COUNT PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=f354ff1a2b34/23 entries; output=TICKET COUNT PASSED

- [x] G2: Every published issue contains What to build, Acceptance criteria, and Blocked by sections and carries enhancement plus ready-for-agent labels
  CHECK: node .unlazy/demand-planning-director-tickets/verify.mjs shape
  EXPECT: TICKET SHAPE PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=f354ff1a2b34/23 entries; output=TICKET SHAPE PASSED

- [x] G3: Every declared blocker points to another issue in the published backlog and every blocker was published before the blocked ticket
  CHECK: node .unlazy/demand-planning-director-tickets/verify.mjs edges
  EXPECT: TICKET EDGES PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=f354ff1a2b34/23 entries; output=TICKET EDGES PASSED

- [x] G4: The 24 issue titles are unique and do not duplicate the two pre-existing open dashboard issues
  CHECK: node .unlazy/demand-planning-director-tickets/verify.mjs uniqueness
  EXPECT: TICKET UNIQUENESS PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=f354ff1a2b34/23 entries; output=TICKET UNIQUENESS PASSED

- [x] G5: The final manifest contains a working GitHub URL for every issue and records whether native dependency links were created or text fallback was retained
  CHECK: node .unlazy/demand-planning-director-tickets/verify.mjs urls
  EXPECT: TICKET URLS PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=f354ff1a2b34/23 entries; output=TICKET URLS PASSED
