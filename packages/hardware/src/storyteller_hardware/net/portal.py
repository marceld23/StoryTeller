"""Captive-portal web app (only runs while the onboarding AP is up).

DNS is hijacked to this host, so every request lands here. We answer the
OS captive-probe URLs and any unknown path with the portal page, which makes
iOS/Android/Windows auto-pop the "Sign in to network" sheet.
"""

from __future__ import annotations

import html
import logging
import subprocess
import threading

from storyteller_core.config import Config

from . import onboarding

log = logging.getLogger("storyteller.netcheck")


def _page(networks: list[dict], msg: str = "") -> str:
    opts = "".join(
        f"<option value='{html.escape(n['ssid'])}'>"
        f"{html.escape(n['ssid'])} ({n['signal']}%"
        f"{'' if n['security'] in ('', 'open') else ' 🔒'})</option>"
        for n in networks)
    note = f"<p style='color:#b00'>{html.escape(msg)}</p>" if msg else ""
    return (
        "<!doctype html><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Storyteller WLAN-Setup</title>"
        "<style>body{font:16px system-ui;margin:1.5rem;max-width:30rem}"
        "input,select,button{font:inherit;width:100%;padding:.6rem;"
        "margin:.35rem 0;box-sizing:border-box}button{background:#111;"
        "color:#fff;border:0;border-radius:6px}h1{font-size:1.3rem}</style>"
        "<h1>📶 Storyteller — WLAN einrichten</h1>"
        "<p>Wähle dein WLAN und gib den Schlüssel ein. Der Storyteller "
        "verbindet sich, merkt es sich und startet neu.</p>"
        f"{note}"
        "<form method='post' action='/connect'>"
        f"<label>Netzwerk<select name='ssid'>{opts}"
        "<option value=''>— anderes (manuell) —</option></select></label>"
        "<input name='ssid_manual' placeholder='SSID manuell (optional)'>"
        "<input name='password' type='password' "
        "placeholder='WLAN-Schlüssel'>"
        "<button>Verbinden</button></form>"
        "<form method='get' action='/rescan'>"
        "<button style='background:#555'>Erneut suchen</button></form>")


def create_app(cfg: Config, networks: list[dict]):
    from fastapi import FastAPI, Form
    from fastapi.responses import HTMLResponse, RedirectResponse

    app = FastAPI(title="Storyteller Wi-Fi Setup")
    state = {"networks": list(networks)}

    def portal(msg: str = "") -> HTMLResponse:
        return HTMLResponse(_page(state["networks"], msg))

    @app.get("/", response_class=HTMLResponse)
    def root():
        return portal()

    @app.get("/rescan")
    def rescan():
        try:
            n = onboarding.scan(cfg)
            if n:
                state["networks"] = n
        except Exception:
            pass
        return RedirectResponse("/", status_code=303)

    @app.post("/connect", response_class=HTMLResponse)
    def do_connect(ssid: str = Form(""), ssid_manual: str = Form(""),
                    password: str = Form("")):
        target = (ssid_manual or ssid).strip()
        if not target:
            return portal("Bitte ein Netzwerk wählen oder SSID eingeben.")

        def worker(ss: str, key: str):
            try:
                if onboarding.connect(cfg, ss, key):
                    log.info("onboarding success — rebooting")
                    subprocess.run(["systemctl", "reboot"], check=False)
                else:
                    log.warning("onboarding connect failed — AP back up")
                    onboarding.start_ap(cfg)  # let the user retry
            except Exception as exc:
                log.error("connect worker error: %r", exc)
                onboarding.start_ap(cfg)

        threading.Thread(target=worker, args=(target, password),
                         daemon=True).start()
        return HTMLResponse(
            "<!doctype html><meta charset='utf-8'><meta name='viewport' "
            "content='width=device-width,initial-scale=1'>"
            "<style>body{font:16px system-ui;margin:1.5rem;max-width:30rem}"
            "</style><h1>🔄 Verbinde …</h1>"
            f"<p>Verbinde mit <b>{html.escape(target)}</b>. Bei Erfolg "
            "startet der Storyteller in ~1 Minute neu und nutzt dieses WLAN "
            "künftig automatisch.</p><p>Erscheint <b>storyteller-wifi</b> "
            "erneut, war der Schlüssel falsch — wieder verbinden und erneut "
            "versuchen.</p>")

    # --- captive-portal probe URLs + catch-all (auto-popup) ---
    @app.get("/generate_204")
    @app.get("/gen_204")
    def android_204():
        return RedirectResponse("/", status_code=302)

    @app.get("/{full_path:path}", response_class=HTMLResponse)
    def catch_all(full_path: str):
        # Apple/Windows/everything else -> serve the portal so it pops up.
        return portal()

    return app
