import datetime as dt

from sqlalchemy import ForeignKey, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = {"schema": "app"}

    id: Mapped[str] = mapped_column(primary_key=True)
    region: Mapped[str]
    plan: Mapped[str]
    segment: Mapped[str]  # "residential" | "business"
    # node_id is plain text (no FK) until network_nodes/network_links land
    # in the linking-layer migration (§7.1) — see design doc §8.3.
    node_id: Mapped[str]
    # Nullable: only the dev/demo generator sets this; tiny customers don't.
    tenure_months: Mapped[int | None] = mapped_column(default=None)


class NetworkNode(Base):
    __tablename__ = "network_nodes"
    __table_args__ = {"schema": "app"}

    id: Mapped[str] = mapped_column(primary_key=True)
    region: Mapped[str]
    kind: Mapped[str]


class NetworkLink(Base):
    __tablename__ = "network_links"
    __table_args__ = {"schema": "app"}

    id: Mapped[str] = mapped_column(primary_key=True)
    region: Mapped[str]
    from_node_id: Mapped[str] = mapped_column(ForeignKey("app.network_nodes.id"))
    to_node_id: Mapped[str] = mapped_column(ForeignKey("app.network_nodes.id"))
    redundant: Mapped[bool]


class Event(Base):
    __tablename__ = "events"
    __table_args__ = {"schema": "app"}

    id: Mapped[str] = mapped_column(primary_key=True)
    source: Mapped[str]  # network_alarm | billing_run | deploy | policy_change
    start_at: Mapped[dt.datetime]
    end_at: Mapped[dt.datetime]
    scope: Mapped[dict] = mapped_column(JSON)
    search_text: Mapped[str]


class Complaint(Base):
    __tablename__ = "complaints"
    __table_args__ = {"schema": "app"}

    complaint_id: Mapped[str] = mapped_column(primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("app.customers.id"))
    received_at: Mapped[dt.datetime]
    channel: Mapped[str]  # phone | email | chat | web
    text: Mapped[str]
    product: Mapped[str]
    region: Mapped[str]
    node_id: Mapped[str]
    is_repeat: Mapped[bool] = mapped_column(default=False)
    prior_complaint_ids: Mapped[list] = mapped_column(JSON, default=list)
    escalation_status: Mapped[str] = mapped_column(default="open")
    escalated_at: Mapped[dt.datetime | None] = mapped_column(default=None)
    sla_deadline: Mapped[dt.datetime | None] = mapped_column(default=None)


class Telemetry(Base):
    __tablename__ = "telemetry"
    __table_args__ = {"schema": "app"}

    # No single-column PK: a hypertable row is identified by (node_id or
    # link_id, sampled_at) — see the uq_app_telemetry_key constraint in 0003.
    node_id: Mapped[str | None] = mapped_column(ForeignKey("app.network_nodes.id"), primary_key=True)
    link_id: Mapped[str | None] = mapped_column(ForeignKey("app.network_links.id"), primary_key=True)
    sampled_at: Mapped[dt.datetime] = mapped_column(primary_key=True)
    optical_power_dbm: Mapped[float]
    errored_seconds: Mapped[int]
    packet_loss_pct: Mapped[float]
    latency_ms: Mapped[float]
    alarm: Mapped[bool]
