# Gates: furnished static dashboard prototype

OWNS: dashboard/**, scripts/validate_static_dashboard_ui.mjs, validation-artifacts/static-dashboard-shell/**, .unlazy/static-dashboard-prototype/GATES.md

Scope: furnish all five static dashboard tabs with realistic synthetic data, inline visuals, lightweight filtering, and quality exceptions while preserving the fixed-viewport accessible shell

- [x] G1: all five tabs render synthetic data and finished visuals with no skeleton or placeholder content
  CHECK: node scripts/validate_static_dashboard_ui.mjs --output validation-artifacts/static-dashboard-shell
  EXPECT: STATIC DASHBOARD UI VALIDATION PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=f354ff1a2b34/23 entries; output=Artifacts: /root/GitHub/forecast_analysis/validation-artifacts/static-dashboard-shell | STATIC DASHBOARD UI VALIDATION PASSED

- [x] G2: source files parse and owned text files contain no trailing whitespace
  CHECK: node --check dashboard/app.js && node --check scripts/validate_static_dashboard_ui.mjs && node -e "const fs=require('fs');const paths=['dashboard/index.html','dashboard/styles.css','dashboard/app.js','scripts/validate_static_dashboard_ui.mjs','.unlazy/static-dashboard-prototype/GATES.md'];for(const path of paths){const lines=fs.readFileSync(path,'utf8').split(/\n/);const bad=lines.flatMap((line,index)=>/[ \t]+$/.test(line)?[index+1]:[]);if(bad.length)throw new Error(path+' trailing whitespace at '+bad.join(','));}process.stdout.write('FURNISHED DASHBOARD SOURCE CHECKS PASSED\\n')"
  EXPECT: FURNISHED DASHBOARD SOURCE CHECKS PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=f354ff1a2b34/23 entries; output=FURNISHED DASHBOARD SOURCE CHECKS PASSED

- [x] G3: dashboard preview and its local assets are published through the shared preview root
  CHECK: BASE='https:'//sazzadvps.taildd3bd9.ts.net && preview ./dashboard forecast-dashboard-shell >/tmp/static-dashboard-preview.log && curl -fsS -o /dev/null "$BASE/forecast-dashboard-shell/" && curl -fsS -o /dev/null "$BASE/forecast-dashboard-shell/fonts/chakra-petch-600.ttf" && curl -fsS -o /dev/null "$BASE/forecast-dashboard-shell/favicon.ico" && tailscale serve status | grep -F '|-- /                            path  /root/previews' >/dev/null && echo FURNISHED DASHBOARD PREVIEW PASSED
  EXPECT: FURNISHED DASHBOARD PREVIEW PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=f354ff1a2b34/23 entries; output=FURNISHED DASHBOARD PREVIEW PASSED

- [x] G4: regenerated screenshot gallery and validation report are published and return HTTP 200
  CHECK: BASE='https:'//sazzadvps.taildd3bd9.ts.net && preview ./validation-artifacts/static-dashboard-shell forecast-dashboard-validation >/tmp/static-dashboard-gallery-preview.log && curl -fsS -o /dev/null "$BASE/forecast-dashboard-validation/" && curl -fsS -o /dev/null "$BASE/forecast-dashboard-validation/validation-report.html" && echo FURNISHED DASHBOARD GALLERY PASSED
  EXPECT: FURNISHED DASHBOARD GALLERY PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=f354ff1a2b34/23 entries; output=FURNISHED DASHBOARD GALLERY PASSED
