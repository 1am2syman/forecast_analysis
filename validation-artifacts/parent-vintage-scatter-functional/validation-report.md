# Exhaustive dashboard functionality validation

- Result: FAIL
- Generated: 2026-08-31T14:34:57.926Z
- Checks: 48 passed / 50
- Shared controls exercised: 28 / 28
- Screenshots: 4
- Failures: 
  - revision chart respects the selected source: Revision history band contract failed: {"title":"Forecast revision paths · ML","hasLedger":false,"queue":"ML action queue","sources":["ML"],"queueRows":98,"queueSparklinePoints":1380,"queueSkuCodes":["706088","706059","707066","711848","706090","710085","711378","707719","707905","716831","719861","723532","713088","713680","723538","713681","723536","723540","703584","716659","725248","716654","707989","726121","716830","722024","711379","723534","720814","715166","716655","727425","711198","723541","723542","723533","720361","724119","727423","716306","720360","723543","716308","725315","718021","726986","715678","725947","715164","723546","715161","716621","723527","721129","725314","716662","726985","725949","707789","725948","716663","726286","720101","720100","716622","715162","719463","716653","720704","707936","726657","702082","716658","719462","726677","718033","715677","724058","720183","720359","719578","724121","715169","724061","715167","724059","724120","726658","721172","716660","717613","727975","717612","720182","720181","716624","724060","726858"],"materialDescription":"PCNO 200ml FT BOT- (PB)","scrollable":true,"gridFont":11,"axisFont":11,"legendFont":10,"hasFullscreen":true,"hasDownload":true,"revisionBands":6,"revisionPaths":24,"revisionSegments":24,"revisionImprovedSegments":12,"revisionWorsenedSegments":12,"revisionNeutralSegments":0,"revisionSegmentHits":24,"revisionEndpoints":6,"revisionCircles":30,"revisionSmooth":0,"revisionLinear":24,"revisionAxis":"Delta vs oldest forecast (%)","revisionMonths":["2026-03-01","2026-04-01","2026-05-01","2026-06-01","2026-07-01","2026-08-01"],"oneEndpointPerBand":true,"pathsStayInsideBands":true}
  - all CSV export buttons download: TypeError: Cannot read properties of null (reading 'click')
    at <anonymous>:1:183
