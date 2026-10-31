include .env
export

.PHONY: up down migrate seed-tiny generate-dev seed-dev check-extensions test-backend worker enqueue-run job-status generate-held-out seed-held-out eval

HELD_OUT_SEED := 20261029
# Hashed into the default run ID so editing held-out.yaml (new seed, sizes,
# causes, ...) can't silently reuse another config's cached extractions/
# embeddings, which are keyed by (run_id, complaint_id) only.
HELD_OUT_CONFIG_HASH := $(shell shasum -a 256 configs/worlds/held-out.yaml | cut -c1-8)
EVAL_RUN_ID := $(or $(RUN_ID),held-out-eval-$(HELD_OUT_CONFIG_HASH))

up:
	docker compose -f infra/docker-compose.yml up -d --build

down:
	docker compose -f infra/docker-compose.yml down

migrate:
	cd backend && DATABASE_URL=$(DATABASE_URL_OWNER) BT_PIPELINE_PASSWORD=$(POSTGRES_PASSWORD) BT_EVAL_PASSWORD=$(POSTGRES_PASSWORD) .venv/bin/alembic upgrade head

seed-tiny:
	cd backend && PYTHONPATH=src .venv/bin/python -m backtrace_eval.generator.load --fixture ../fixtures/tiny --database-url $(DATABASE_URL_EVAL)

generate-dev:
	cd backend && PYTHONPATH=src .venv/bin/python -m backtrace_eval.generator.cli generate --world-config ../configs/worlds/dev.yaml --out ../fixtures/dev

seed-dev: generate-dev
	cd backend && PYTHONPATH=src .venv/bin/python -m backtrace_eval.generator.load --fixture ../fixtures/dev --database-url $(DATABASE_URL_EVAL)

generate-held-out:
	cd backend && PYTHONPATH=src .venv/bin/python -m backtrace_eval.generator.cli generate --world-config ../configs/worlds/held-out.yaml --out ../fixtures/held-out

seed-held-out: generate-held-out
	cd backend && PYTHONPATH=src .venv/bin/python -m backtrace_eval.generator.load --fixture ../fixtures/held-out --database-url $(DATABASE_URL_EVAL)

check-extensions:
	cd backend && PYTHONPATH=src .venv/bin/python -m backtrace.db.check_extensions --database-url $(DATABASE_URL_OWNER)

test-backend:
	cd backend && PYTHONPATH=src .venv/bin/python -m pytest -q

worker:
	cd backend && PYTHONPATH=src .venv/bin/python -m backtrace.worker.main

# make enqueue-run [RUN_ID=...] [PROFILE=dev]
enqueue-run:
	cd backend && PYTHONPATH=src .venv/bin/python -m backtrace.pipeline.run_cli enqueue $(if $(RUN_ID),--run-id $(RUN_ID)) --dataset-profile $(or $(PROFILE),dev)

# make job-status RUN_ID=...
job-status:
	cd backend && PYTHONPATH=src .venv/bin/python -m backtrace.pipeline.run_cli status --run-id $(RUN_ID)

# make eval [RUN_ID=...] — seeds the held-out world, runs the full pipeline
# on it, waits for the worker (started by `make up`) to finish, then writes
# the ablation report. One command, held-out split only (§13.3, issue #43).
eval: seed-held-out
	cd backend && PYTHONPATH=src .venv/bin/python -m backtrace.pipeline.run_cli enqueue --run-id $(EVAL_RUN_ID) --dataset-profile held-out --dataset-seed $(HELD_OUT_SEED)
	cd backend && PYTHONPATH=src .venv/bin/python -m backtrace.pipeline.run_cli wait --run-id $(EVAL_RUN_ID)
	cd backend && PYTHONPATH=src .venv/bin/python -m backtrace_eval.ablation --run-id $(EVAL_RUN_ID) --out ../docs/eval/held-out-report.md
	cat docs/eval/held-out-report.md
