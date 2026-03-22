"""Tests for WebSocket endpoint."""

from starlette.testclient import TestClient

from app.main import app


def test_websocket_auto_push_on_connect() -> None:
    """WebSocket should auto-push state and history on connect."""
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        # state is pushed automatically on connect
        data = ws.receive_json()
        assert data["type"] == "state"
        assert "is_downloading" in data["data"]
        assert "queue_size" in data["data"]
        assert "connected_clients" in data["data"]

        # history_complete follows immediately (empty DB)
        data = ws.receive_json()
        assert data["type"] == "history_complete"
        assert data["data"]["total"] == 0


def test_websocket_request_state() -> None:
    """Client can still explicitly request state."""
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        # Consume auto-push messages
        ws.receive_json()  # state
        ws.receive_json()  # history_complete

        # Explicitly request state
        ws.send_json({"type": "request_state"})
        data = ws.receive_json()
        assert data["type"] == "state"


def test_websocket_request_history() -> None:
    """Client can still explicitly request history."""
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        # Consume auto-push messages
        ws.receive_json()  # state
        ws.receive_json()  # history_complete

        # Explicitly request history
        ws.send_json({"type": "request_history"})
        data = ws.receive_json()
        assert data["type"] == "history_complete"
        assert data["data"]["total"] == 0


def test_websocket_invalid_json() -> None:
    """WebSocket should ignore invalid JSON without disconnecting."""
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        # Consume auto-push messages
        ws.receive_json()  # state
        ws.receive_json()  # history_complete

        ws.send_text("not json")
        # Should still respond to valid messages after invalid one
        ws.send_json({"type": "request_state"})
        data = ws.receive_json()
        assert data["type"] == "state"
