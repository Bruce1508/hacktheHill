import datetime as dt
import os

import pytest
from sqlalchemy import select

from backtrace.db.models import Complaint, ComplaintEmbedding, ComplaintFeatures, Customer, LlmCall, PipelineRun
from backtrace.db.session import get_session


DEMO_USERS = ("demo-agent", "demo-team-lead", "demo-compliance")


def _seed_one_complaint():
    database_url = os.environ["DATABASE_URL_PIPELINE"]
    with get_session(database_url) as session:
        session.merge(Customer(id="api-cust-1", region="north", plan="fiber_basic", segment="residential", node_id="node-north-1"))
        session.merge(
            Complaint(
                complaint_id="api-complaint-1",
                customer_id="api-cust-1",
                received_at=dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc),
                channel="web",
                text="My bill is wrong.",
                product="fiber_basic",
                region="north",
                node_id="node-north-1",
            )
        )
        session.commit()


def test_list_complaints_returns_seeded_row(client):
    _seed_one_complaint()
    response = client.get("/complaints", headers={"X-Demo-User": "demo-agent"})
    assert response.status_code == 200
    ids = [row["complaint_id"] for row in response.json()]
    assert "api-complaint-1" in ids

    database_url = os.environ["DATABASE_URL_PIPELINE"]
    with get_session(database_url) as session:
        session.delete(session.get(Complaint, "api-complaint-1"))
        session.delete(session.get(Customer, "api-cust-1"))
        session.commit()


def test_ingest_complaint_stores_and_embeds(client, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    database_url = os.environ["DATABASE_URL_PIPELINE"]
    with get_session(database_url) as session:
        session.merge(Customer(id="ingest-cust-1", region="north", plan="fiber_basic", segment="residential", node_id="node-north-1"))
        session.merge(
            PipelineRun(
                run_id="test-ingest-run",
                dataset_profile="dev",
                dataset_seed=1,
                config={},
                started_at=dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc),
            )
        )
        session.commit()

    response = client.post(
        "/complaints",
        headers={"X-Demo-User": "demo-agent"},
        json={
            "run_id": "test-ingest-run",
            "complaint_id": "ingest-complaint-1",
            "customer_id": "ingest-cust-1",
            "received_at": "2026-01-05T12:00:00Z",
            "channel": "web",
            "text": "My fiber connection keeps dropping.",
            "product": "fiber_basic",
            "region": "north",
            "node_id": "node-north-1",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body == {"complaint_id": "ingest-complaint-1", "needs_review": False, "embedded": True}

    with get_session(database_url) as session:
        assert session.get(Complaint, "ingest-complaint-1") is not None
        assert session.get(ComplaintFeatures, ("test-ingest-run", "ingest-complaint-1")) is not None
        assert session.get(ComplaintEmbedding, ("test-ingest-run", "ingest-complaint-1")) is not None

        session.delete(session.get(ComplaintEmbedding, ("test-ingest-run", "ingest-complaint-1")))
        session.delete(session.get(ComplaintFeatures, ("test-ingest-run", "ingest-complaint-1")))
        session.delete(session.get(Complaint, "ingest-complaint-1"))
        session.delete(session.get(Customer, "ingest-cust-1"))
        for call in session.execute(select(LlmCall).where(LlmCall.run_id == "test-ingest-run")).scalars():
            session.delete(call)
        session.delete(session.get(PipelineRun, "test-ingest-run"))
        session.commit()


def test_list_complaints_requires_a_demo_user(client):
    response = client.get("/complaints")

    assert response.status_code == 401


@pytest.mark.parametrize("demo_user", DEMO_USERS)
def test_each_demo_role_can_list_complaints(client, demo_user):
    response = client.get("/complaints", headers={"X-Demo-User": demo_user})

    assert response.status_code == 200


def test_unknown_demo_user_is_rejected(client):
    response = client.get(
        "/complaints",
        headers={"X-Demo-User": "unknown-user", "Cookie": "demo_user=demo-agent"},
    )

    assert response.status_code == 401


def test_demo_user_cookie_is_used_as_a_fallback(client):
    response = client.get(
        "/complaints",
        headers={"Cookie": "demo_user=demo-team-lead"},
    )

    assert response.status_code == 200


def test_demo_user_header_takes_precedence_over_cookie(client):
    response = client.get(
        "/complaints",
        headers={"X-Demo-User": "demo-agent", "Cookie": "demo_user=unknown-user"},
    )

    assert response.status_code == 200


@pytest.mark.parametrize("auth_mode", (None, "auth0"))
def test_demo_auth_fails_closed_for_unavailable_mode(client, monkeypatch, auth_mode):
    if auth_mode is None:
        monkeypatch.delenv("AUTH_MODE", raising=False)
    else:
        monkeypatch.setenv("AUTH_MODE", auth_mode)

    response = client.get(
        "/complaints",
        headers={"X-Demo-User": "demo-agent"},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Authentication service unavailable"}


@pytest.mark.parametrize(
    "query",
    ("limit=0", "limit=101", "offset=-1", "offset=10001"),
)
def test_list_complaints_rejects_invalid_pagination(client, query):
    response = client.get(
        f"/complaints?{query}",
        headers={"X-Demo-User": "demo-agent"},
    )

    assert response.status_code == 422


def test_list_complaints_accepts_bounded_pagination(client):
    response = client.get(
        "/complaints?limit=1&offset=0",
        headers={"X-Demo-User": "demo-agent"},
    )

    assert response.status_code == 200
    assert len(response.json()) <= 1


def test_health_remains_public(client):
    response = client.get("/health")

    assert response.status_code == 200


def test_complaints_documents_both_demo_auth_methods(client):
    operation = client.get("/openapi.json").json()["paths"]["/complaints"]["get"]

    assert operation["security"] == [
        {"DemoUserHeader": []},
        {"DemoUserCookie": []},
    ]
