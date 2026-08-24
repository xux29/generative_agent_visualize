"""Smoke tests for viz_backend HTTP routes."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from viz_backend.app import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.get_json()["status"] == "ok"


def test_editor_status(client):
    r = client.get("/api/viz/editor/status")
    assert r.status_code == 200
    data = r.get_json()
    assert "configured" in data
    assert "model" in data


def test_mechanism_tabs(client):
    r = client.get("/api/viz/mechanism/tabs")
    assert r.status_code == 200
    tabs = r.get_json()["tabs"]
    assert len(tabs) == 4
    assert tabs[0]["id"] == "health"


def test_legacy_editor_status(client):
    r = client.get("/api/editor/status")
    assert r.status_code == 200


def test_index_page(client):
    r = client.get("/")
    assert r.status_code == 200


def test_editor_page(client):
    r = client.get("/editor")
    assert r.status_code == 200


def test_chat_stream_empty(client):
    r = client.post("/api/viz/editor/chat/stream", json={"message": ""})
    assert r.status_code == 400


def test_chat_stream_sse(client):
    r = client.post(
        "/api/viz/editor/chat/stream",
        json={"message": "你好，只需简短回复"},
    )
    assert r.status_code == 200
    assert "text/event-stream" in (r.content_type or "")
    body = r.get_data(as_text=True)
    assert "data:" in body
    assert "done" in body or "error" in body
