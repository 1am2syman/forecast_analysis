# Gates: static dashboard release validation

OWNS: dashboard/**, scripts/validate_static_dashboard_ui.mjs, validation-artifacts/static-dashboard-shell/**, .unlazy/static-dashboard-validation/GATES.md

Scope: validate and polish the static HTML/CSS dashboard shell across every tab, interaction, supported viewport, accessibility state, and screenshot artifact without modifying the unrelated Marimo work in progress

- [x] G1: browser validation covers every tab, supported viewport, navigation path, overflow contract, focus state, font, resource, and console-error check
  CHECK: node scripts/validate_static_dashboard_ui.mjs --output validation-artifacts/static-dashboard-shell
  EXPECT: STATIC DASHBOARD UI VALIDATION PASSED
  EVIDENCE: exit=0; cwd=/root/GitHub/forecast_analysis; output=Screenshots: 18 | Artifacts: /root/GitHub/forecast_analysis/validation-artifacts/static-dashboard-shell | STATIC DASHBOARD UI VALIDATION PASSED

- [x] G2: the JavaScript shell and validation harness parse, and owned text files contain no trailing whitespace
  CHECK: node --check dashboard/app.js && node --check scripts/validate_static_dashboard_ui.mjs && node -e "const fs=require('fs');const paths=['dashboard/index.html','dashboard/styles.css','dashboard/app.js','scripts/validate_static_dashboard_ui.mjs','.unlazy/static-dashboard-validation/GATES.md'];for(const path of paths){const lines=fs.readFileSync(path,'utf8').split(/\n/);const bad=lines.flatMap((line,index)=>/[ \t]+$/.test(line)?[index+1]:[]);if(bad.length)throw new Error(path+' trailing whitespace at '+bad.join(','));}process.stdout.write('STATIC DASHBOARD SOURCE CHECKS PASSED\\n')"
  EXPECT: STATIC DASHBOARD SOURCE CHECKS PASSED
  EVIDENCE: exit=0; cwd=/root/GitHub/forecast_analysis; output=STATIC DASHBOARD SOURCE CHECKS PASSED

- [x] G3: final static preview is published through the shared preview root and returns HTTP 200
  CHECK: preview ./dashboard forecast-dashboard-shell >/tmp/static-dashboard-preview.log && curl -fsS -o /dev/null <https://sazzadvps.taildd3bd9.ts.net/forecast-dashboard-shell/> && curl -fsS -o /dev/null <https://sazzadvps.taildd3bd9.ts.net/forecast-dashboard-shell/fonts/chakra-petch-600.ttf> && curl -fsS -o /dev/null <https://sazzadvps.taildd3bd9.ts.net/forecast-dashboard-shell/favicon.ico> && tailscale serve status | grep -F '|-- /                            path  /root/previews' >/dev/null && echo STATIC DASHBOARD PREVIEW PASSED
  EXPECT: STATIC DASHBOARD PREVIEW PASSED
  EVIDENCE: exit=0; cwd=/root/GitHub/forecast_analysis; output=STATIC DASHBOARD PREVIEW PASSED

- [x] G4: screenshot gallery and validation report are published through the shared preview root and return HTTP 200
  CHECK: preview ./validation-artifacts/static-dashboard-shell forecast-dashboard-validation >/tmp/static-dashboard-gallery-preview.log && curl -fsS -o /dev/null <https://sazzadvps.taildd3bd9.ts.net/forecast-dashboard-validation/> && curl -fsS -o /dev/null <https://sazzadvps.taildd3bd9.ts.net/forecast-dashboard-validation/validation-report.html> && echo STATIC DASHBOARD GALLERY PASSED
  EXPECT: STATIC DASHBOARD GALLERY PASSED
  EVIDENCE: exit=0; cwd=/root/GitHub/forecast_analysis; output=STATIC DASHBOARD GALLERY PASSED
