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


def launch_capturing(tmp_path, monkeypatch):
    """Run run_dashboard without serving; return (opened URL, app passed to uvicorn)."""
    monkeypatch.setattr(server, "_has_display", lambda: True)
    served = {}
    monkeypatch.setattr(server.uvicorn, "run", lambda app, **_k: served.setdefault("app", app))
    opened = []

    class FakeTimer:
        def __init__(self, _delay, _fn, args=()):
            opened.extend(args)

        def start(self):
            pass

    monkeypatch.setattr(server.threading, "Timer", FakeTimer)
    server.run_dashboard(db_path=str(tmp_path / "test.db"))
    return opened[0], served["app"]


def test_run_dashboard_opens_the_browser_with_the_access_token(tmp_path, monkeypatch):
    monkeypatch.delenv("IPMG_WEB_TOKEN", raising=False)
    url, app = launch_capturing(tmp_path, monkeypatch)

    assert url == f"http://127.0.0.1:8080/?token={app.state.token}"
    assert len(app.state.token) >= 32


def test_run_dashboard_uses_a_pinned_token_from_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("IPMG_WEB_TOKEN", "pinned-token-for-my-proxy")
    url, app = launch_capturing(tmp_path, monkeypatch)

    assert app.state.token == "pinned-token-for-my-proxy"
    assert url.endswith("?token=pinned-token-for-my-proxy")
