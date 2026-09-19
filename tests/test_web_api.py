import io
import json
import time

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from ipmg.web.app import _render_report, create_app
from ipmg.web.db import Database

#: What the browser offers: the plain protocol plus the token-carrying one.
WS_AUTH = ["ipmg", "ipmg.token.test-token"]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("ipmg.core.engine.ping_ip", lambda ip, _t, _c: ("Active", 1.5))
    app = create_app(Database(tmp_path / "api.db"), token="test-token")
    with TestClient(app, headers={"Authorization": "Bearer test-token"}) as test_client:
        yield test_client


@pytest.fixture()
def anonymous(tmp_path):
    """A client that sends no access token."""
    app = create_app(Database(tmp_path / "anon.db"), token="test-token")
    with TestClient(app) as test_client:
        yield test_client


def wait_for_completion(client, scan_id, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        scan = client.get(f"/api/v1/scans/{scan_id}").json()
        if scan["status"] != "running":
            return scan
        time.sleep(0.02)
    raise AssertionError("scan did not finish in time")


def test_create_scan_and_fetch_results(client):
    response = client.post(
        "/api/v1/scans",
        json={"targets": "10.0.0.1\n10.0.0.2", "threads": 2, "source": "test"},
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["total"] == 2

    scan = wait_for_completion(client, payload["id"])
    assert scan["status"] == "complete"
    assert scan["status_counts"] == {"Active": 2}

    results = client.get(f"/api/v1/scans/{payload['id']}/results").json()
    assert {row["ip"] for row in results} == {"10.0.0.1", "10.0.0.2"}


def test_create_scan_rejects_invalid_targets(client):
    response = client.post("/api/v1/scans", json={"targets": "not-an-ip"})
    assert response.status_code == 400

    response = client.post("/api/v1/scans", json={})
    assert response.status_code == 400


def test_scan_expands_cidr_and_ranges(client):
    response = client.post(
        "/api/v1/scans",
        json={"targets": "192.168.0.0/30, 10.0.0.1-10.0.0.3", "threads": 4},
    )
    assert response.status_code == 201
    assert response.json()["total"] == 5  # 2 CIDR hosts + 3 range hosts


def test_report_downloads(client):
    scan_id = client.post("/api/v1/scans", json={"targets": "10.0.0.1"}).json()["id"]
    wait_for_completion(client, scan_id)

    csv_response = client.get(f"/api/v1/scans/{scan_id}/report?fmt=csv")
    assert csv_response.status_code == 200
    assert "10.0.0.1" in csv_response.text
    assert "attachment" in csv_response.headers["content-disposition"]

    md_response = client.get(f"/api/v1/scans/{scan_id}/report?fmt=md")
    assert "# IPMG Scan Report" in md_response.text

    json_response = client.get(f"/api/v1/scans/{scan_id}/report?fmt=json")
    assert json.loads(json_response.text)[0]["IP Address"] == "10.0.0.1"

    xlsx_response = client.get(f"/api/v1/scans/{scan_id}/report?fmt=xlsx")
    assert xlsx_response.status_code == 200
    assert len(xlsx_response.content) > 0

    assert client.get(f"/api/v1/scans/{scan_id}/report?fmt=pdf").status_code == 400


def test_upload_csv_and_json(client, tmp_path):
    csv_path = tmp_path / "targets.csv"
    pd.DataFrame({"IP Address": ["8.8.8.8", "192.168.9.0/30"]}).to_csv(csv_path, index=False)

    with open(csv_path, "rb") as handle:
        response = client.post(
            "/api/v1/upload", files={"file": ("targets.csv", handle, "text/csv")}
        )
    assert response.status_code == 200
    assert response.json()["count"] == 3

    response = client.post(
        "/api/v1/upload",
        files={"file": ("targets.json", json.dumps(["10.1.0.1", "10.1.0.2"]), "application/json")},
    )
    assert response.json()["targets"] == ["10.1.0.1", "10.1.0.2"]

    response = client.post(
        "/api/v1/upload",
        files={
            "file": ("targets.json", json.dumps([{"IP Address": "10.2.0.1"}]), "application/json")
        },
    )
    assert response.json()["targets"] == ["10.2.0.1"]

    response = client.post(
        "/api/v1/upload", files={"file": ("bad.pdf", b"%PDF", "application/pdf")}
    )
    assert response.status_code == 400


def test_stats_assets_and_delete(client):
    scan_id = client.post("/api/v1/scans", json={"targets": "10.0.0.1"}).json()["id"]
    wait_for_completion(client, scan_id)

    stats = client.get("/api/v1/stats").json()
    assert stats["scan_count"] == 1
    assert stats["latest_scan"]["id"] == scan_id

    assets = client.get("/api/v1/assets").json()
    assert assets[0]["ip"] == "10.0.0.1"

    assert client.delete(f"/api/v1/scans/{scan_id}").status_code == 204
    assert client.get(f"/api/v1/scans/{scan_id}").status_code == 404
    assert client.delete(f"/api/v1/scans/{scan_id}").status_code == 404


def test_cancel_requires_running_scan(client):
    scan_id = client.post("/api/v1/scans", json={"targets": "10.0.0.1"}).json()["id"]
    wait_for_completion(client, scan_id)
    assert client.post(f"/api/v1/scans/{scan_id}/cancel").status_code == 409


def test_websocket_rejects_cross_origin(client):
    with pytest.raises(Exception):
        with client.websocket_connect(
            "/api/v1/ws", subprotocols=WS_AUTH, headers={"origin": "http://evil.example"}
        ) as websocket:
            websocket.receive_json()


def test_websocket_receives_scan_events(client):
    with client.websocket_connect("/api/v1/ws", subprotocols=WS_AUTH) as websocket:
        scan_id = client.post("/api/v1/scans", json={"targets": "10.0.0.1"}).json()["id"]

        events = [websocket.receive_json() for _ in range(3)]
        types = [event["type"] for event in events]
        assert types == ["scan_started", "result", "scan_finished"]
        assert all(event["scan_id"] == scan_id for event in events)
        assert events[1]["result"]["ip"] == "10.0.0.1"
        assert events[2]["status"] == "complete"


def test_diff_endpoint_compares_scans(client):
    first = client.post("/api/v1/scans", json={"targets": "10.0.0.1"}).json()["id"]
    wait_for_completion(client, first)

    # Second scan sees an extra host.
    second = client.post("/api/v1/scans", json={"targets": "10.0.0.1\n10.0.0.2"}).json()["id"]
    wait_for_completion(client, second)

    diff = client.get(f"/api/v1/scans/{second}/diff").json()
    assert diff["baseline"]["id"] == first
    assert diff["current"]["id"] == second
    assert diff["summary"]["counts"] == {"new_host": 1}
    assert diff["changes"][0]["ip"] == "10.0.0.2"

    explicit = client.get(f"/api/v1/scans/{second}/diff?baseline={first}").json()
    assert explicit["summary"] == diff["summary"]


def test_diff_endpoint_without_a_baseline(client):
    scan_id = client.post("/api/v1/scans", json={"targets": "10.0.0.1"}).json()["id"]
    wait_for_completion(client, scan_id)

    response = client.get(f"/api/v1/scans/{scan_id}/diff")
    assert response.status_code == 404
    assert "No earlier scan" in response.json()["detail"]

    assert client.get("/api/v1/scans/9999/diff").status_code == 404


def test_diff_report_downloads(client):
    first = client.post("/api/v1/scans", json={"targets": "10.0.0.1"}).json()["id"]
    wait_for_completion(client, first)
    second = client.post("/api/v1/scans", json={"targets": "10.0.0.2"}).json()["id"]
    wait_for_completion(client, second)

    md = client.get(f"/api/v1/scans/{second}/diff/report?fmt=md")
    assert md.status_code == 200
    assert "# IPMG Change Report" in md.text
    assert f"ipmg_changes_{first}_to_{second}.md" in md.headers["content-disposition"]

    payload = json.loads(client.get(f"/api/v1/scans/{second}/diff/report?fmt=json").text)
    assert payload["summary"]["total_changes"] == 2

    csv_report = client.get(f"/api/v1/scans/{second}/diff/report?fmt=csv")
    assert csv_report.text.startswith("Change,Severity")

    assert client.get(f"/api/v1/scans/{second}/diff/report?fmt=pdf").status_code == 400


def test_upload_rejects_oversized_files(client, monkeypatch):
    monkeypatch.setattr("ipmg.web.app.MAX_UPLOAD_BYTES", 128)

    response = client.post(
        "/api/v1/upload",
        files={"file": ("targets.txt", b"10.0.0.1\n" * 200, "text/plain")},
    )
    assert response.status_code == 413


def test_index_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "IPMG Web" in response.text


def test_report_rendering_neutralizes_formula_cells():
    """A PTR record the scanned host controls must not become a live formula."""
    df = pd.DataFrame(
        [
            {
                "IP Address": "10.0.0.1",
                "Status": "Active",
                "Latency": 1.5,
                "Hostname": "=cmd|'/c calc'!A1",
            }
        ]
    )

    assert b"'=cmd" in _render_report(df, "csv")
    assert b",=cmd" not in _render_report(df, "csv")

    xlsx = pd.read_excel(io.BytesIO(_render_report(df, "xlsx")))
    assert xlsx.loc[0, "Hostname"] == "'=cmd|'/c calc'!A1"

    assert rb"'=cmd\|'/c calc'!A1" in _render_report(df, "md")


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/v1/stats"),
        ("get", "/api/v1/scans"),
        ("get", "/api/v1/assets"),
        ("post", "/api/v1/scans"),
        ("delete", "/api/v1/scans/1"),
        ("post", "/api/v1/scans/1/cancel"),
        ("post", "/api/v1/upload"),
    ],
)
def test_api_rejects_requests_without_a_token(anonymous, method, path):
    response = getattr(anonymous, method)(path)
    assert response.status_code == 401
    assert "access token" in response.json()["detail"]


def test_api_rejects_a_wrong_token(anonymous):
    response = anonymous.get("/api/v1/stats", headers={"Authorization": "Bearer nope"})
    assert response.status_code == 401


def test_api_refuses_a_token_in_the_query_string(anonymous):
    # URLs end up in access logs and browser history, so they never authenticate.
    assert anonymous.get("/api/v1/stats?token=test-token").status_code == 401


def test_websocket_accepts_a_bearer_header_from_non_browser_clients(anonymous):
    headers = {"Authorization": "Bearer test-token"}
    with anonymous.websocket_connect("/api/v1/ws", headers=headers) as websocket:
        assert websocket.accepted_subprotocol is None


def test_websocket_answers_with_the_plain_subprotocol(anonymous):
    # The token-carrying protocol must never be echoed back.
    with anonymous.websocket_connect("/api/v1/ws", subprotocols=WS_AUTH) as websocket:
        assert websocket.accepted_subprotocol == "ipmg"


def test_frontend_loads_without_a_token(anonymous):
    # The page itself holds no data; it needs the token only for API calls.
    assert anonymous.get("/").status_code == 200


@pytest.mark.parametrize(
    "subprotocols",
    [None, ["ipmg"], ["ipmg", "ipmg.token.wrong"]],
    ids=["none", "no-token", "wrong-token"],
)
def test_websocket_rejects_a_missing_or_wrong_token(anonymous, subprotocols):
    with pytest.raises(Exception):
        with anonymous.websocket_connect("/api/v1/ws", subprotocols=subprotocols) as websocket:
            websocket.receive_json()


def test_create_app_generates_a_token_when_none_is_given(tmp_path):
    first = create_app(Database(tmp_path / "a.db"))
    second = create_app(Database(tmp_path / "b.db"))
    assert len(first.state.token) >= 32
    assert first.state.token != second.state.token


def test_websocket_closes_a_subscriber_that_falls_behind(client):
    from starlette.websockets import WebSocketDisconnect

    from ipmg.web.manager import OVERFLOW

    manager = client.app.state.manager
    with client.websocket_connect("/api/v1/ws", subprotocols=WS_AUTH) as websocket:
        deadline = time.time() + 5
        while not manager._subscribers and time.time() < deadline:
            time.sleep(0.01)
        (queue,) = manager._subscribers
        manager._loop.call_soon_threadsafe(queue.put_nowait, OVERFLOW)

        with pytest.raises(WebSocketDisconnect) as closed:
            websocket.receive_json()
    assert closed.value.code == 1013
