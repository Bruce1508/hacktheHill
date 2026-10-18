import datetime as dt
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, func, JSON, Numeric
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


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    __table_args__ = {"schema": "app"}

    run_id: Mapped[str] = mapped_column(primary_key=True)
    dataset_profile: Mapped[str]
    dataset_seed: Mapped[int]
    config: Mapped[dict] = mapped_column(JSON)
    started_at: Mapped[dt.datetime]
    finished_at: Mapped[dt.datetime | None] = mapped_column(default=None)
    stage_timings: Mapped[dict | None] = mapped_column(JSON, default=None)


class LlmCache(Base):
    __tablename__ = "llm_cache"
    __table_args__ = {"schema": "app"}

    # sha256 hex of (model, prompt_version, input, ...) — see llm/cache.py.
    key: Mapped[str] = mapped_column(primary_key=True)
    response: Mapped[dict] = mapped_column(JSON)
    # server_default must be declared here too (not just in the migration's
    # DDL) or SQLAlchemy sends an explicit NULL for an unset attribute and
    # violates NOT NULL — confirmed by an actual insert attempt.
    created_at: Mapped[dt.datetime] = mapped_column(server_default=func.now())


class LlmCall(Base):
    __tablename__ = "llm_calls"
    __table_args__ = {"schema": "app"}

    # Composite PK (id, called_at): a hypertable's PK/unique index must
    # include the partitioning column — see migration 0003.
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    called_at: Mapped[dt.datetime] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("app.pipeline_runs.run_id"))
    stage: Mapped[str]  # extraction | embedding
    model: Mapped[str]
    prompt_version: Mapped[str]
    tokens_in: Mapped[int]
    tokens_out: Mapped[int]
    latency_ms: Mapped[float]
    cost_estimate: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    cache_hit: Mapped[bool]


class ComplaintFeatures(Base):
    __tablename__ = "complaint_features"
    __table_args__ = {"schema": "app"}

    run_id: Mapped[str] = mapped_column(ForeignKey("app.pipeline_runs.run_id"), primary_key=True)
    complaint_id: Mapped[str] = mapped_column(ForeignKey("app.complaints.complaint_id"), primary_key=True)
    extraction: Mapped[dict] = mapped_column(JSON)
    extraction_version: Mapped[str]
    pii_redacted_text: Mapped[str]
    needs_review: Mapped[bool] = mapped_column(default=False)


class ComplaintEmbedding(Base):
    __tablename__ = "complaint_embeddings"
    __table_args__ = {"schema": "app"}

    run_id: Mapped[str] = mapped_column(ForeignKey("app.pipeline_runs.run_id"), primary_key=True)
    complaint_id: Mapped[str] = mapped_column(ForeignKey("app.complaints.complaint_id"), primary_key=True)
    model_version: Mapped[str]
    embedding: Mapped[list[float]] = mapped_column(Vector(768))


class ComplaintLayout(Base):
    __tablename__ = "complaint_layout"
    __table_args__ = {"schema": "app"}

    run_id: Mapped[str] = mapped_column(ForeignKey("app.pipeline_runs.run_id"), primary_key=True)
    complaint_id: Mapped[str] = mapped_column(ForeignKey("app.complaints.complaint_id"), primary_key=True)
    x: Mapped[float]
    y: Mapped[float]
    layout_version: Mapped[str]


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = {"schema": "app"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    type: Mapped[str]  # pipeline.run | pipeline.stage | letters.draft
    stage: Mapped[str | None] = mapped_column(default=None)
    run_id: Mapped[str] = mapped_column(ForeignKey("app.pipeline_runs.run_id"))
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(server_default="queued")  # queued|running|done|failed
    attempts: Mapped[int] = mapped_column(server_default="0")
    locked_at: Mapped[dt.datetime | None] = mapped_column(default=None)
    error: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[dt.datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(server_default=func.now())


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeat"
    __table_args__ = {"schema": "app"}

    id: Mapped[bool] = mapped_column(primary_key=True, default=True)
    updated_at: Mapped[dt.datetime] = mapped_column(server_default=func.now())


class DetectedAnomaly(Base):
    __tablename__ = "detected_anomalies"
    __table_args__ = {"schema": "app"}

    id: Mapped[str] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("app.pipeline_runs.run_id"))
    node_id: Mapped[str | None] = mapped_column(ForeignKey("app.network_nodes.id"), default=None)
    link_id: Mapped[str | None] = mapped_column(ForeignKey("app.network_links.id"), default=None)
    metric: Mapped[str]
    start_at: Mapped[dt.datetime]
    end_at: Mapped[dt.datetime]
    peak_score: Mapped[float]
    method: Mapped[str]  # "rolling_z_v1"


class ComplaintBurst(Base):
    __tablename__ = "complaint_bursts"
    __table_args__ = {"schema": "app"}

    id: Mapped[str] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("app.pipeline_runs.run_id"))
    region: Mapped[str]
    start_at: Mapped[dt.datetime]
    end_at: Mapped[dt.datetime]
    complaint_count: Mapped[int]
    peak_score: Mapped[float]


class SymptomCluster(Base):
    __tablename__ = "symptom_clusters"
    __table_args__ = {"schema": "app"}

    id: Mapped[str] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("app.pipeline_runs.run_id"))
    label: Mapped[int]  # HDBSCAN label, >= 0
    size: Mapped[int]
    method: Mapped[str]  # "text" | "text+structured"


class SymptomClusterMember(Base):
    __tablename__ = "symptom_cluster_members"
    __table_args__ = {"schema": "app"}

    run_id: Mapped[str] = mapped_column(ForeignKey("app.pipeline_runs.run_id"), primary_key=True)
    complaint_id: Mapped[str] = mapped_column(ForeignKey("app.complaints.complaint_id"), primary_key=True)
    cluster_id: Mapped[str | None] = mapped_column(ForeignKey("app.symptom_clusters.id"), default=None)  # null = noise


class Cohort(Base):
    __tablename__ = "cohorts"
    __table_args__ = {"schema": "app"}

    id: Mapped[str] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("app.pipeline_runs.run_id"))
    status: Mapped[str] = mapped_column(server_default="proposed")
    kind: Mapped[str]  # "linked" | "no_linked_evidence"
    hypothesis: Mapped[str | None] = mapped_column(default=None)
    hypothesis_citations: Mapped[dict | list | None] = mapped_column(JSON, default=None)
    confidence: Mapped[float | None] = mapped_column(default=None)


class CohortMember(Base):
    __tablename__ = "cohort_members"
    __table_args__ = {"schema": "app"}

    run_id: Mapped[str] = mapped_column(ForeignKey("app.pipeline_runs.run_id"), primary_key=True)
    complaint_id: Mapped[str] = mapped_column(ForeignKey("app.complaints.complaint_id"), primary_key=True)
    cohort_id: Mapped[str] = mapped_column(ForeignKey("app.cohorts.id"))
    membership_score: Mapped[float]
    assigned_by: Mapped[str]  # "batch"
    needs_review: Mapped[bool]


class CohortEventLink(Base):
    __tablename__ = "cohort_event_links"
    __table_args__ = {"schema": "app"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cohort_id: Mapped[str] = mapped_column(ForeignKey("app.cohorts.id"))
    run_id: Mapped[str] = mapped_column(ForeignKey("app.pipeline_runs.run_id"))
    event_id: Mapped[str | None] = mapped_column(ForeignKey("app.events.id"), default=None)
    anomaly_id: Mapped[str | None] = mapped_column(ForeignKey("app.detected_anomalies.id"), default=None)
    overlap_score: Mapped[float]
    time_offset_minutes: Mapped[float | None] = mapped_column(default=None)
    evidence: Mapped[dict] = mapped_column(JSON)
