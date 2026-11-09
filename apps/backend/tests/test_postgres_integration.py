"""Runs the backend against a REAL PostgreSQL (the unit tests use a fake connection).

Skipped unless INTEGRATION_DB_HOST is set. CI starts a postgres service container; locally:
    INTEGRATION_DB_HOST=127.0.0.1 INTEGRATION_DB_PORT=5432 INTEGRATION_DB_USER=app \
    INTEGRATION_DB_PASSWORD=secret INTEGRATION_DB_NAME=appdb pytest tests/test_postgres_integration.py
"""
import os

import pytest

from app.main import create_app

pytestmark = pytest.mark.skipif(not os.environ.get("INTEGRATION_DB_HOST"), reason="no INTEGRATION_DB_HOST: no real database")


@pytest.fixture
def env(monkeypatch):
    for key, name in (("DB_HOST", "HOST"), ("DB_PORT", "PORT"), ("DB_USER", "USER"), ("DB_PASSWORD", "PASSWORD"), ("DB_NAME", "NAME")):
        monkeypatch.setenv(key, os.environ[f"INTEGRATION_DB_{name}"])
    monkeypatch.setenv("DB_CONNECT_TIMEOUT", "3")


def test_ready_with_the_right_credentials(env):
    response = create_app().test_client().get("/ready")
    assert response.status_code == 200 and response.get_json() == {"status": "ready"}


def test_ready_reports_a_wrong_password_and_health_stays_up(env, monkeypatch):
    monkeypatch.setenv("DB_PASSWORD", "definitely-wrong")
    client = create_app().test_client()
    assert client.get("/ready").status_code == 503
    assert client.get("/health").status_code == 200       # liveness must not depend on the database


def test_items_roundtrip_with_awkward_values(env):
    client = create_app().test_client()
    names = ["plain", "with 'quote' and ; semicolon", "unicode: żółć ✓", "x" * 500]
    for name in names:
        assert client.post("/api/items", json={"name": name}).status_code == 201
    stored = [i["name"] for i in client.get("/api/items").get_json()["items"]]
    for name in names:
        assert name in stored


def test_sql_injection_is_just_text(env):
    client = create_app().test_client()
    payload = "x'); DROP TABLE items; --"
    assert client.post("/api/items", json={"name": payload}).status_code == 201
    assert payload in [i["name"] for i in client.get("/api/items").get_json()["items"]]   # the table still exists
