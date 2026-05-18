"""Wi-Fi onboarding logic (NetworkManager / nmcli only, no hostapd).

Flow (run as root via the storyteller-netcheck service, BEFORE storyteller):
  1. wait up to netcheck.timeout_s for connectivity
  2. connected -> return (normal boot continues)
  3. not connected -> scan (station mode) & cache, start AP `storyteller-wifi`
     with a DNS-hijack so any request opens the captive portal, serve the
     portal; on submit: stop AP, connect to the chosen Wi-Fi (persisted by
     NM, autoconnect), reboot.

Single radio: scan happens BEFORE the AP is up; the portal shows the cached
list (+ manual entry / rescan).
"""

from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path

from ..config import Config

log = logging.getLogger("storyteller.netcheck")

HIJACK_CONF = Path(
    "/etc/NetworkManager/dnsmasq-shared.d/010-storyteller-captive.conf")
HOTSPOT_CON = "Hotspot"


def _run(args: list[str], timeout: int = 25) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True,
                          timeout=timeout)


# --- connectivity ---

def have_connectivity(cfg: Config) -> bool:
    """True if there is real network access (never trigger AP when online)."""
    try:
        c = _run(["nmcli", "-t", "networking", "connectivity"]).stdout.strip()
        if c in ("full", "limited", "portal"):
            return True
    except Exception:
        pass
    try:
        r = _run(["nmcli", "-t", "-f", "TYPE,STATE", "device"])
        for line in r.stdout.splitlines():
            t, _, st = line.partition(":")
            if t in ("wifi", "ethernet") and st.startswith("connected"):
                return True
    except Exception:
        pass
    return False


def wait_for_connectivity(cfg: Config) -> bool:
    deadline = time.time() + max(1, cfg.netcheck.timeout_s)
    while time.time() < deadline:
        if have_connectivity(cfg):
            return True
        time.sleep(3)
    return have_connectivity(cfg)


# --- scan ---

def scan(cfg: Config) -> list[dict]:
    """Scan in station mode (before AP). Returns [{ssid,signal,security}]."""
    try:
        _run(["nmcli", "device", "wifi", "rescan",
              "ifname", cfg.netcheck.iface], timeout=20)
    except Exception:
        pass
    out: dict[str, dict] = {}
    try:
        r = _run(["nmcli", "-t", "-e", "no", "-f",
                  "SSID,SIGNAL,SECURITY", "device", "wifi", "list",
                  "ifname", cfg.netcheck.iface])
        for line in r.stdout.splitlines():
            parts = line.split(":")
            if len(parts) < 3:
                continue
            ssid = parts[0].strip()
            if not ssid:
                continue
            try:
                sig = int(parts[1])
            except ValueError:
                sig = 0
            sec = parts[2].strip() or "open"
            if ssid not in out or sig > out[ssid]["signal"]:
                out[ssid] = {"ssid": ssid, "signal": sig, "security": sec}
    except Exception as exc:
        log.warning("scan failed: %r", exc)
    return sorted(out.values(), key=lambda d: d["signal"], reverse=True)


# --- access point + DNS hijack (captive portal) ---

def _write_hijack(cfg: Config) -> None:
    try:
        HIJACK_CONF.parent.mkdir(parents=True, exist_ok=True)
        # Resolve EVERY name to the portal -> OS captive detection pops up.
        HIJACK_CONF.write_text(
            f"address=/#/{cfg.netcheck.portal_host}\nno-resolv\n")
    except Exception as exc:
        log.warning("hijack conf write failed: %r", exc)


def _remove_hijack() -> None:
    try:
        HIJACK_CONF.unlink(missing_ok=True)
    except Exception:
        pass


def start_ap(cfg: Config) -> bool:
    _write_hijack(cfg)
    r = _run(["nmcli", "device", "wifi", "hotspot",
              "ifname", cfg.netcheck.iface,
              "ssid", cfg.netcheck.ap_ssid,
              "password", cfg.netcheck.ap_password], timeout=30)
    ok = r.returncode == 0
    log.info("AP %s -> %s", cfg.netcheck.ap_ssid,
             "up" if ok else f"FAILED ({r.stderr.strip()})")
    return ok


def stop_ap(cfg: Config) -> None:
    _run(["nmcli", "connection", "down", HOTSPOT_CON], timeout=15)


def cleanup_ap(cfg: Config) -> None:
    stop_ap(cfg)
    _run(["nmcli", "connection", "delete", HOTSPOT_CON], timeout=15)
    _remove_hijack()


def connect(cfg: Config, ssid: str, key: str) -> bool:
    """Stop AP, connect to the chosen Wi-Fi (persisted by NM). No key logged."""
    cleanup_ap(cfg)
    args = ["nmcli", "device", "wifi", "connect", ssid,
            "ifname", cfg.netcheck.iface]
    if key:
        args += ["password", key]
    try:
        r = _run(args, timeout=45)
    except Exception as exc:
        log.warning("connect error for ssid=%r: %r", ssid, exc)
        return False
    if r.returncode != 0:
        log.warning("connect failed for ssid=%r: %s", ssid,
                    r.stderr.strip())
        return False
    for _ in range(10):
        if have_connectivity(cfg):
            log.info("connected to ssid=%r (saved, autoconnect)", ssid)
            return True
        time.sleep(2)
    return have_connectivity(cfg)


# --- orchestration ---

def run_onboarding(cfg: Config) -> None:
    if not cfg.netcheck.enabled:
        log.info("netcheck disabled")
        return
    if wait_for_connectivity(cfg):
        log.info("connectivity OK — normal boot")
        return
    log.warning("no Wi-Fi — starting captive portal AP %r",
                cfg.netcheck.ap_ssid)
    networks = scan(cfg)
    log.info("cached %d networks", len(networks))
    if not start_ap(cfg):
        log.error("could not start AP — giving up netcheck")
        return
    # Offline spoken hint (cached prompt — no internet for TTS here).
    try:
        from ..audio.backend import get_backend
        from ..voice.prompts import VoicePromptCache

        VoicePromptCache(cfg).play("wifi_setup", get_backend(cfg))
    except Exception as exc:
        log.warning("wifi_setup prompt failed: %r", exc)
    try:
        import uvicorn

        from .portal import create_app

        app = create_app(cfg, networks)
        uvicorn.run(app, host="0.0.0.0", port=cfg.netcheck.web_port,
                    log_level="warning")
    except Exception as exc:
        log.error("portal failed: %r", exc)
        cleanup_ap(cfg)
