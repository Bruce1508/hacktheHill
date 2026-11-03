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

```sh
cd infra
docker compose up -d --build
```

Run migrations + seed the dev world once the `db` service is healthy (same commands as local, just prefixed to run inside the `api` container or via the host-side `DATABASE_URL_*` vars pointed at the box):

```sh
docker compose exec api alembic upgrade head
# then seed-dev equivalent — see Makefile's `seed-dev` target for the exact command
```

## 5. Open firewall ports

In the Vultr dashboard's firewall settings (or `ufw` on the box), allow inbound `3000` (web) and `8000` (api) from anywhere, plus `22` for SSH.

## 6. Verify

Open `http://<IP>:3000` and walk the 10-step demo against the deployed build — this is the acceptance criteria for #28, not a localhost run.

## Notes

- `infra/docker-compose.yml`'s `web` service runs `pnpm dev`, not a production build — intentional for speed; a real prod build is unnecessary scope for a hackathon demo window.
- `fixtures/held-out/` and `docs/eval/` are gitignored — if the deployed demo needs held-out eval artifacts, regenerate them on the box via `make seed-held-out` rather than copying local files over.
