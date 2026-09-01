---
name: "restart-forecast-dashboard"
description: "Restart the VPS forecast dashboard and expose its stable Tailscale preview route."
---

# Restart the forecast dashboard

1. Stop the existing forecast-dashboard background terminal. If it is not tracked, inspect the listener on port `8766` and terminate it only after confirming it is `dashboard.server`.
2. Start `uv run python -m dashboard.server --host 127.0.0.1 --port 8766` as a background terminal from the repository root.
3. Confirm startup by waiting for `Forecast dashboard ready` or a successful `GET http://127.0.0.1:8766/api/health`.
4. Run `preview --proxy 8766 forecast-dashboard`, then verify `tailscale serve status` still maps `/forecast-dashboard` to `http://localhost:8766` without creating another funnel.
5. Report `https://sazzadvps.taildd3bd9.ts.net/forecast-dashboard/` to the user. Never present the localhost URL as the usable link.
