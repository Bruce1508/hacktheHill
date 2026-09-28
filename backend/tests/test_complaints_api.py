import datetime as dt
import os

from backtrace.db.models import Complaint, Customer
from backtrace.db.session import get_session


def _seed_one_complaint():
    database_url = os.environ["DATABASE_URL_PIPELINE"]
    with get_session(database_url) as session:
        session.merge(Customer(id="api-cust-1", region="north", plan="fiber_basic", segment="residential", node_id="node-north-1"))
        session.merge(
            Complaint(
                complaint_id="api-complaint-1",
                customer_id="api-cust-1",
                received_at=dt.datetime.now(dt.timezone.utc),
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
    response = client.get("/complaints")
    assert response.status_code == 200
    ids = [row["complaint_id"] for row in response.json()]
    assert "api-complaint-1" in ids
