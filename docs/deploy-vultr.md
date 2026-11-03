# Deploying to Vultr (#28)

Reuses `infra/docker-compose.yml` as-is — no new Dockerfiles needed. Dev auth stays on (Auth0 is out of scope per the Day 6 decision); this gets the 10-step demo running on a public URL instead of localhost.

## 1. Provision the instance

In the Vultr dashboard: Deploy New Server → Cloud Compute → Ubuntu 22.04 LTS, smallest size that has ≥2GB RAM (clustering + the Node dev server need headroom). Note the public IP.

## 2. Install Docker on the box

SSH in (`ssh root@<IP>`), then:

```sh
curl -fsSL https://get.docker.com | sh
apt-get install -y docker-compose-plugin git
```

## 3. Get the code and config onto the box

```sh
git clone https://github.com/Bruce1508/hacktheHill.git
cd hacktheHill
cp .env.example .env
```

Edit `.env`:
- `GEMINI_API_KEY` — your real key (never commit this)
- `POSTGRES_PASSWORD` — change from `devpassword` to something real
- Leave `AUTH_MODE=dev` (Auth0 is explicitly out of scope for this ship)

## 4. Bring it up

Run from the repo root (not `infra/`), with `--env-file .env` explicit — this compose version doesn't auto-discover `.env` from the CWD the way older versions did, and silently defaults every var to blank (the `db` container then fails to start with "superuser password is not specified"):

```sh
docker compose --env-file .env -f infra/docker-compose.yml up -d --build
```

`backend/Dockerfile` only `COPY`s `src/`, not the `alembic/` directory — migrations can't run inside the `api` container. Run them from a host-side venv instead, pointed at the DB's exposed port (`POSTGRES_PORT` in `.env`, default 5433):

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
cd backend && ~/.local/bin/uv sync --frozen
cd .. && source .env && cd backend
DATABASE_URL=$DATABASE_URL_OWNER BT_PIPELINE_PASSWORD=$POSTGRES_PASSWORD BT_EVAL_PASSWORD=$POSTGRES_PASSWORD .venv/bin/alembic upgrade head
cd ..
```

Then seed the dev world the same way:

```sh
PYTHONPATH=backend/src backend/.venv/bin/python -m backtrace_eval.generator.cli generate --world-config configs/worlds/dev.yaml --out fixtures/dev
PYTHONPATH=backend/src backend/.venv/bin/python -m backtrace_eval.generator.load --fixture fixtures/dev --database-url $DATABASE_URL_EVAL
```

## 5. Open firewall ports

`ufw` is active by default on a fresh Vultr Ubuntu image, allowing only `22`:

```sh
ufw allow 3000/tcp
ufw allow 8000/tcp
ufw reload
```

## 6. Verify

```sh
curl -o /dev/null -w "%{http_code}\n" http://<IP>:8000/health
curl -o /dev/null -w "%{http_code}\n" http://<IP>:3000
```

Then open `http://<IP>:3000` in a browser and walk the 10-step demo against the deployed build — this is the acceptance criteria for #28, not a localhost run.

## Notes

- `infra/docker-compose.yml`'s `web` service runs `pnpm dev`, not a production build — intentional for speed; a real prod build is unnecessary scope for a hackathon demo window.
- `fixtures/held-out/` and `docs/eval/` are gitignored — if the deployed demo needs held-out eval artifacts, regenerate them on the box via `make seed-held-out` rather than copying local files over.
