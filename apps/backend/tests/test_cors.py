from app.main import create_app


def preflight(client, origin):
    return client.options(
        "/api/items",
        headers={"Origin": origin, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"},
    )


def test_allowed_origin_gets_the_cors_headers():
    client = create_app(connect=lambda: None, cors_origins="https://app.example.com").test_client()
    response = preflight(client, "https://app.example.com")
    assert response.headers["Access-Control-Allow-Origin"] == "https://app.example.com"
    assert "POST" in response.headers["Access-Control-Allow-Methods"]
    assert "Content-Type" in response.headers["Access-Control-Allow-Headers"]
    assert response.headers["Vary"] == "Origin"


def test_other_origins_get_nothing():
    client = create_app(connect=lambda: None, cors_origins="https://app.example.com").test_client()
    assert "Access-Control-Allow-Origin" not in preflight(client, "https://evil.example").headers


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("CORS_ALLOW_ORIGIN", raising=False)
    client = create_app(connect=lambda: None).test_client()
    assert "Access-Control-Allow-Origin" not in preflight(client, "https://app.example.com").headers


def test_several_origins_and_wildcard(monkeypatch):
    client = create_app(connect=lambda: None, cors_origins="http://a.example, http://b.example").test_client()
    assert preflight(client, "http://b.example").headers["Access-Control-Allow-Origin"] == "http://b.example"
    wildcard = create_app(connect=lambda: None, cors_origins="*").test_client()
    assert preflight(wildcard, "http://anything").headers["Access-Control-Allow-Origin"] == "*"


def test_environment_variable_is_used(monkeypatch):
    monkeypatch.setenv("CORS_ALLOW_ORIGIN", "http://app.example.com")
    client = create_app(connect=lambda: None).test_client()
    assert client.get("/health", headers={"Origin": "http://app.example.com"}).headers["Access-Control-Allow-Origin"] == "http://app.example.com"
