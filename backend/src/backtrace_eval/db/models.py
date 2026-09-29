"""ORM models for the `eval` schema — the answer key. Only the generator and
eval harness (this package) ever touch these; `backtrace` must not import
this module (enforced by tests/test_import_rules.py, one direction only)."""

import datetime as dt
from decimal import Decimal

from sqlalchemy import JSON, Numeric
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class EvalBase(DeclarativeBase):
    pass


class GoldEvent(EvalBase):
    __tablename__ = "gold_events"
    __table_args__ = {"schema": "eval"}

    id: Mapped[str] = mapped_column(primary_key=True)
    kind: Mapped[str]
    start_at: Mapped[dt.datetime]
    end_at: Mapped[dt.datetime]
    region: Mapped[str]
    affected_customer_ids: Mapped[list] = mapped_column(JSON)
    severity: Mapped[str]
    complaint_probability: Mapped[float]


class GoldComplaintLabel(EvalBase):
    __tablename__ = "gold_complaint_labels"
    __table_args__ = {"schema": "eval"}

    # References app.complaints.complaint_id at the DB level (enforced by the
    # 0003 migration's FK, in a different SQLAlchemy MetaData than EvalBase's).
    # Declaring it again here as an ORM ForeignKey fails to resolve across
    # metadata objects, so it's plain data here; the loader writes complaints first.
    complaint_id: Mapped[str] = mapped_column(primary_key=True)
    root_cause_id: Mapped[str | None]
    secondary_cause_id: Mapped[str | None]
    true_cause: Mapped[str]
    customer_claimed_cause: Mapped[str | None]
    misattributed: Mapped[bool]
    one_off: Mapped[bool]
    multi_issue: Mapped[bool]
    financial_impact: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    customer_impact_severity: Mapped[str]
    vulnerability_flag: Mapped[bool]
    vulnerability_mentioned: Mapped[bool]
    gold_remedy: Mapped[str]
    injected_defect: Mapped[str | None]
