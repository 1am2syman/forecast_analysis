# Gates: dual-handle planner timeline

OWNS: dashboard/index.html, dashboard/app.js, dashboard/styles.css, dashboard/timeline.js, scripts/validate_timeline_control.mjs, scripts/validate_timeline_logic.mjs, validation-artifacts/timeline-planner/**

Scope: Make one always-active dual-handle month range slider the source of truth; presets, month/quarter context, draggable window, and From/To fields must remain synchronized with exact API dates.

- [x] G1: timeline calculations preserve inclusive month counts, calendar-quarter presets, arbitrary monthly ranges, and synchronized preset detection
  CHECK: node scripts/validate_timeline_logic.mjs
  EXPECT: timeline data correctness validation passed
  CWD: ../..
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=timeline data correctness validation passed

- [x] G2: edge cases keep both handles ordered and usable across one-month data, short datasets, unavailable presets, year boundaries, partial quarters, and range clamping
  CHECK: node scripts/validate_timeline_logic.mjs --edge-cases
  EXPECT: timeline edge-case validation passed
  CWD: ../..
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=timeline edge-case validation passed

- [x] G3: real-browser UX validation proves both handles are always active, presets reposition both ends, manual handle movement clears unmatched presets, quarter mode preserves monthly precision, exact fields synchronize, and the selected window can move intact
  CHECK: node scripts/validate_timeline_control.mjs --output validation-artifacts/timeline-planner
  EXPECT: timeline UX validation passed
  CWD: ../..
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=timeline UX validation passed

- [x] G4: responsive screenshots at desktop, wider, and compact viewports show both handles, selected track, meaningful axis labels, exact dates, focus states, and no clipping, overlap, or horizontal overflow
  CHECK: node scripts/validate_timeline_control.mjs --output validation-artifacts/timeline-planner --screenshots-only
  EXPECT: timeline screenshot capture passed
  CWD: ../..
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=timeline screenshot capture passed

- [x] G5: focused project tests and edited-file diagnostics remain free of blocking regressions
  CHECK: uv run python -m unittest tests.test_static_dashboard_adapter tests.test_static_dashboard_server
  EXPECT: OK
  CWD: ../..
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=Ran 21 tests in 10.639s | OK

- [x] G6: screenshots are manually inspected for hierarchy, alignment, spacing, wrapping, handle-label collisions, visible focus, selected states, and neighboring filter regressions
  EVIDENCE: Reviewed desktop, wide, compact, 6M preset, quarter preset, manual partial-quarter, exact-field, and keyboard-focus screenshots. Both handles and the selected track remain clear; meaningful year/quarter axis labels do not collide; preset and custom states are legible; From/To fields stay visible; compact layout scrolls vertically without horizontal overflow; no neighboring-filter clipping or alignment regression was observed. Tight one- or two-month ranges offset the handles vertically to avoid overlap.
