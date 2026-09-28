# Backtrace

Root-cause engine for customer complaints. See `Backtrace — Technical Design Doc.md`
for the full design; this README tracks what actually runs.

## Quickstart

Requires Python >=3.12 (built and tested against 3.13; 3.12 works too).

```bash
cd backend && python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]" && cd ..
cp .env.example .env
make up
make migrate
make seed-tiny
```

Then open http://localhost:3000 — you should see ~100 synthetic `tiny` complaints.

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

## Day 1 status

- [x] `make up && make migrate && make seed-tiny` runs clean from a fresh volume
- [x] `GET /complaints` returns the seeded tiny dataset
- [x] Web app at http://localhost:3000 lists them
- [x] Extension check recorded above
- [x] `backtrace` → `backtrace_eval` import rule enforced by `test_import_rules.py`
