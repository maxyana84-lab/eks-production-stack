from app.main import create_app


def client(monkeypatch=None):
    return create_app().test_client()


def test_index_and_health():
    c = client()
    assert c.get("/").status_code == 200
    assert b"EKS Production Stack" in c.get("/").data
    assert c.get("/health").get_json() == {"status": "ok"}


def test_config_uses_api_url(monkeypatch):
    monkeypatch.setenv("API_URL", "https://api.example.com")
    body = client().get("/config.js").get_data(as_text=True)
    assert 'apiUrl: "https://api.example.com"' in body


def test_metrics_exposed():
    c = client()
    c.get("/")
    c.get("/missing")
    text = c.get("/metrics").get_data(as_text=True)
    assert 'service="frontend"' in text and 'code="404"' in text


def test_config_cannot_be_broken_by_the_value(monkeypatch):
    monkeypatch.setenv("API_URL", 'x"; alert(1); //')
    body = client().get("/config.js").get_data(as_text=True)
    assert body == 'window.APP_CONFIG = { apiUrl: "x\\"; alert(1); //" };'
