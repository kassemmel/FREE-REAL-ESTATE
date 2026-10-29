# BleepBloopBot

A demo AI chat app for showing off **Prisma AIRS** prompt/response scanning. A small
Flask backend fans chats out to multiple LLM routes and scans every prompt and reply
with Prisma AIRS; a static `index.html` is the UI.

**LLM routes** (pick per-chat in the UI, all scanned by AIRS):
- `ollama` — local models via the bundled Ollama container
- `azure/*` — Azure AI Foundry / Azure OpenAI deployments
- `AIGW/*` — models through the Portkey AI gateway

## Repo layout

| Path | What |
|---|---|
| `backend/` | Flask/gunicorn app (`app.py`) — the single source of truth for both deployments |
| `index.html`, `images/` | the UI, shared by both deployments |
| `compose.base.yml` | shared services (`ollama` + `backend`); pulled in via `include:` |
| `docker-compose.yml` | **Caddy-host** edge (default stack) — web :3131, plus n8n + stocks-mcp |
| `docker-compose.azure.yml` | **Azure public-VM** edge — nginx TLS (certbot), IP allowlist |
| `nginx.conf` | Caddy-host nginx (plain :80 → backend) |
| `azure/` | Azure edge nginx, TLS, and ARM/IaC — see [`azure/README.md`](azure/README.md) |
| `RED-TEAMING.md` | red-team runbook / target notes |

The app code lives once at the repo root. Both edges build the same `backend/` and
serve the same `index.html` — the two compose files only differ in the *edge* (how the
site is exposed and TLS'd) and which extra services run. `compose.base.yml` holds the
shared `ollama` + `backend` definitions so the two edges can't drift.

## Running

Configuration comes from `.env` (gitignored; copy `.env.example` and fill it in).

**Caddy host** (default — TLS terminated by an external Caddy on another host):

```sh
docker compose up -d
```

Serves the UI on `:3131`; also brings up `n8n` (:5678) and `stocks-mcp` (:8077) for
Caddy to front. Load the n8n workflows and credentials with `n8n/n8n-sync.sh import`
(see [`n8n/README.md`](n8n/README.md)).

**Azure public VM** (nginx is the public edge, TLS via Let's Encrypt/certbot):

```sh
docker compose -f docker-compose.azure.yml up -d --build
```

Deploy/renewal details, the IP allowlist, and first-cert issuance are in
[`azure/README.md`](azure/README.md). n8n and stocks-mcp are intentionally not part of
the Azure stack.

> Both compose files auto-load `.env` from the directory you run them in, so keep
> `.env` at the repo root.
