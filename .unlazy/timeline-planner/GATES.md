# Gates: dual-handle planner timeline

OWNS: dashboard/index.html, dashboard/app.js, dashboard/styles.css, dashboard/timeline.js, scripts/validate_timeline_control.mjs, scripts/validate_timeline_logic.mjs, validation-artifacts/timeline-planner/**

Scope: Make one always-active dual-handle month range slider the source of truth; presets, month/quarter context, draggable window, and From/To fields must remain synchronized with exact API dates.

- [ ] G1: timeline calculations preserve inclusive month counts, calendar-quarter presets, arbitrary monthly ranges, and synchronized preset detection
  CHECK: node scripts/validate_timeline_logic.mjs
  EXPECT: timeline data correctness validation passed
  CWD: ../..
  EVIDENCE: pending

- [ ] G2: edge cases keep both handles ordered and usable across one-month data, short datasets, unavailable presets, year boundaries, partial quarters, and range clamping
  CHECK: node scripts/validate_timeline_logic.mjs --edge-cases
  EXPECT: timeline edge-case validation passed
  CWD: ../..
  EVIDENCE: pending

- [ ] G3: real-browser UX validation proves both handles are always active, presets reposition both ends, manual handle movement clears unmatched presets, quarter mode preserves monthly precision, exact fields synchronize, and the selected window can move intact
  CHECK: node scripts/validate_timeline_control.mjs --output validation-artifacts/timeline-planner
  EXPECT: timeline UX validation passed
  CWD: ../..
  EVIDENCE: pending

- [ ] G4: responsive screenshots at desktop, wider, and compact viewports show both handles, selected track, meaningful axis labels, exact dates, focus states, and no clipping, overlap, or horizontal overflow
  CHECK: node scripts/validate_timeline_control.mjs --output validation-artifacts/timeline-planner --screenshots-only
  EXPECT: timeline screenshot capture passed
  CWD: ../..
  EVIDENCE: pending

- [ ] G5: focused project tests and edited-file diagnostics remain free of blocking regressions
  CHECK: uv run python -m unittest tests.test_static_dashboard_adapter tests.test_static_dashboard_server
  EXPECT: OK
  CWD: ../..
  EVIDENCE: pending

- [ ] G6: screenshots are manually inspected for hierarchy, alignment, spacing, wrapping, handle-label collisions, visible focus, selected states, and neighboring filter regressions
  EVIDENCE: pending
