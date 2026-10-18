import argparse
import datetime as dt
import json
from decimal import Decimal
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert as pg_insert

from backtrace.db.models import Complaint, Customer, Event, NetworkLink, NetworkNode, Telemetry
from backtrace.db.session import get_session
from backtrace_eval.db.models import GoldComplaintLabel, GoldEvent


def load_fixture_into_db(fixture_dir: Path, database_url: str) -> None:
    """Load a flat `tiny`-profile fixture (customers/events/complaints.json)."""
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


def _bulk_upsert_telemetry(session, rows: list[dict], chunk_size: int = 2000) -> None:
    """Core-level chunked upsert; 193k+ dev-world rows would be far too slow
    through per-row ORM merge()."""
    table = Telemetry.__table__
    for start in range(0, len(rows), chunk_size):
        chunk = rows[start : start + chunk_size]
        values = [{**row, "sampled_at": dt.datetime.fromisoformat(row["sampled_at"])} for row in chunk]
        stmt = pg_insert(table).values(values).on_conflict_do_nothing(constraint="uq_app_telemetry_key")
        session.execute(stmt)


def load_dev_world_into_db(fixture_dir: Path, database_url: str) -> None:
    """Load a `dev`-profile fixture: app/*.json + eval/*.json, written by
    write_dev_world. Requires the bt_eval role (both schemas)."""
    app_dir, eval_dir = fixture_dir / "app", fixture_dir / "eval"
    manifest = json.loads((fixture_dir / "manifest.json").read_text())
    customers = json.loads((app_dir / "customers.json").read_text())
    network_nodes = json.loads((app_dir / "network_nodes.json").read_text())
    network_links = json.loads((app_dir / "network_links.json").read_text())
    events = json.loads((app_dir / "events.json").read_text())
    telemetry = json.loads((app_dir / "telemetry.json").read_text())
    complaints = json.loads((app_dir / "complaints.json").read_text())
    gold_events = json.loads((eval_dir / "gold_events.json").read_text())
    gold_complaint_labels = json.loads((eval_dir / "gold_complaint_labels.json").read_text())

    # Dependency order: topology and customers before events/complaints that
    # reference them; complaints before gold_complaint_labels (FK).
    with get_session(database_url) as session:
        for row in network_nodes:
            session.merge(NetworkNode(**row))
        for row in network_links:
            session.merge(NetworkLink(**row))
        for row in customers:
            session.merge(Customer(**row))
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
                    is_repeat=c["is_repeat"],
                    prior_complaint_ids=c["prior_complaint_ids"],
                    escalation_status=c["escalation_status"],
                    escalated_at=dt.datetime.fromisoformat(c["escalated_at"]) if c["escalated_at"] else None,
                    sla_deadline=dt.datetime.fromisoformat(c["sla_deadline"]) if c["sla_deadline"] else None,
                )
            )
        session.commit()

        _bulk_upsert_telemetry(session, telemetry)
        session.commit()

        for row in gold_events:
            session.merge(GoldEvent(**row))
        for row in gold_complaint_labels:
            session.merge(
                GoldComplaintLabel(
                    complaint_id=row["complaint_id"],
                    root_cause_id=row["root_cause_id"],
                    secondary_cause_id=row["secondary_cause_id"],
                    true_cause=row["true_cause"],
                    customer_claimed_cause=row["customer_claimed_cause"],
                    misattributed=row["misattributed"],
                    one_off=row["one_off"],
                    multi_issue=row["multi_issue"],
                    financial_impact=Decimal(row["financial_impact"]),
                    customer_impact_severity=row["customer_impact_severity"],
                    vulnerability_flag=row["vulnerability_flag"],
                    vulnerability_mentioned=row["vulnerability_mentioned"],
                    gold_remedy=row["gold_remedy"],
                    injected_defect=row["injected_defect"],
                )
            )
        session.commit()

    print(f"Loaded dev world ({manifest['profile']}, seed {manifest['seed']}): {manifest['counts']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--database-url", required=True)
    args = parser.parse_args()
    fixture_dir = Path(args.fixture)
    if (fixture_dir / "manifest.json").exists():
        load_dev_world_into_db(fixture_dir, args.database_url)
    else:
        load_fixture_into_db(fixture_dir, args.database_url)


if __name__ == "__main__":
    main()
