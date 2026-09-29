include .env
export

.PHONY: up down migrate seed-tiny generate-dev seed-dev check-extensions test-backend

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

check-extensions:
	cd backend && PYTHONPATH=src .venv/bin/python -m backtrace.db.check_extensions --database-url $(DATABASE_URL_OWNER)

test-backend:
	cd backend && PYTHONPATH=src .venv/bin/python -m pytest -q
