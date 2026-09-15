---
name: "restart-forecast-dashboard"
description: "Restart the VPS forecast dashboard and expose its stable Tailscale preview route."
---

# Restart the forecast dashboard

The dashboard runs as the **systemd unit** `forecast-dashboard.service`
(`/etc/systemd/system/forecast-dashboard.service`):
`WorkingDirectory=/root/GitHub/forecast_analysis`, `ExecStart=.venv/bin/python -m dashboard.server --host 127.0.0.1 --port 8766`,
`Restart=always`.

Use systemd, not a Pi background terminal: a background terminal is killed when the Pi session
ends or reloads (observed as exit code 143). No `.service` files are kept in this repo; the unit
lives in `/etc/systemd/system/` only.

1. Check who owns the port before changing anything: `ss -ltnp | grep 8766`.
   - Unit-owned or free → proceed.
   - Held by an untracked process → confirm it is `dashboard.server` and terminate it by **explicit
     PID**. Do **not** use `pkill -f "uv run python -m dashboard.server"`: that pattern also matches
     the calling shell's own command line and kills the caller.
2. Restart: `systemctl restart forecast-dashboard.service` (or `enable --now` if disabled).
3. Confirm startup by waiting for `Forecast dashboard ready` or a successful
   `GET http://127.0.0.1:8766/api/health`. Then confirm `systemctl is-active` is `active` and
   `MainPID` is non-zero, so systemd — not a stray manual instance — owns the port.
4. Run `preview --proxy 8766 forecast-dashboard`, then verify `tailscale serve status` still maps
   `/forecast-dashboard` to `http://localhost:8766` without creating another funnel.
5. Report `https://sazzadvps.taildd3bd9.ts.net/forecast-dashboard/` to the user. Never present the
   localhost URL as the usable link.

Notes:

- This host's resolver (`8.8.8.8`) cannot resolve `*.ts.net`, so `curl` to the hostname fails locally.
  Verify the route with `curl --resolve sazzadvps.taildd3bd9.ts.net:443:100.109.213.10 <url>`.
- The hostname is currently **tailnet-only** (`tailscale serve status` shows `(tailnet only)`, no
  public DNS record). Say so when reporting; make it public only on request, via
  `preview --proxy 8766 forecast-dashboard --public`.
- Stale serve paths also point at 8766 (`/ticket-10`, `/ticket-14`,
  `/forecast-dashboard-real-data`); they are harmless duplicates, not extra instances.
