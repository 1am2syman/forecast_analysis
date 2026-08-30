# Gates: metric-faithful static dashboard shell

OWNS: dashboard/**, scripts/validate_static_dashboard_ui.mjs, validation-artifacts/static-dashboard-shell/**, .unlazy/static-dashboard-ambition-fidelity/GATES.md

Scope: make the static approval shell faithfully represent the production dashboard's metrics, shared filters, revision/source distinction, product stability, exception workflow, and quality diagnostics while preserving the fixed-viewport accessible design

- [x] G1: all five tabs expose the required metric families and analytical states without semantic unit errors, placeholders, clipping, or page scrolling
  CHECK: node scripts/validate_static_dashboard_ui.mjs --output validation-artifacts/static-dashboard-shell
  EXPECT: STATIC DASHBOARD UI VALIDATION PASSED
  EVIDENCE: passed 2026-08-27; 18 screenshots across desktop, short-laptop, narrow, focus, hover, and rail-detail states; report at validation-artifacts/static-dashboard-shell/validation-report.md

- [x] G2: dashboard source and validation harness parse cleanly and owned text files contain no trailing whitespace
  CHECK: node --check dashboard/app.js && node --check scripts/validate_static_dashboard_ui.mjs && node -e "const fs=require('fs');const paths=['dashboard/index.html','dashboard/styles.css','dashboard/app.js','scripts/validate_static_dashboard_ui.mjs','.unlazy/static-dashboard-ambition-fidelity/GATES.md'];for(const path of paths){const lines=fs.readFileSync(path,'utf8').split(/\n/);const bad=lines.flatMap((line,index)=>/[ \t]+$/.test(line)?[index+1]:[]);if(bad.length)throw new Error(path+' trailing whitespace at '+bad.join(','));}process.stdout.write('METRIC-FAITHFUL DASHBOARD SOURCE CHECKS PASSED\n')"
  EXPECT: METRIC-FAITHFUL DASHBOARD SOURCE CHECKS PASSED
  EVIDENCE: passed 2026-08-27; Node syntax checks, whitespace check, primary LSP diagnostics, and pi-lens session diagnostics were clean

- [x] G3: the dashboard and all local assets are published through the existing shared preview route and return HTTP 200
  CHECK: BASE='https:'//sazzadvps.taildd3bd9.ts.net && preview ./dashboard forecast-dashboard-shell >/tmp/static-dashboard-preview.log && curl -fsS -o /dev/null "$BASE/forecast-dashboard-shell/" && curl -fsS -o /dev/null "$BASE/forecast-dashboard-shell/fonts/chakra-petch-600.ttf" && curl -fsS -o /dev/null "$BASE/forecast-dashboard-shell/favicon.ico" && tailscale serve status | grep -F '|-- /                            path  /root/previews' >/dev/null && echo METRIC-FAITHFUL DASHBOARD PREVIEW PASSED
  EXPECT: METRIC-FAITHFUL DASHBOARD PREVIEW PASSED
  EVIDENCE: passed 2026-08-27; [dashboard preview](https://sazzadvps.taildd3bd9.ts.net/forecast-dashboard-shell/) returned HTTP 200 on the configured shared tailnet route

- [x] G4: the regenerated screenshot gallery and validation report are published and return HTTP 200
  CHECK: BASE='https:'//sazzadvps.taildd3bd9.ts.net && preview ./validation-artifacts/static-dashboard-shell forecast-dashboard-validation >/tmp/static-dashboard-gallery-preview.log && curl -fsS -o /dev/null "$BASE/forecast-dashboard-validation/" && curl -fsS -o /dev/null "$BASE/forecast-dashboard-validation/validation-report.html" && echo METRIC-FAITHFUL DASHBOARD GALLERY PASSED
  EXPECT: METRIC-FAITHFUL DASHBOARD GALLERY PASSED
  EVIDENCE: passed 2026-08-27; [validation gallery](https://sazzadvps.taildd3bd9.ts.net/forecast-dashboard-validation/) and validation-report.html returned HTTP 200 on the configured shared tailnet route
