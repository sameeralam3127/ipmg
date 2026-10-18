import os

import pytest

from ipmg.reporting import ui


@pytest.fixture(autouse=True)
def ui_on_stdout():
    """Put the UI back on stdout after a test that moved it to stderr.

    ``--json`` and ``--jsonl`` redirect the shared console for the rest of the
    process, which in a test run means for every test that follows.
    """
    yield
    ui.use_stderr(False)


@pytest.fixture(autouse=True)
def isolate_user_config(tmp_path, monkeypatch):
    """Keep a developer's own config file out of the tests.

    Every scan reads the user's config directory, so without this the suite
    would pass or fail depending on whose machine it ran on. The project's
    ``./ipmg.toml`` is left alone: that one is visible in the checkout, and a
    test that cares about it writes its own.
    """
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))


@pytest.fixture(autouse=True)
def isolate_snmp_credentials(monkeypatch):
    """Keep a developer's own IPMG_SNMP_* variables out of the tests."""
    for name in list(os.environ):
        if name.startswith("IPMG_SNMP_"):
            monkeypatch.delenv(name)


@pytest.fixture()
def stub_scan(monkeypatch):
    """Run scans against a scripted set of ping results."""
    state = {"statuses": {}}
    # Kept on the state so a test can wrap the loader instead of replacing it.
    state["load"] = lambda _sources: list(state["statuses"])

    monkeypatch.setattr("ipmg.services.scan_service.load_all_targets", state["load"])
    monkeypatch.setattr("ipmg.services.scan_service.save_results", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("ipmg.services.scan_service.print_summary", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "ipmg.core.engine.ping_ip",
        lambda ip, _timeout, _count: state["statuses"][ip],
    )
    return state
