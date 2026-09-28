import argparse
import datetime as dt
import json
from pathlib import Path

from backtrace.db.models import Complaint, Customer, Event
from backtrace.db.session import get_session


def load_fixture_into_db(fixture_dir: Path, database_url: str) -> None:
    customers = json.loads((fixture_dir / "customers.json").read_text())
    events = json.loads((fixture_dir / "events.json").read_text())
    complaints = json.loads((fixture_dir / "complaints.json").read_text())

    with get_session(database_url) as session:
        for c in customers:
            session.merge(Customer(**c))
        for e in events:
            session.merge(
                Event(
                    id=e["id"],
                    source=e["source"],
                    start_at=dt.datetime.fromisoformat(e["start_at"]),
                    end_at=dt.datetime.fromisoformat(e["end_at"]),
                    scope=e["scope"],
                    search_text=e["search_text"],
                )
            )
        for c in complaints:
            session.merge(
                Complaint(
                    complaint_id=c["complaint_id"],
                    customer_id=c["customer_id"],
                    received_at=dt.datetime.fromisoformat(c["received_at"]),
                    channel=c["channel"],
                    text=c["text"],
                    product=c["product"],
                    region=c["region"],
                    node_id=c["node_id"],
                )
            )
        session.commit()

    print(f"Loaded {len(customers)} customers, {len(events)} events, {len(complaints)} complaints")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--database-url", required=True)
    args = parser.parse_args()
    load_fixture_into_db(Path(args.fixture), args.database_url)


if __name__ == "__main__":
    main()
