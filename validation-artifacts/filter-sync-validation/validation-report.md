# Exhaustive dashboard functionality validation

- Result: FAIL
- Generated: 2026-09-07T06:26:02.510Z
- Checks: 40 passed / 47
- Shared controls exercised: 21 / 27
- Screenshots: 4
- Failures: 
  - shared control · target_end: target_end did not update the active-filter count
  - shared control · comparison_mode and disabled groups: TypeError: Cannot read properties of null (reading 'disabled')
    at <anonymous>:1:209
  - all shared controls exercised: Unexercised shared controls: horizon, minimum_actual_volume, target_end
  - product parent and target-month drill-down: Timed out: product parent drill-down
  - revision chart respects the selected source: Timed out: ML revision action view
  - all CSV export buttons download: TypeError: Cannot read properties of null (reading 'click')
    at <anonymous>:1:183
  - all buttons classified and operable: Unclassified buttons: [{"text":"Month","action":null,"target":null,"subtab":null,"exportKind":null,"fullscreenKind":null,"modeAction":null,"revisionSort":null,"scatterAction":null,"drilldownCategory":null,"drilldownParentCode":null,"drilldownClose":false,"drilldownClear":false,"disabled":false},{"text":"Quarter","action":null,"target":null,"subtab":null,"exportKind":null,"fullscreenKind":null,"modeAction":null,"revisionSort":null,"scatterAction":null,"drilldownCategory":null,"drilldownParentCode":null,"drilldownClose":false,"drilldownClear":false,"disabled":false},{"text":"3M","action":null,"target":null,"subtab":null,"exportKind":null,"fullscreenKind":null,"modeAction":null,"revisionSort":null,"scatterAction":null,"drilldownCategory":null,"drilldownParentCode":null,"drilldownClose":false,"drilldownClear":false,"disabled":false},{"text":"6M","action":null,"target":null,"subtab":null,"exportKind":null,"fullscreenKind":null,"modeAction":null,"revisionSort":null,"scatterAction":null,"drilldownCategory":null,"drilldownParentCode":null,"drilldownClose":false,"drilldownClear":false,"disabled":false},{"text":"12M","action":null,"target":null,"subtab":null,"exportKind":null,"fullscreenKind":null,"modeAction":null,"revisionSort":null,"scatterAction":null,"drilldownCategory":null,"drilldownParentCode":null,"drilldownClose":false,"drilldownClear":false,"disabled":false},{"text":"24M","action":null,"target":null,"subtab":null,"exportKind":null,"fullscreenKind":null,"modeAction":null,"revisionSort":null,"scatterAction":null,"drilldownCategory":null,"drilldownParentCode":null,"drilldownClose":false,"drilldownClear":false,"disabled":true},{"text":"All","action":null,"target":null,"subtab":null,"exportKind":null,"fullscreenKind":null,"modeAction":null,"revisionSort":null,"scatterAction":null,"drilldownCategory":null,"drilldownParentCode":null,"drilldownClose":false,"drilldownClear":false,"disabled":false},{"text":"Vintages\n                        1","action":null,"target":null,"subtab":null,"exportKind":null,"fullscreenKind":null,"modeAction":null,"revisionSort":null,"scatterAction":null,"drilldownCategory":null,"drilldownParentCode":null,"drilldownClose":false,"drilldownClear":false,"disabled":false},{"text":"Vintages\n              1","action":null,"target":null,"subtab":null,"exportKind":null,"fullscreenKind":null,"modeAction":null,"revisionSort":null,"scatterAction":null,"drilldownCategory":null,"drilldownParentCode":null,"drilldownClose":false,"drilldownClear":false,"disabled":false}]
