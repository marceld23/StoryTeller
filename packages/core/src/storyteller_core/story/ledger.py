"""Append-only cost ledger (data/cost.jsonl).

Each LLM / TTS / STT / embedding call writes one JSON line with the
incremental cost. Admin resets are written as marker lines, so a reset
is itself part of the audit trail — nothing is mutated or deleted in
place, which makes the ledger resistant to accidental loss and easy to
inspect.

Entry shape (regular call):
  {"ts": "<iso>", "date": "YYYY-MM-DD", "thread_id": str|null,
   "world_id": str|null, "kind": "chat|embed|tts|stt",
   "model": str|null, "chat_in": int, "chat_out": int, "embed": int,
   "tts_chars": int, "stt_sec": float, "usd": float}

Marker shapes:
  {"ts": "<iso>", "date": "YYYY-MM-DD", "marker": "reset_daily"}
  {"ts": "<iso>", "thread_id": str, "marker": "reset_session"}
  {"ts": "<iso>", "date": "YYYY-MM-DD", "marker": "warned_daily"}

Daily / session totals scan only entries that come AFTER the last reset
marker for that bucket, so a reset effectively zeroes the running sum
without rewriting history.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime, timedelta
from datetime import date as _date

from ..config import Config
from .cost import DailyCapExceeded, chat_unit_prices, is_local_role

log = logging.getLogger("storyteller.cost.ledger")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _today() -> str:
    return _date.today().isoformat()


class CostLedger:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.path = cfg.path(cfg.cost.ledger_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ---------------- write -------------------------------------------------

    def _append_raw(self, entry: dict) -> None:
        line = json.dumps(entry, ensure_ascii=False)
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
                os.fsync(f.fileno())
        except OSError as exc:
            log.warning("cost ledger write failed (%s): %r", self.path, exc)

    def record(self, *, kind: str, usd: float,
               thread_id: str | None = None, world_id: str | None = None,
               model: str | None = None, chat_in: int = 0, chat_out: int = 0,
               embed: int = 0, tts_chars: int = 0,
               stt_sec: float = 0.0) -> None:
        """Append one regular usage entry.

        Free (usd <= 0) calls — typically local Ollama / XTTS / faster-
        whisper — are skipped: only paid calls contribute to the ledger
        so daily totals reflect actual cloud spend.
        """
        if not usd or float(usd) <= 0.0:
            return
        self._append_raw({
            "ts": _now_iso(),
            "date": _today(),
            "kind": kind,
            "thread_id": thread_id,
            "world_id": world_id,
            "model": model,
            "chat_in": int(chat_in),
            "chat_out": int(chat_out),
            "embed": int(embed),
            "tts_chars": int(tts_chars),
            "stt_sec": float(stt_sec),
            "usd": float(usd or 0.0),
        })

    def reset_daily(self, date: str | None = None) -> str:
        date = date or _today()
        self._append_raw({"ts": _now_iso(), "date": date,
                          "marker": "reset_daily"})
        return date

    def reset_session(self, thread_id: str) -> None:
        self._append_raw({"ts": _now_iso(), "thread_id": thread_id,
                          "marker": "reset_session"})

    def mark_warned_today(self, date: str | None = None) -> str:
        date = date or _today()
        self._append_raw({"ts": _now_iso(), "date": date,
                          "marker": "warned_daily"})
        return date

    # ---------------- read --------------------------------------------------

    def _iter_entries(self):
        if not self.path.exists():
            return
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except Exception:
                    continue

    def _entries_since_last_marker(self, *, date: str | None = None,
                                    thread_id: str | None = None) -> list[dict]:
        """Return entries written AFTER the most recent matching reset
        marker. If `date` is given, scopes to reset_daily for that date.
        If `thread_id` is given, scopes to reset_session for that thread."""
        all_entries = list(self._iter_entries())
        cut_idx = -1
        for i, e in enumerate(all_entries):
            marker = e.get("marker")
            if not marker:
                continue
            if date and marker == "reset_daily" and e.get("date") == date:
                cut_idx = i
            if thread_id and marker == "reset_session" \
                    and e.get("thread_id") == thread_id:
                cut_idx = i
        return all_entries[cut_idx + 1:]

    def daily_total(self, date: str | None = None) -> float:
        date = date or _today()
        total = 0.0
        for e in self._entries_since_last_marker(date=date):
            if e.get("marker"):
                continue
            if e.get("date") == date:
                total += float(e.get("usd") or 0.0)
        return total

    def session_total(self, thread_id: str) -> float:
        total = 0.0
        for e in self._entries_since_last_marker(thread_id=thread_id):
            if e.get("marker"):
                continue
            if e.get("thread_id") == thread_id:
                total += float(e.get("usd") or 0.0)
        return total

    # ---------------- cap checks -------------------------------------------

    def is_over_daily_cap(self, date: str | None = None) -> bool:
        if not self.cfg.cost.enforce:
            return False
        cap = float(self.cfg.cost.daily_cap_usd or 0.0)
        if cap <= 0:
            return False
        return self.daily_total(date) >= cap

    def assert_under_cap(self) -> None:
        """Raise `DailyCapExceeded` if today's spend is already at/over
        the daily cap. Callers use this to refuse the next paid call so
        story state on disk stays consistent."""
        if self.is_over_daily_cap():
            raise DailyCapExceeded(
                self.daily_total(),
                float(self.cfg.cost.daily_cap_usd or 0.0))

    def record_chat_usage(self, *, role: str, model: str | None,
                          usage, thread_id: str | None = None,
                          world_id: str | None = None) -> float:
        """Convenience for one-shot chat calls outside the engine (world
        generation, recap, etc.): compute USD from `usage`, skip if the
        role is on a local endpoint, append a ledger entry, and return
        the USD delta. Mirrors `CostTracker.record_chat` but without the
        per-session totals — those callers don't persist a tracker.
        """
        if usage is None or is_local_role(self.cfg, role):
            return 0.0
        pin = int(getattr(usage, "prompt_tokens", 0) or 0)
        pout = int(getattr(usage, "completion_tokens", 0) or 0)
        in_price, out_price = chat_unit_prices(self.cfg, model)
        usd = pin / 1e6 * in_price + pout / 1e6 * out_price
        self.record(kind="chat", usd=usd, thread_id=thread_id,
                    world_id=world_id, model=model,
                    chat_in=pin, chat_out=pout)
        return usd

    def daily_pct(self, date: str | None = None) -> float:
        cap = float(self.cfg.cost.daily_cap_usd or 0.0)
        if cap <= 0:
            return 0.0
        return self.daily_total(date) / cap * 100.0

    def is_approaching_daily_cap(self, date: str | None = None) -> bool:
        if not self.cfg.cost.enforce:
            return False
        return self.daily_pct(date) >= int(self.cfg.cost.warn_threshold_pct)

    def warned_today(self, date: str | None = None) -> bool:
        date = date or _today()
        for e in self._iter_entries():
            if e.get("marker") == "warned_daily" and e.get("date") == date:
                # any warning marker after the last reset_daily for that day counts
                pass
        # cheaper: check whether ANY warned_daily marker for `date` exists
        # AFTER the last reset_daily for `date`
        entries = self._entries_since_last_marker(date=date)
        return any(e.get("marker") == "warned_daily" and e.get("date") == date
                   for e in entries)

    # ---------------- admin reporting --------------------------------------

    def summary(self, days: int = 7) -> dict:
        today = _date.today()
        out: dict = {
            "today_usd": self.daily_total(today.isoformat()),
            "cap_daily_usd": float(self.cfg.cost.daily_cap_usd or 0.0),
            "warn_threshold_pct": int(self.cfg.cost.warn_threshold_pct),
            "pct": self.daily_pct(today.isoformat()),
            "over_cap": self.is_over_daily_cap(today.isoformat()),
            "approaching": self.is_approaching_daily_cap(today.isoformat()),
            "warned_today": self.warned_today(today.isoformat()),
            "enforce": bool(self.cfg.cost.enforce),
            "days": [],
        }
        for i in range(max(1, int(days))):
            d = today - timedelta(days=i)
            out["days"].append({"date": d.isoformat(),
                                "usd": self.daily_total(d.isoformat())})
        return out

    def worlds_for(self, days: int = 7) -> list[dict]:
        """Per-world spend rollup over the last `days` days. Includes
        non-paid lines (usd=0) implicitly because record() already
        skips them. Bypasses session reset markers — world totals are
        a longitudinal view, not a "since last reset" view."""
        from datetime import timedelta
        today = _date.today()
        cutoff = (today - timedelta(days=max(1, int(days)) - 1)).isoformat()
        by_world: dict[str, dict] = {}
        for e in self._iter_entries():
            if e.get("marker"):
                continue
            if (e.get("date") or "") < cutoff:
                continue
            wid = e.get("world_id") or "(ohne Welt)"
            agg = by_world.setdefault(wid, {
                "world_id": wid, "usd": 0.0, "calls": 0,
                "chat_in": 0, "chat_out": 0, "embed": 0,
                "tts_chars": 0, "stt_sec": 0.0, "last_ts": "",
            })
            agg["usd"] += float(e.get("usd") or 0.0)
            agg["calls"] += 1
            agg["chat_in"] += int(e.get("chat_in") or 0)
            agg["chat_out"] += int(e.get("chat_out") or 0)
            agg["embed"] += int(e.get("embed") or 0)
            agg["tts_chars"] += int(e.get("tts_chars") or 0)
            agg["stt_sec"] += float(e.get("stt_sec") or 0.0)
            ts = e.get("ts") or ""
            if ts > agg["last_ts"]:
                agg["last_ts"] = ts
        out = list(by_world.values())
        out.sort(key=lambda r: r["usd"], reverse=True)
        return out

    def sessions_for(self, date: str | None = None) -> list[dict]:
        """Sessions touched on `date`, with their since-reset usd total."""
        date = date or _today()
        by_thread: dict[str, dict] = {}
        for e in self._iter_entries():
            if e.get("marker"):
                continue
            if e.get("date") != date:
                continue
            tid = e.get("thread_id") or "(none)"
            agg = by_thread.setdefault(tid, {
                "thread_id": tid, "world_id": e.get("world_id"),
                "usd": 0.0, "last_ts": e.get("ts")})
            agg["usd"] += float(e.get("usd") or 0.0)
            if (e.get("ts") or "") > (agg["last_ts"] or ""):
                agg["last_ts"] = e.get("ts")
        # subtract per-session resets that happened today
        out = []
        for tid, agg in by_thread.items():
            if tid == "(none)":
                out.append(agg)
                continue
            agg["usd"] = self.session_total(tid)
            out.append(agg)
        out.sort(key=lambda r: r.get("last_ts") or "", reverse=True)
        return out
