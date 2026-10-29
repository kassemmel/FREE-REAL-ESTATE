# n8n workflows as code

The n8n container (`bleepbloopbot-n8n`, see `docker-compose.yml`) stores its
workflows in the `n8n_data` volume. This folder is the source of truth for them.

| File | What |
|------|------|
| `workflows/se-roundtable.json` | `SE Roundtable` — Chat Trigger (Basic Auth), REST red-teaming target |
| `workflows/se-roundtable-airt-n8n-target.json` | `SE Roundtable (AIRT n8n target)` — Webhook (Header Auth), native n8n red-teaming target |
| `credentials.template.json` | Credentials the workflows use, with `${VAR}` placeholders filled from `.env` |
| `n8n-sync.sh` | `export` / `import` between this folder and the running container |

Endpoints and SCM settings for both targets: [`../RED-TEAMING.md`](../RED-TEAMING.md).

## Recreate on a fresh host

```bash
cp .env.example .env         # fill in all values, incl. the n8n/Portkey MCP ones
docker compose up -d
n8n/n8n-sync.sh import       # credentials + workflows, publish, restart n8n
```

`import` overwrites workflows/credentials with the same IDs, publishes both
workflows, and restarts n8n (a few seconds of downtime) since published state
is only picked up on start. It is safe to re-run.

Before first use, create the n8n owner account in the editor — the CLI import
assigns workflows to it.

## After editing a workflow in the n8n UI

```bash
n8n/n8n-sync.sh export       # writes sanitized workflows/*.json
git diff n8n/                # review, then commit
```

`export` drops instance state (owner/project, version IDs, timestamps, active
flag) so the files only change when the workflow does. Credentials are never
exported — only their IDs appear in the workflow JSON.

## Credentials

| ID | n8n name | Type | From `.env` |
|----|----------|------|-------------|
| `aypPOwgmZuWI3Jk0` | OpenAI account | openAiApi (→ Portkey AI gateway) | `PORTKEY_API_KEY`, `PORTKEY_BASE_URL` |
| `GjVTRCGVMxfuQ8Tm` | Header Auth account | httpHeaderAuth `x-portkey-api-key` (stocks-mcp) | `PORTKEY_MCP_API_KEY` |
| `AirtHdrAuth00001` | AIRT Webhook Header Auth | httpHeaderAuth `X-AIRT-Key` | `N8N_AIRT_HEADER_SECRET` |
| `ChatBasicAuth001` | Chat Trigger Basic Auth | httpBasicAuth | `N8N_CHAT_BASIC_USER`, `N8N_CHAT_BASIC_PASSWORD` |

Adding a credential: create it in n8n, reference it from a workflow, then add an
entry with the same `id`/`type`/field names to `credentials.template.json` and
the backing variable to `.env` / `.env.example`.

## Notes

- Workflow edits made in the n8n UI are lost on the next `import` unless you
  `export` and commit them first.
- The AIRT workflow's 446 branch catches *any* agent error, not only Portkey
  guardrail blocks — check the n8n execution log if a scan shows unexpected
  blocks.
