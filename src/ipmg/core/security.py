import logging

from rich.panel import Panel
from rich.text import Text

from ipmg.utils.helpers import console

_DISCLAIMER_SHOWN = False


DISCLAIMER = """
IPMG sends ICMP ping traffic.
Only use on networks where you have explicit authorization.
"""


def print_disclaimer_once() -> None:
    global _DISCLAIMER_SHOWN

    if _DISCLAIMER_SHOWN:
        return

    _DISCLAIMER_SHOWN = True
    logging.warning("IPMG disclaimer displayed")
    console.print(
        Panel(
            Text(DISCLAIMER.strip(), style="warning"),
            title="[ipmg.accent]Security Notice[/ipmg.accent]",
            border_style="warning",
            expand=False,
        )
    )
