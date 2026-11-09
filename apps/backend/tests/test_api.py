import pytest

from app.main import create_app


class FakeCursor:
    def __init__(self, store):
        self.store, self._rows = store, []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        if sql.startswith("INSERT"):
            self.store.append(params[0])
            self._rows = [(len(self.store),)]
        elif sql.startswith("SELECT"):
            self._rows = [(i + 1, n) for i, n in reversed(list(enumerate(self.store)))]

    def fetchone(self):
        return self._rows[0]

    def fetchall(self):
        return self._rows


class FakeConn:
    def __init__(self, store):
        self.store = store

    def cursor(self):
        return FakeCursor(self.store)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def close(self):
        pass


@pytest.fixture
def client():
    store = []
    return create_app(connect=lambda: FakeConn(store)).test_client()


def test_health(client):
    assert client.get("/health").get_json() == {"status": "ok"}


def test_ready_reports_database_outage():
    def broken():
        raise ConnectionError("down")

    response = create_app(connect=broken).test_client().get("/ready")
    assert response.status_code == 503
    assert response.get_json()["status"] == "database unavailable"


def test_items_roundtrip(client):
    assert client.post("/api/items", json={"name": "first"}).status_code == 201
    client.post("/api/items", json={"name": "second"})
    body = client.get("/api/items").get_json()
    assert [i["name"] for i in body["items"]] == ["second", "first"]


def test_item_requires_a_name(client):
    assert client.post("/api/items", json={"name": "  "}).status_code == 400
    assert client.post("/api/items", data="not json").status_code == 400


def test_metrics_count_requests_by_route_and_code(client):
    client.get("/health")
    client.get("/health")
    client.get("/does-not-exist")
    text = client.get("/metrics").get_data(as_text=True)
    assert 'http_requests_total{code="200",method="GET",path="/health",service="backend"} 2.0' in text
    assert 'path="unmatched"' in text and 'code="404"' in text
    assert "http_request_duration_seconds_bucket" in text
    assert "http_requests_in_flight" in text


def test_metrics_endpoint_is_not_counted(client):
    client.get("/metrics")
    assert 'path="/metrics"' not in client.get("/metrics").get_data(as_text=True)


def test_a_scrape_is_not_an_active_connection(client):
    client.get("/health")
    text = client.get("/metrics").get_data(as_text=True)
    assert 'http_requests_in_flight{service="backend"} 0.0' in text
