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
