"""The authorization notice shown before IPMG sends any probe."""

from __future__ import annotations

import logging

from ipmg.reporting import ui

_DISCLAIMER_SHOWN = False

DISCLAIMER = "ICMP probes only {dash} scan only networks you are authorized to scan."

log = logging.getLogger(__name__)


def print_disclaimer_once() -> None:
    """Print the authorization notice the first time a command probes hosts."""
    global _DISCLAIMER_SHOWN

    if _DISCLAIMER_SHOWN:
        return

    _DISCLAIMER_SHOWN = True
    log.debug("authorization notice displayed")
    ui.note(DISCLAIMER.format(dash=ui.glyph("dash")))
