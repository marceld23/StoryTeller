"""Logging-Setup: Datei (config.logging.file) + Konsole (WARNING)."""

from __future__ import annotations

import logging

from ..config import Config

_done = False


def setup_logging(cfg: Config) -> logging.Logger:
    global _done
    logger = logging.getLogger("storyteller")
    if _done:
        return logger
    logger.setLevel(getattr(logging, cfg.logging.level.upper(), logging.INFO))
    fp = cfg.path(cfg.logging.file)
    fp.parent.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(fp, encoding="utf-8")
    fh.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(fh)
    ch = logging.StreamHandler()
    ch.setLevel(logging.WARNING)
    logger.addHandler(ch)
    _done = True
    return logger
