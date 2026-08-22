from ipmg.web import server


def test_is_loopback():
    assert server._is_loopback("127.0.0.1")
    assert server._is_loopback("localhost")
    assert server._is_loopback("::1")
    assert not server._is_loopback("0.0.0.0")
    assert not server._is_loopback("10.0.0.5")


def test_has_display_linux_without_display(monkeypatch):
    monkeypatch.setattr(server.sys, "platform", "linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    assert server._has_display() is False


def test_has_display_linux_with_display(monkeypatch):
    monkeypatch.setattr(server.sys, "platform", "linux")
    monkeypatch.setenv("DISPLAY", ":0")
    assert server._has_display() is True


def test_has_display_non_linux(monkeypatch):
    monkeypatch.setattr(server.sys, "platform", "darwin")
    monkeypatch.delenv("DISPLAY", raising=False)
    assert server._has_display() is True


def test_run_dashboard_skips_browser_when_headless(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_has_display", lambda: False)
    monkeypatch.setattr(server.uvicorn, "run", lambda *a, **k: None)

    timers = []

    class FakeTimer:
        def __init__(self, *args, **kwargs):
            timers.append(args)

        def start(self):
            pass

    monkeypatch.setattr(server.threading, "Timer", FakeTimer)

    server.run_dashboard(db_path=str(tmp_path / "test.db"))

    assert timers == []


def test_run_dashboard_opens_browser_when_display_available(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_has_display", lambda: True)
    monkeypatch.setattr(server.uvicorn, "run", lambda *a, **k: None)

    timers = []

    class FakeTimer:
        def __init__(self, *args, **kwargs):
            timers.append(args)

        def start(self):
            pass

    monkeypatch.setattr(server.threading, "Timer", FakeTimer)

    server.run_dashboard(db_path=str(tmp_path / "test.db"))

    assert len(timers) == 1
