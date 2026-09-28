# Day 1 Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the Backtrace "running skeleton" — the Day 1 milestone from the design doc §19: monorepo, Docker Compose, DB + extension check, Alembic migrations for `app`/`eval` schemas + roles, FastAPI + Next.js skeleton, Pydantic contracts, and a `tiny` dataset that the web app can list end to end.

**Architecture:** One monorepo (this directory as root). Backend is a single Python package (`backtrace`) plus a role-separated sibling package (`backtrace_eval`) for the synthetic-data generator, both under `backend/src/`. Frontend is a single Next.js app under `apps/web/`. Postgres (TimescaleDB image) runs in Docker with two schemas (`app`, `eval`) and two least-privilege roles (`bt_pipeline`, `bt_eval`). `make up && make migrate && make seed-tiny` must bring the whole thing to life; the web app then lists the ~100 `tiny` complaints via a real API call.

**Tech Stack:** Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic, psycopg3, pytest, httpx. Next.js (App Router) + TypeScript + Tailwind CSS + shadcn/ui, pnpm. Docker + Docker Compose. TimescaleDB/PostgreSQL image with pgvector + pgvectorscale bundled.

**Spec:** `Backtrace — Technical Design Doc.md` (repo root) — §6 (architecture), §7 (data model), §15 (deployment), §19 Day 1 row.

## Scope decision (deviation from the spec's finished-system diagram, recorded per doc convention)

The spec's overall diagram (§6.2) and deployment section (§15) show a `worker` service in Docker Compose. Day 1's own done-criteria (§19) do **not** require the worker — the `jobs` table and worker loop are explicitly Day 2/§11 work, and today's worker would just be an empty shell with no tested behavior. This plan builds `db`, `api`, and `web` only. Task 2 leaves a `worker:` stanza commented out in `docker-compose.yml` with a one-line pointer to §11, so Day 2's plan adds real behavior instead of scaffolding a placeholder today.

## Global Constraints

- One monorepo, one FastAPI application, one PostgreSQL/TimescaleDB database, at most one Python worker — no microservices, no message broker. (§6, §6.1)
- Ground-truth evaluation data must be inaccessible to the application pipeline: enforced by DB role separation (`bt_pipeline` vs `bt_eval`) **and** a CI-enforced rule that `backtrace` must never import `backtrace_eval`. (§6.1 principle 5, §5.8)
- All generated data is labeled `synthetic` in the DB and, later, the UI. (§5.1)
- Stack is fixed: Python 3.12+/FastAPI/Pydantic/SQLAlchemy 2.x/Alembic; Next.js/React/TypeScript/Tailwind/shadcn/ui; Docker + Docker Compose. (§6.3)
- `tiny` profile: ~100 customers, ~100 complaints, ~3 root-cause events; must load in seconds; fixture is committed to the repo. (§5.1)
- Day 1 check: confirm TimescaleDB, pgvector, pgvectorscale, pg_textsearch availability on the local Docker image and record the result in the README; environment differences are handled by fallbacks, not separate code paths. (§15)
- Prefer simple, debuggable implementations; no speculative flexibility. (§6.1 principle 11)

---

## File Structure

```
hacktheHill/
├── .env.example
├── .gitignore
├── Makefile
├── README.md
├── configs/
│   └── worlds/
│       └── tiny.yaml                  # tiny-profile generator parameters
├── fixtures/
│   └── tiny/                          # committed generator output (JSON)
│       ├── customers.json
│       ├── events.json
│       └── complaints.json
├── infra/
│   └── docker-compose.yml
├── backend/
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   │       ├── 0001_schemas_and_roles.py
│   │       └── 0002_core_tables.py
│   ├── src/
│   │   ├── backtrace/
│   │   │   ├── __init__.py
│   │   │   ├── api/
│   │   │   │   ├── __init__.py
│   │   │   │   └── main.py            # FastAPI app: /health, /complaints
│   │   │   ├── contracts/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── extraction.py      # ComplaintExtraction (Pydantic)
│   │   │   │   ├── complaints.py      # API DTOs
│   │   │   │   └── evidence.py        # Evidence pack stub
│   │   │   └── db/
│   │   │       ├── __init__.py
│   │   │       ├── session.py
│   │   │       ├── models.py          # Customer, Event, Complaint
│   │   │       └── check_extensions.py
│   │   └── backtrace_eval/
│   │       ├── __init__.py
│   │       └── generator/
│   │           ├── __init__.py
│   │           ├── tiny.py            # pure, deterministic tiny-world generator
│   │           ├── cli.py             # `generate` subcommand → fixtures/tiny/
│   │           └── load.py            # loads a fixture into app schema (bt_eval role)
│   └── tests/
│       ├── conftest.py
│       ├── test_health.py
│       ├── test_complaints_api.py
│       ├── test_contracts.py
│       ├── test_generator_tiny.py
│       └── test_import_rules.py       # backtrace must not import backtrace_eval
└── apps/
    └── web/                           # Next.js app (scaffolded by create-next-app)
        └── src/
            └── app/
                ├── page.tsx           # lists tiny complaints via the API
                └── lib/
                    └── api.ts
```

---

### Task 1: Repo scaffolding & tooling

**Files:**
- Create: `.gitignore`
- Create: `README.md`
- Create: `Makefile`
- Create: `.env.example`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `git` repo with an initial commit; `Makefile` targets `up`, `down`, `migrate`, `seed-tiny`, `check-extensions`, `test-backend` that later tasks fill in with real commands (each target's real command is written in the task that needs it — no target is left as a placeholder past the task that uses it).

- [ ] **Step 1: Initialize git**

```bash
git init
git branch -m main
```

- [ ] **Step 2: Write `.gitignore`**

```gitignore
# Python
__pycache__/
*.pyc
.venv/
*.egg-info/
.pytest_cache/

# Node
node_modules/
.next/
apps/web/.env.local

# Env / secrets
.env

# OS
.DS_Store
```

- [ ] **Step 3: Write `.env.example`**

```bash
# --- Postgres (dev) ---
POSTGRES_DB=backtrace
POSTGRES_USER=backtrace_owner
POSTGRES_PASSWORD=devpassword
POSTGRES_PORT=5433

# Host-side URLs (used by `make migrate`, `make seed-tiny`, tests — run outside Docker)
DATABASE_URL_OWNER=postgresql+psycopg://backtrace_owner:devpassword@localhost:5433/backtrace
DATABASE_URL_PIPELINE=postgresql+psycopg://bt_pipeline:devpassword@localhost:5433/backtrace
DATABASE_URL_EVAL=postgresql+psycopg://bt_eval:devpassword@localhost:5433/backtrace

# --- App ---
AUTH_MODE=dev
GEMINI_API_KEY=
```

Copy it: `cp .env.example .env` (`.env` is gitignored; `.env.example` is committed).

- [ ] **Step 4: Write the root `Makefile` skeleton**

```makefile
include .env
export

.PHONY: up down migrate seed-tiny check-extensions test-backend

up:
	docker compose -f infra/docker-compose.yml up -d --build

down:
	docker compose -f infra/docker-compose.yml down

migrate:
	cd backend && DATABASE_URL=$(DATABASE_URL_OWNER) BT_PIPELINE_PASSWORD=$(POSTGRES_PASSWORD) BT_EVAL_PASSWORD=$(POSTGRES_PASSWORD) alembic upgrade head

seed-tiny:
	cd backend && PYTHONPATH=src python -m backtrace_eval.generator.load --fixture ../fixtures/tiny --database-url $(DATABASE_URL_EVAL)

check-extensions:
	cd backend && PYTHONPATH=src python -m backtrace.db.check_extensions --database-url $(DATABASE_URL_OWNER)

test-backend:
	cd backend && PYTHONPATH=src python -m pytest -q
```

- [ ] **Step 5: Write `README.md` stub**

```markdown
# Backtrace

Root-cause engine for customer complaints. See `Backtrace — Technical Design Doc.md`
for the full design; this README tracks what actually runs.

## Quickstart

\`\`\`bash
cp .env.example .env
make up
make migrate
make seed-tiny
\`\`\`

Then open http://localhost:3000 — you should see ~100 synthetic `tiny` complaints.

## Environment check (Day 1, §15)

_Filled in by Task 10._
```

- [ ] **Step 6: Commit**

```bash
git add .gitignore README.md Makefile .env.example
git commit -m "chore: scaffold repo, Makefile, env template"
```

---

### Task 2: Docker Compose stack (db + api + web)

**Files:**
- Create: `infra/docker-compose.yml`
- Create: `backend/Dockerfile`

**Interfaces:**
- Consumes: `.env` values from Task 1 (`POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_PORT`).
- Produces: a `db` service reachable at `localhost:${POSTGRES_PORT}` from the host and at `db:5432` from other containers; an `api` service built from `backend/Dockerfile`; a `web` service placeholder that Task 11 fills with a real Dockerfile-free `pnpm dev` mount (kept simple: bind-mount + `pnpm dev`, no production build on Day 1).

- [ ] **Step 1: Write `backend/Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir -e .

ENV PYTHONPATH=/app/src

CMD ["uvicorn", "backtrace.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

(`pyproject.toml` and `src/` are created in Task 3; this Dockerfile is inert until then, which is fine — Compose only builds it when `make up` runs, after Task 3.)

- [ ] **Step 2: Write `infra/docker-compose.yml`**

```yaml
services:
  db:
    image: timescale/timescaledb-ha:pg16
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    ports:
      - "${POSTGRES_PORT}:5432"
    volumes:
      - backtrace_db_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 5s
      timeout: 3s
      retries: 10

  api:
    build:
      context: ../backend
    depends_on:
      db:
        condition: service_healthy
    environment:
      DATABASE_URL_PIPELINE: postgresql+psycopg://bt_pipeline:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}
      AUTH_MODE: ${AUTH_MODE}
    ports:
      - "8000:8000"

  # worker: see §11 of the design doc — added in the Day 2 plan once app.jobs
  # exists and there is a real dequeue loop to run. Left out on Day 1 on purpose
  # (see "Scope decision" at the top of this plan).

  web:
    image: node:20-slim
    working_dir: /app
    volumes:
      - ../apps/web:/app
    command: sh -c "corepack enable && pnpm install && pnpm dev -- --hostname 0.0.0.0"
    environment:
      NEXT_PUBLIC_API_URL: http://localhost:8000
    ports:
      - "3000:3000"
    depends_on:
      - api

volumes:
  backtrace_db_data:
```

- [ ] **Step 3: Commit**

```bash
git add infra/docker-compose.yml backend/Dockerfile
git commit -m "chore: docker compose stack for db, api, web"
```

---

### Task 3: Backend package skeleton + health endpoint

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/src/backtrace/__init__.py`
- Create: `backend/src/backtrace/api/__init__.py`
- Create: `backend/src/backtrace/api/main.py`
- Create: `backend/tests/conftest.py`
- Test: `backend/tests/test_health.py`

**Interfaces:**
- Produces: `backtrace.api.main:app` (FastAPI instance), `GET /health` → `{"status": "ok"}`. Later tasks add routers/dependencies to this same `app`.

- [ ] **Step 1: Write `backend/pyproject.toml`**

```toml
[project]
name = "backtrace"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "pydantic>=2.8",
    "sqlalchemy>=2.0",
    "alembic>=1.13",
    "psycopg[binary]>=3.2",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "httpx>=0.27",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/backtrace", "src/backtrace_eval"]
```

- [ ] **Step 2: Create empty package files**

```bash
mkdir -p backend/src/backtrace/api backend/src/backtrace/db backend/src/backtrace/contracts
mkdir -p backend/src/backtrace_eval/generator
mkdir -p backend/tests
touch backend/src/backtrace/__init__.py \
      backend/src/backtrace/api/__init__.py \
      backend/src/backtrace/db/__init__.py \
      backend/src/backtrace/contracts/__init__.py \
      backend/src/backtrace_eval/__init__.py \
      backend/src/backtrace_eval/generator/__init__.py
```

- [ ] **Step 3: Write `backend/src/backtrace/api/main.py`**

```python
from fastapi import FastAPI

app = FastAPI(title="Backtrace API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 4: Install the package for local dev/tests**

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cd ..
```

- [ ] **Step 5: Write `backend/tests/conftest.py`**

```python
import pytest
from fastapi.testclient import TestClient

from backtrace.api.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
```

- [ ] **Step 6: Write the failing test**

```python
# backend/tests/test_health.py
def test_health_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 7: Run it to verify it passes** (it should pass immediately since Step 3 already wrote the endpoint — this confirms the package installs and imports cleanly)

Run: `cd backend && PYTHONPATH=src pytest tests/test_health.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/pyproject.toml backend/src backend/tests/conftest.py backend/tests/test_health.py
git commit -m "feat(backend): FastAPI skeleton with /health"
```

---

### Task 4: DB roles & Alembic migration for schemas/roles

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/versions/0001_schemas_and_roles.py`

**Interfaces:**
- Consumes: `DATABASE_URL` env var (owner/superuser connection, set by `make migrate`), `BT_PIPELINE_PASSWORD` / `BT_EVAL_PASSWORD` env vars (default to the dev Postgres password if unset — dev-only convenience, real secrets never committed).
- Produces: Postgres schemas `app`, `eval`; roles `bt_pipeline` (full DML on `app`, no access to `eval`) and `bt_eval` (full DML on both `app` and `eval`), matching §7.2's access rules. Later tasks' tables/grants build on this.

- [ ] **Step 1: Add Alembic to the venv and scaffold it**

```bash
cd backend
source .venv/bin/activate
alembic init alembic
```

- [ ] **Step 2: Edit `backend/alembic.ini`** — point `sqlalchemy.url` at the env var instead of a hardcoded value

Find the line `sqlalchemy.url = driver://user:pass@localhost/dbname` and delete it (the URL is supplied by `env.py` from the environment instead, so no DB credential is ever committed).

- [ ] **Step 3: Write `backend/alembic/env.py`**

```python
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])

target_metadata = None


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, literal_binds=True, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 4: Write `backend/alembic/versions/0001_schemas_and_roles.py`**

```python
"""schemas and roles

Revision ID: 0001
Revises:
Create Date: 2026-09-28
"""
import os

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _create_role_if_missing(role: str, password: str) -> None:
    op.execute(f"""
    DO $$
    BEGIN
      IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') THEN
        CREATE ROLE {role} LOGIN PASSWORD '{password}';
      END IF;
    END
    $$;
    """)


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS app;")
    op.execute("CREATE SCHEMA IF NOT EXISTS eval;")

    pipeline_password = os.environ.get("BT_PIPELINE_PASSWORD", "devpassword")
    eval_password = os.environ.get("BT_EVAL_PASSWORD", "devpassword")

    _create_role_if_missing("bt_pipeline", pipeline_password)
    _create_role_if_missing("bt_eval", eval_password)

    # bt_pipeline: app schema only (§7.2 — API + worker never touch eval)
    op.execute("GRANT USAGE ON SCHEMA app TO bt_pipeline;")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA app GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO bt_pipeline;")

    # bt_eval: both schemas (generator writes app.events/customers/complaints
    # and eval.gold_*; eval harness reads both) (§5.4, §7.2)
    op.execute("GRANT USAGE ON SCHEMA app TO bt_eval;")
    op.execute("GRANT USAGE ON SCHEMA eval TO bt_eval;")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA app GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO bt_eval;")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA eval GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO bt_eval;")


def downgrade() -> None:
    op.execute("DROP OWNED BY bt_pipeline;")
    op.execute("DROP OWNED BY bt_eval;")
    op.execute("DROP ROLE IF EXISTS bt_pipeline;")
    op.execute("DROP ROLE IF EXISTS bt_eval;")
    op.execute("DROP SCHEMA IF EXISTS eval CASCADE;")
    op.execute("DROP SCHEMA IF EXISTS app CASCADE;")
```

- [ ] **Step 5: Bring up the db and run the migration to verify it applies**

Run: `make up` (db only will be usable this early — `api`/`web` may fail to build until later tasks; that's fine, ignore those errors for this step), then `make migrate`
Expected: `bt_pipeline` and `bt_eval` roles exist; `app` and `eval` schemas exist. Verify:

```bash
docker exec -it $(docker ps -qf name=db) psql -U backtrace_owner -d backtrace -c "\dn" -c "\du"
```

Expected output includes `app`, `eval` schemas and `bt_pipeline`, `bt_eval` roles.

- [ ] **Step 6: Commit**

```bash
git add backend/alembic.ini backend/alembic
git commit -m "feat(db): app/eval schemas and role-separated grants"
```

---

### Task 5: Core SQLAlchemy models & tables migration

**Files:**
- Create: `backend/src/backtrace/db/session.py`
- Create: `backend/src/backtrace/db/models.py`
- Create: `backend/alembic/versions/0002_core_tables.py`
- Test: `backend/tests/test_models.py`

**Interfaces:**
- Consumes: `bt_pipeline`/`bt_eval` roles and `app` schema from Task 4.
- Produces: `Customer`, `Event`, `Complaint` ORM models (schema `app`) with columns matching the subset of §5.6/§7.1 needed for Day 1 display (remaining fields — `is_repeat`, `escalation_status`, embeddings, etc. — are added in the migrations that first need them, per YAGNI). `get_session(database_url)` context manager other tasks reuse.

- [ ] **Step 1: Write `backend/src/backtrace/db/session.py`**

```python
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


@contextmanager
def get_session(database_url: str) -> Iterator[Session]:
    engine = create_engine(database_url)
    with Session(engine) as session:
        yield session
    engine.dispose()
```

- [ ] **Step 2: Write `backend/src/backtrace/db/models.py`**

```python
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
```

- [ ] **Step 3: Write `backend/alembic/versions/0002_core_tables.py`**

```python
"""core tables: customers, events, complaints

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-28
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("region", sa.String, nullable=False),
        sa.Column("plan", sa.String, nullable=False),
        sa.Column("segment", sa.String, nullable=False),
        sa.Column("node_id", sa.String, nullable=False),
        schema="app",
    )

    op.create_table(
        "events",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("source", sa.String, nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scope", sa.JSON, nullable=False),
        sa.Column("search_text", sa.String, nullable=False),
        schema="app",
    )

    op.create_table(
        "complaints",
        sa.Column("complaint_id", sa.String, primary_key=True),
        sa.Column("customer_id", sa.String, sa.ForeignKey("app.customers.id"), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("channel", sa.String, nullable=False),
        sa.Column("text", sa.String, nullable=False),
        sa.Column("product", sa.String, nullable=False),
        sa.Column("region", sa.String, nullable=False),
        sa.Column("node_id", sa.String, nullable=False),
        schema="app",
    )
    op.create_index("ix_app_complaints_received_at", "complaints", ["received_at"], schema="app")


def downgrade() -> None:
    op.drop_table("complaints", schema="app")
    op.drop_table("events", schema="app")
    op.drop_table("customers", schema="app")
```

- [ ] **Step 4: Write the test**

```python
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
```

- [ ] **Step 5: Run the migration and the test**

Run: `make migrate` then `cd backend && PYTHONPATH=src DATABASE_URL_PIPELINE=$DATABASE_URL_PIPELINE pytest tests/test_models.py -v`
Expected: PASS (requires `db` container up and `.env` sourced — `set -a; source ../.env; set +a` if running outside `make`)

- [ ] **Step 6: Commit**

```bash
git add backend/src/backtrace/db backend/alembic/versions/0002_core_tables.py backend/tests/test_models.py
git commit -m "feat(db): customers, events, complaints tables"
```

---

### Task 6: Pydantic contracts (extraction, API DTOs, evidence)

**Files:**
- Create: `backend/src/backtrace/contracts/extraction.py`
- Create: `backend/src/backtrace/contracts/complaints.py`
- Create: `backend/src/backtrace/contracts/evidence.py`
- Test: `backend/tests/test_contracts.py`

**Interfaces:**
- Produces: `ComplaintExtraction` (used by the Day 2 extraction stage, §8.2 step 2), `ComplaintOut` (the API DTO the `/complaints` endpoint in Task 7 returns), `EvidencePackStub` (placeholder shape for the Day 3 hypothesis evidence pack, §8.2 step 8 — kept minimal, no logic, just the contract so `contracts/` matches the Day 1 scope item in §19).

- [ ] **Step 1: Write `backend/src/backtrace/contracts/extraction.py`**

```python
from pydantic import BaseModel


class ComplaintExtraction(BaseModel):
    """Schema-bound output of Gemini structured extraction (§8.2 step 2)."""

    product: str
    symptoms: list[str]
    claimed_cause: str
    issue_start_mentioned: str | None = None
    amounts: list[str] = []
    issues: list[str]
    vulnerability_signals: list[str] = []
    requested_outcome: str | None = None
    identifiers: list[str] = []
```

- [ ] **Step 2: Write `backend/src/backtrace/contracts/complaints.py`**

```python
import datetime as dt

from pydantic import BaseModel


class ComplaintOut(BaseModel):
    complaint_id: str
    customer_id: str
    received_at: dt.datetime
    channel: str
    text: str
    product: str
    region: str

    model_config = {"from_attributes": True}
```

- [ ] **Step 3: Write `backend/src/backtrace/contracts/evidence.py`**

```python
from pydantic import BaseModel


class EvidencePackStub(BaseModel):
    """Placeholder shape for the hypothesis evidence pack (§8.2 step 8).

    Filled in with real linking-score components once evidence linking
    (§8.3) exists — Day 3 work. Kept here now only so the contracts
    package matches the Day 1 scope item in §19.
    """

    cohort_id: str
    complaint_ids: list[str]
    event_ids: list[str]
    anomaly_ids: list[str]
```

- [ ] **Step 4: Write the test**

```python
# backend/tests/test_contracts.py
from backtrace.contracts.complaints import ComplaintOut
from backtrace.contracts.evidence import EvidencePackStub
from backtrace.contracts.extraction import ComplaintExtraction


def test_complaint_extraction_requires_issues_field():
    extraction = ComplaintExtraction(
        product="fiber_basic",
        symptoms=["no internet"],
        claimed_cause="router broken",
        issues=["no internet"],
    )
    assert extraction.issues == ["no internet"]


def test_complaint_out_serializes_from_orm_style_object():
    import datetime as dt

    class FakeRow:
        complaint_id = "c1"
        customer_id = "cust1"
        received_at = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
        channel = "web"
        text = "down"
        product = "fiber_basic"
        region = "north"

    dto = ComplaintOut.model_validate(FakeRow())
    assert dto.complaint_id == "c1"


def test_evidence_pack_stub_round_trips_json():
    pack = EvidencePackStub(cohort_id="coh1", complaint_ids=["c1"], event_ids=["e1"], anomaly_ids=[])
    assert EvidencePackStub.model_validate_json(pack.model_dump_json()) == pack
```

- [ ] **Step 5: Run the tests**

Run: `cd backend && PYTHONPATH=src pytest tests/test_contracts.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/src/backtrace/contracts backend/tests/test_contracts.py
git commit -m "feat(contracts): extraction, complaint DTO, evidence pack stub"
```

---

### Task 7: `GET /complaints` API endpoint

**Files:**
- Modify: `backend/src/backtrace/api/main.py`
- Test: `backend/tests/test_complaints_api.py`

**Interfaces:**
- Consumes: `Complaint` model (Task 5), `ComplaintOut` DTO (Task 6), `DATABASE_URL_PIPELINE` env var.
- Produces: `GET /complaints?limit=&offset=` → `list[ComplaintOut]`, ordered by `received_at`. This is the endpoint Task 11's web page calls.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_complaints_api.py
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && PYTHONPATH=src pytest tests/test_complaints_api.py -v`
Expected: FAIL with `404 Not Found` (no `/complaints` route yet)

- [ ] **Step 3: Implement the endpoint**

```python
# backend/src/backtrace/api/main.py
import os

from fastapi import FastAPI
from sqlalchemy import select

from backtrace.contracts.complaints import ComplaintOut
from backtrace.db.models import Complaint
from backtrace.db.session import get_session

app = FastAPI(title="Backtrace API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/complaints")
def list_complaints(limit: int = 100, offset: int = 0) -> list[ComplaintOut]:
    database_url = os.environ["DATABASE_URL_PIPELINE"]
    with get_session(database_url) as session:
        rows = session.execute(
            select(Complaint).order_by(Complaint.received_at).limit(limit).offset(offset)
        ).scalars().all()
        return [ComplaintOut.model_validate(row) for row in rows]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && PYTHONPATH=src pytest tests/test_complaints_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/backtrace/api/main.py backend/tests/test_complaints_api.py
git commit -m "feat(api): GET /complaints"
```

---

### Task 8: Tiny-world generator (`backtrace_eval`)

**Files:**
- Create: `configs/worlds/tiny.yaml`
- Create: `backend/src/backtrace_eval/generator/tiny.py`
- Create: `backend/src/backtrace_eval/generator/cli.py`
- Test: `backend/tests/test_generator_tiny.py`

**Interfaces:**
- Consumes: `configs/worlds/tiny.yaml` (seed, counts, regions).
- Produces: `generate_tiny_world(config) -> TinyWorld` (pure, deterministic, no I/O, no network — matches §5.1's "must load in seconds" and the no-LLM-in-CI constraint). `TinyWorld` has `.customers`, `.events`, `.complaints` lists of plain dicts, JSON-serializable. `cli.py generate` writes those to `fixtures/tiny/*.json` (consumed by Task 9's loader).

- [ ] **Step 1: Write `configs/worlds/tiny.yaml`**

```yaml
seed: 42
num_customers: 100
num_events: 3
num_complaints: 100
regions: [north, south, east, west]
plans: [fiber_basic, fiber_pro, business_ethernet, tv_bundle]
channels: [phone, email, chat, web]
event_sources: [network_alarm, billing_run, deploy, policy_change]
window_days: 14
```

- [ ] **Step 2: Write the failing test**

```python
# backend/tests/test_generator_tiny.py
from backtrace_eval.generator.tiny import TinyWorldConfig, generate_tiny_world


def test_generate_tiny_world_is_deterministic_and_sized():
    config = TinyWorldConfig(
        seed=42,
        num_customers=100,
        num_events=3,
        num_complaints=100,
        regions=["north", "south", "east", "west"],
        plans=["fiber_basic", "fiber_pro", "business_ethernet", "tv_bundle"],
        channels=["phone", "email", "chat", "web"],
        event_sources=["network_alarm", "billing_run", "deploy", "policy_change"],
        window_days=14,
    )

    world_a = generate_tiny_world(config)
    world_b = generate_tiny_world(config)

    assert len(world_a.customers) == 100
    assert len(world_a.events) == 3
    assert len(world_a.complaints) == 100
    assert world_a.customers == world_b.customers  # same seed → same output
    assert all(c["customer_id"] in {cust["id"] for cust in world_a.customers} for c in world_a.complaints)
```

- [ ] **Step 3: Run it to verify it fails**

Run: `cd backend && PYTHONPATH=src pytest tests/test_generator_tiny.py -v`
Expected: FAIL with `ModuleNotFoundError` or `ImportError`

- [ ] **Step 4: Write `backend/src/backtrace_eval/generator/tiny.py`**

```python
import datetime as dt
import random
from dataclasses import dataclass, field


@dataclass
class TinyWorldConfig:
    seed: int
    num_customers: int
    num_events: int
    num_complaints: int
    regions: list[str]
    plans: list[str]
    channels: list[str]
    event_sources: list[str]
    window_days: int


@dataclass
class TinyWorld:
    customers: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    complaints: list[dict] = field(default_factory=list)


_SEGMENT_BY_PLAN = {
    "fiber_basic": "residential",
    "fiber_pro": "residential",
    "tv_bundle": "residential",
    "business_ethernet": "business",
}

_TEXT_TEMPLATES = [
    "My {product} has been having issues since {day}.",
    "I'm writing about a problem with my {product} account.",
    "This is my second time reporting a {product} issue.",
    "Something is wrong with my {product} service in {region}.",
]


def generate_tiny_world(config: TinyWorldConfig) -> TinyWorld:
    rng = random.Random(config.seed)
    world_start = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)

    customers = []
    for i in range(config.num_customers):
        region = rng.choice(config.regions)
        plan = rng.choice(config.plans)
        customers.append(
            {
                "id": f"cust_{i:04d}",
                "region": region,
                "plan": plan,
                "segment": _SEGMENT_BY_PLAN[plan],
                "node_id": f"node-{region}-{rng.randint(1, 5)}",
            }
        )

    events = []
    for i in range(config.num_events):
        start_offset = rng.randint(0, config.window_days - 1)
        start_at = world_start + dt.timedelta(days=start_offset, hours=rng.randint(0, 23))
        end_at = start_at + dt.timedelta(hours=rng.randint(1, 12))
        region = rng.choice(config.regions)
        source = rng.choice(config.event_sources)
        events.append(
            {
                "id": f"event_{i:03d}",
                "source": source,
                "start_at": start_at.isoformat(),
                "end_at": end_at.isoformat(),
                "scope": {"region": region},
                "search_text": f"{source} affecting {region}",
            }
        )

    complaints = []
    for i in range(config.num_complaints):
        customer = rng.choice(customers)
        day_offset = rng.randint(0, config.window_days - 1)
        received_at = world_start + dt.timedelta(days=day_offset, hours=rng.randint(0, 23), minutes=rng.randint(0, 59))
        template = rng.choice(_TEXT_TEMPLATES)
        complaints.append(
            {
                "complaint_id": f"complaint_{i:04d}",
                "customer_id": customer["id"],
                "received_at": received_at.isoformat(),
                "channel": rng.choice(config.channels),
                "text": template.format(product=customer["plan"], region=customer["region"], day=received_at.date()),
                "product": customer["plan"],
                "region": customer["region"],
                "node_id": customer["node_id"],
            }
        )

    return TinyWorld(customers=customers, events=events, complaints=complaints)
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd backend && PYTHONPATH=src pytest tests/test_generator_tiny.py -v`
Expected: PASS

- [ ] **Step 6: Write `backend/src/backtrace_eval/generator/cli.py`**

```python
import argparse
import json
from pathlib import Path

import yaml

from backtrace_eval.generator.tiny import TinyWorldConfig, generate_tiny_world


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["generate"])
    parser.add_argument("--world-config", default="../configs/worlds/tiny.yaml")
    parser.add_argument("--out", default="../fixtures/tiny")
    args = parser.parse_args()

    with open(args.world_config) as f:
        raw = yaml.safe_load(f)
    config = TinyWorldConfig(**raw)
    world = generate_tiny_world(config)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "customers.json").write_text(json.dumps(world.customers, indent=2))
    (out_dir / "events.json").write_text(json.dumps(world.events, indent=2))
    (out_dir / "complaints.json").write_text(json.dumps(world.complaints, indent=2))
    print(f"Wrote {len(world.customers)} customers, {len(world.events)} events, {len(world.complaints)} complaints to {out_dir}")


if __name__ == "__main__":
    main()
```

Add `pyyaml` to `backend/pyproject.toml` dependencies: `"pyyaml>=6.0",`.

- [ ] **Step 7: Generate and commit the fixture**

```bash
cd backend
source .venv/bin/activate
pip install -e ".[dev]"
PYTHONPATH=src python -m backtrace_eval.generator.cli generate --world-config ../configs/worlds/tiny.yaml --out ../fixtures/tiny
cd ..
git add configs/worlds/tiny.yaml backend/src/backtrace_eval/generator/tiny.py backend/src/backtrace_eval/generator/cli.py backend/tests/test_generator_tiny.py fixtures/tiny backend/pyproject.toml
git commit -m "feat(generator): deterministic tiny-world generator + committed fixture"
```

---

### Task 9: Fixture loader, `make seed-tiny`, and the import-rule test

**Files:**
- Create: `backend/src/backtrace_eval/generator/load.py`
- Create: `backend/tests/test_import_rules.py`

**Interfaces:**
- Consumes: `fixtures/tiny/*.json` (Task 8), `Customer`/`Event`/`Complaint` models (Task 5), `DATABASE_URL_EVAL`.
- Produces: `make seed-tiny` populates `app.customers`, `app.events`, `app.complaints` via the `bt_eval` role. A CI-enforceable test asserting `backtrace` never imports `backtrace_eval` (§6.1 principle 5, §5.8).

- [ ] **Step 1: Write `backend/src/backtrace_eval/generator/load.py`**

```python
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
```

Note: this file imports from `backtrace.db` — that direction is fine. The forbidden direction is `backtrace` importing `backtrace_eval`, which Step 2 enforces.

- [ ] **Step 2: Write the import-rule test**

```python
# backend/tests/test_import_rules.py
import ast
from pathlib import Path

BACKTRACE_SRC = Path(__file__).parent.parent / "src" / "backtrace"


def test_backtrace_never_imports_backtrace_eval():
    offending: list[str] = []
    for path in BACKTRACE_SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            if any(name.startswith("backtrace_eval") for name in names):
                offending.append(str(path))
    assert not offending, f"backtrace must not import backtrace_eval, found in: {offending}"
```

- [ ] **Step 3: Run both**

Run: `cd backend && PYTHONPATH=src pytest tests/test_import_rules.py -v`
Expected: PASS

Run (with `db` up and `.env` sourced): `make seed-tiny`
Expected: prints `Loaded 100 customers, 3 events, 100 complaints`

- [ ] **Step 4: Verify via the API**

Run: `curl -s http://localhost:8000/complaints | python3 -m json.tool | head -20` (requires `make up` with Task 3/7's `api` service built)
Expected: a JSON array of complaint objects

- [ ] **Step 5: Commit**

```bash
git add backend/src/backtrace_eval/generator/load.py backend/tests/test_import_rules.py
git commit -m "feat(generator): fixture loader (bt_eval role) + import-rule test"
```

---

### Task 10: Extension check script + README recording

**Files:**
- Create: `backend/src/backtrace/db/check_extensions.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `DATABASE_URL_OWNER`.
- Produces: a script printing which of `timescaledb`, `vector` (pgvector), `vectorscale` (pgvectorscale), and `pg_textsearch` are installed/available on the running `db` container; a filled-in README section recording the result, per §15's Day 1 check.

- [ ] **Step 1: Write `backend/src/backtrace/db/check_extensions.py`**

```python
import argparse

from sqlalchemy import create_engine, text

CHECKED_EXTENSIONS = ["timescaledb", "vector", "vectorscale", "pg_textsearch"]


def check_extensions(database_url: str) -> dict[str, bool]:
    engine = create_engine(database_url)
    results: dict[str, bool] = {}
    with engine.connect() as conn:
        available = {
            row[0]
            for row in conn.execute(text("SELECT name FROM pg_available_extensions"))
        }
        installed = {
            row[0] for row in conn.execute(text("SELECT extname FROM pg_extension"))
        }
        for ext in CHECKED_EXTENSIONS:
            results[ext] = ext in available or ext in installed
    engine.dispose()
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    args = parser.parse_args()
    results = check_extensions(args.database_url)
    for ext, available in results.items():
        print(f"{ext}: {'available' if available else 'NOT available'}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it against the local Docker image**

Run: `make check-extensions`
Expected output (record the *actual* output — this is a real check, not a guess):

```
timescaledb: available
vector: available
vectorscale: available
pg_textsearch: NOT available
```

- [ ] **Step 3: Update `README.md`** with the real result from Step 2

```markdown
## Environment check (Day 1, §15)

Checked against `timescale/timescaledb-ha:pg16` (local Docker image), 2026-09-28:

| Extension | Available |
| --- | --- |
| timescaledb | yes |
| pgvector | yes |
| pgvectorscale | yes |
| pg_textsearch | no — falls back to Postgres built-in `tsvector` + `ts_rank` behind `retrieval.lexical_search()` (§9.2) |

Re-run: `make check-extensions`. Re-check against the managed TigerData instance once
provisioned and update this table — differences are handled by the `tsvector` fallback,
not by separate code paths (§15).
```

(If Step 2's actual output differs — e.g. `vectorscale` turns out unavailable too — write the real numbers here, not these example ones.)

- [ ] **Step 4: Commit**

```bash
git add backend/src/backtrace/db/check_extensions.py README.md
git commit -m "feat(db): extension availability check, recorded in README"
```

---

### Task 11: Next.js web skeleton listing tiny complaints

**Files:**
- Create: `apps/web/` (scaffolded via `create-next-app`)
- Modify: `apps/web/src/app/page.tsx`
- Create: `apps/web/src/lib/api.ts`

**Interfaces:**
- Consumes: `GET /complaints` (Task 7) via `NEXT_PUBLIC_API_URL`.
- Produces: a page at `/` rendering the list of complaints — the visible proof of demo step 1 (§2) at skeleton scale.

- [ ] **Step 1: Scaffold the app**

```bash
mkdir -p apps
cd apps
pnpm create next-app@latest web --typescript --tailwind --app --no-src-dir=false --import-alias "@/*" --eslint --use-pnpm
cd web
pnpm dlx shadcn@latest init -d
pnpm dlx shadcn@latest add table
cd ../..
```

- [ ] **Step 2: Write `apps/web/src/lib/api.ts`**

```typescript
export type Complaint = {
  complaint_id: string;
  customer_id: string;
  received_at: string;
  channel: string;
  text: string;
  product: string;
  region: string;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function fetchComplaints(): Promise<Complaint[]> {
  const res = await fetch(`${API_URL}/complaints`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Failed to fetch complaints: ${res.status}`);
  }
  return res.json();
}
```

- [ ] **Step 3: Write `apps/web/src/app/page.tsx`**

```tsx
import { fetchComplaints } from "@/lib/api";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export default async function Home() {
  const complaints = await fetchComplaints();

  return (
    <main className="p-8">
      <h1 className="text-2xl font-semibold mb-4">
        Backtrace — {complaints.length} complaints (tiny)
      </h1>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Received</TableHead>
            <TableHead>Channel</TableHead>
            <TableHead>Product</TableHead>
            <TableHead>Region</TableHead>
            <TableHead>Text</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {complaints.map((c) => (
            <TableRow key={c.complaint_id}>
              <TableCell>{new Date(c.received_at).toLocaleString()}</TableCell>
              <TableCell>{c.channel}</TableCell>
              <TableCell>{c.product}</TableCell>
              <TableCell>{c.region}</TableCell>
              <TableCell>{c.text}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </main>
  );
}
```

- [ ] **Step 4: Run it and verify manually**

Run: `make up` (rebuilds `api` and starts `web`), then wait for `db`/`api` healthy, then `make migrate && make seed-tiny`

Open `http://localhost:3000` in a browser.
Expected: a table listing 100 rows of synthetic complaint data.

- [ ] **Step 5: Commit**

```bash
git add apps/web
git commit -m "feat(web): Next.js skeleton listing tiny complaints"
```

---

### Task 12: End-to-end verification & README done-criteria checklist

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: everything above.
- Produces: a verified, from-scratch run of the Day 1 done-criteria (§19: "`make up && make migrate && make seed-tiny` works; web lists `tiny` complaints via the API; extension check recorded in README"), and a checklist in the README so the next session can confirm state quickly without re-deriving it.

- [ ] **Step 1: Tear down and rebuild from scratch to catch any hidden local state**

```bash
make down
docker volume rm hacktheHill_backtrace_db_data 2>/dev/null || true
make up
```

Wait for `db` healthy (`docker compose -f infra/docker-compose.yml ps`).

- [ ] **Step 2: Run the full sequence**

```bash
make migrate
make seed-tiny
make check-extensions
```

Expected: no errors; extension output matches what's recorded in README (Task 10).

- [ ] **Step 3: Run the full backend test suite**

Run: `make test-backend`
Expected: all tests pass (`test_health`, `test_models`, `test_contracts`, `test_complaints_api`, `test_generator_tiny`, `test_import_rules`)

- [ ] **Step 4: Verify the web app in a browser**

Open `http://localhost:3000`.
Expected: table with 100 complaint rows, matching `fixtures/tiny/complaints.json` count.

- [ ] **Step 5: Add the Day 1 checklist to `README.md`**

```markdown
## Day 1 status

- [x] `make up && make migrate && make seed-tiny` runs clean from a fresh volume
- [x] `GET /complaints` returns the seeded tiny dataset
- [x] Web app at http://localhost:3000 lists them
- [x] Extension check recorded above
- [x] `backtrace` → `backtrace_eval` import rule enforced by `test_import_rules.py`
```

- [ ] **Step 6: Commit**

```bash
git add README.md
git commit -m "chore: verify Day 1 skeleton end-to-end"
```

---

## Self-Review

**Spec coverage** — every Day 1 bullet from §19 has a task: monorepo (Task 1), Docker Compose (Task 2), DB + extensions (Task 4, Task 10), Alembic migrations for `app`/`eval` schemas + roles (Task 4), FastAPI + Next.js skeleton (Task 3, Task 11), Pydantic contracts — extraction/API DTOs/evidence (Task 6), `tiny` dataset (Task 8–9). Done-criteria — `make up && make migrate && make seed-tiny` works (Task 12), web lists `tiny` complaints via the API (Task 11–12), extension check recorded in README (Task 10) — are each independently verified in Task 12.

**Placeholder scan** — no task defers its own code; the one intentionally-deferred item (the `worker` service) is called out explicitly in the "Scope decision" section with its own reasoning and a pointer to where it resumes, not left as a silent TODO.

**Type consistency** — `Customer`/`Event`/`Complaint` field names match across `models.py` (Task 5), the Alembic migration (Task 5), the generator's dict shape (Task 8), the loader (Task 9), and `ComplaintOut` (Task 6/7). `TinyWorldConfig` fields match `configs/worlds/tiny.yaml` keys exactly (Task 8).

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-09-28-day1-skeleton.md`. Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
