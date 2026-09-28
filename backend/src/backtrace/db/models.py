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
