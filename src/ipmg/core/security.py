"""The authorization notice shown before IPMG sends any probe."""

from __future__ import annotations

import logging
from typing import Sequence

from ipmg.reporting import ui

_DISCLAIMER_SHOWN = False

DISCLAIMER = "{probes} probes only {dash} scan only networks you are authorized to scan."

log = logging.getLogger(__name__)


def print_disclaimer_once(probes: Sequence[str] = ("ICMP",)) -> None:
    """Print the authorization notice the first time a command probes hosts.

    ``probes`` names what the command will send, such as ``("ICMP", "TCP
    connect")``, so the notice never understates it.
    """
    global _DISCLAIMER_SHOWN

    if _DISCLAIMER_SHOWN:
        return

    _DISCLAIMER_SHOWN = True
    log.debug("authorization notice displayed")
    ui.note(DISCLAIMER.format(probes=" and ".join(probes), dash=ui.glyph("dash")))
