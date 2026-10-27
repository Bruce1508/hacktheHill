# backend/tests/test_health.py
def test_health_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    # Worker heartbeat (§11): "unknown"/"dead"/"alive" depending on whether a
    # worker has run in this test DB; never absent, never a 5xx.
    assert body["worker"] in ("unknown", "dead", "alive")


def test_cors_allows_web_origin_with_credentials(client):
    response = client.options(
        "/cohorts/x/confirm",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert response.headers["access-control-allow-credentials"] == "true"
