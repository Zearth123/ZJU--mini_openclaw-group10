import os
import time

os.environ["MINIOPENCLAW_ACCESS_TOKEN"] = "test-token"

from fastapi.testclient import TestClient

from backend.web_app import app, store


HEADERS = {"Authorization": "Bearer test-token"}


def test_auth_sessions_settings_and_path_boundary():
    with TestClient(app) as client:
        assert client.get("/api/sessions").status_code == 401
        created = client.post("/api/sessions", headers=HEADERS, json={"title": "API test"}).json()
        session_id = created["id"]
        assert any(row["id"] == session_id for row in client.get("/api/sessions", headers=HEADERS).json())

        settings = client.get("/api/settings", headers=HEADERS).json()
        assert "api_key" not in settings
        updated = client.patch("/api/settings", headers=HEADERS, json={"max_turns": 40}).json()
        assert updated["max_turns"] == 40

        assert client.get("/api/files", headers=HEADERS, params={"path": "../../"}).status_code == 403
        client.delete("/api/sessions/" + session_id, headers=HEADERS)


def test_fake_backend_run_persists_messages_and_events():
    with TestClient(app) as client:
        session_id = client.post("/api/sessions", headers=HEADERS, json={"title": "Run test"}).json()["id"]
        response = client.post(
            "/api/sessions/" + session_id + "/runs",
            headers=HEADERS,
            data={"task": "你好"},
        )
        assert response.status_code == 200
        run_id = response.json()["id"]

        deadline = time.time() + 5
        status = "queued"
        while time.time() < deadline:
            rows = client.get("/api/runs", headers=HEADERS).json()
            status = next(row["status"] for row in rows if row["id"] == run_id)
            if status in {"completed", "failed", "cancelled"}:
                break
            time.sleep(0.05)

        assert status == "completed"
        messages = client.get("/api/sessions/" + session_id + "/messages", headers=HEADERS).json()
        assert [message["role"] for message in messages] == ["user", "assistant"]
        event_rows = store.all(
            "SELECT type,created_at FROM run_events WHERE run_id=? ORDER BY seq",
            (run_id,),
        )
        assert event_rows[0]["type"] == "run_queued"
        assert event_rows[-1]["type"] == "run_finished"
        assistant = store.one(
            "SELECT created_at FROM messages WHERE session_id=? AND role='assistant' ORDER BY created_at DESC",
            (session_id,),
        )
        assert event_rows[-1]["created_at"] >= assistant["created_at"]
        client.delete("/api/sessions/" + session_id, headers=HEADERS)
