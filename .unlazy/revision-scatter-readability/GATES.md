# Gates: revision scatter readability

OWNS: dashboard/app.js, dashboard/styles.css, scripts/validate_dashboard_functionality.mjs, validation-artifacts/revision-scatter-readability/**

Scope: Deliver a readable default scatter chart with bounded volume sizing, density context, filtering, zoom/pan, selection, accessible tooltips, and browser-verified behavior.

- [x] G1: Modified JavaScript parses and edited source files have no blocking primary diagnostics.
  CHECK: node --check dashboard/app.js && node --check scripts/validate_dashboard_functionality.mjs && echo SCATTER_SYNTAX_OK
  EXPECT: SCATTER_SYNTAX_OK
  CWD: /root/GitHub/forecast_analysis
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=SCATTER_SYNTAX_OK

- [x] G2: Exhaustive real-browser dashboard validation passes with the new scatter interaction contract.
  CHECK: node scripts/validate_dashboard_functionality.mjs --output validation-artifacts/revision-scatter-readability
  EXPECT: EXHAUSTIVE DASHBOARD FUNCTIONALITY VALIDATION PASSED
  CWD: /root/GitHub/forecast_analysis
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=EXHAUSTIVE DASHBOARD FUNCTIONALITY VALIDATION PASSED

- [x] G3: The live Comparison revision chart is visually readable in uniform-dot and volume-size modes at desktop width, with interaction controls visible and no destructive overlap.
  EVIDENCE: Browser review of `validation-artifacts/revision-scatter-readability/comparison-uniform.png`, `comparison-volume.png`, and `comparison-fullscreen-volume.png`: default uniform dots are small and separated, density is subtle, volume mode is capped, controls remain legible, and fullscreen provides readable spacing.
