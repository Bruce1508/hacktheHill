# backend/tests/test_models.py
import datetime as dt
import os

from backtrace.db.models import Complaint, Customer
from backtrace.db.session import get_session


def test_can_insert_and_read_customer_and_complaint():
    database_url = os.environ["DATABASE_URL_PIPELINE"]
    with get_session(database_url) as session:
        customer = Customer(id="test-cust-1", region="north", plan="fiber_basic", segment="residential", node_id="node-north-1")
        session.merge(customer)
        session.commit()

        complaint = Complaint(
            complaint_id="test-complaint-1",
            customer_id="test-cust-1",
            received_at=dt.datetime.now(dt.timezone.utc),
            channel="web",
            text="My internet is down.",
            product="fiber_basic",
            region="north",
            node_id="node-north-1",
        )
        session.merge(complaint)
        session.commit()

        fetched = session.get(Complaint, "test-complaint-1")
        assert fetched is not None
        assert fetched.customer_id == "test-cust-1"

        session.delete(fetched)
        session.delete(session.get(Customer, "test-cust-1"))
        session.commit()
