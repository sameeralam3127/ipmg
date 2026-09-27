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
