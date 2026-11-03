def test_health_is_public(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.get_json() == {"status": "ok"}


def test_heartbeat_reports_degraded_without_database(client):
    r = client.get("/api/v1/heartbeat")
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"] == "degraded"
    assert body["service"] == "eaexplorer-api"
    assert body["database"]["reachable"] is False
    assert "X-Request-ID" in r.headers


def test_openapi_lists_the_endpoints(client):
    spec = client.get("/api/openapi.json").get_json()
    assert spec["info"]["title"] == "EA Explorer API"
    for path in ("/api/v1/heartbeat", "/api/v1/me", "/api/v1/jobs/heartbeat", "/api/v1/audit"):
        assert path in spec["paths"]
    assert "bearerAuth" in spec["components"]["securitySchemes"]


def test_swagger_ui_is_served(client):
    r = client.get("/api/docs")
    assert r.status_code == 200
    assert b"swagger" in r.data.lower()
