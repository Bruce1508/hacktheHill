# backend/tests/test_health.py
def test_health_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    # Worker heartbeat (§11): "unknown"/"dead"/"alive" depending on whether a
    # worker has run in this test DB; never absent, never a 5xx.
    assert body["worker"] in ("unknown", "dead", "alive")
