# Backtrace

Root-cause engine for customer complaints. See `Backtrace — Technical Design Doc.md`
for the full design; this README tracks what actually runs.

## Quickstart

```bash
cp .env.example .env
make up
make migrate
make seed-tiny
```

Then open http://localhost:3000 — you should see ~100 synthetic `tiny` complaints.

## Environment check (Day 1, §15)

_Filled in by Task 10._
