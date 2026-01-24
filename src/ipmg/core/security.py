import logging

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
    print(DISCLAIMER)
