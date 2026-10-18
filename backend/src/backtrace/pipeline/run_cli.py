"""CLI to enqueue a pipeline run and inspect job status (§Phase 4 Makefile
targets: enqueue a run, inspect run/job status, rerun the same input)."""

import argparse
import datetime as dt
import os
import uuid

from sqlalchemy import select

from backtrace.db import jobs
from backtrace.db.models import Job, PipelineRun
from backtrace.db.session import get_session


def enqueue_run(database_url: str, run_id: str | None, dataset_profile: str, dataset_seed: int) -> str:
    run_id = run_id or f"run-{uuid.uuid4().hex[:12]}"
    with get_session(database_url) as session:
        session.merge(
            PipelineRun(
                run_id=run_id,
                dataset_profile=dataset_profile,
                dataset_seed=dataset_seed,
                config={},
                started_at=dt.datetime.now(dt.timezone.utc),
            )
        )
        session.commit()
        jobs.enqueue(session, run_id, "pipeline.run", {})
    return run_id


def print_status(database_url: str, run_id: str) -> None:
    with get_session(database_url) as session:
        rows = session.execute(select(Job).where(Job.run_id == run_id).order_by(Job.id)).scalars().all()
        if not rows:
            print(f"no jobs found for run_id={run_id}")
        for row in rows:
            print(f"job={row.id} type={row.type} stage={row.stage} status={row.status} attempts={row.attempts} error={row.error}")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    enqueue_p = sub.add_parser("enqueue")
    enqueue_p.add_argument("--run-id")
    enqueue_p.add_argument("--dataset-profile", default="dev")
    # matches configs/worlds/dev.yaml's seed; a second run over the same
    # profile+seed is "rerun the same input" for the Phase 6 zero-token check.
    enqueue_p.add_argument("--dataset-seed", type=int, default=20260928)

    status_p = sub.add_parser("status")
    status_p.add_argument("--run-id", required=True)

    args = parser.parse_args()
    database_url = os.environ["DATABASE_URL_PIPELINE"]
    if args.command == "enqueue":
        run_id = enqueue_run(database_url, args.run_id, args.dataset_profile, args.dataset_seed)
        print(f"enqueued pipeline.run for run_id={run_id}")
    elif args.command == "status":
        print_status(database_url, args.run_id)


if __name__ == "__main__":
    main()
