# BleepBloopBot — Prisma AIRS AI Red Teaming (SCM)

How to red-team the BleepBloopBot chatbot using **Prisma AIRS AI Red Teaming**,
configured through **Strata Cloud Manager (SCM)**.

> Note: this is a *different* product surface from the inline AIRS guardrail the
> app already calls (`POST {region}/v1/scan/sync/request`, `backend/app.py:105`).
> AI Red Teaming is an autonomous attacker that fires categorized attacks
> (jailbreaks, prompt injection, PII exfil, etc.) at the running app and scores
> how it holds up. It uses the red-teaming **deployment profile** on the tenant.

- **Target app:** BleepBloopBot
- **Public endpoint:** `https://chatbot.demo-networks.com/api/chat`
- **Method:** SCM console (UI)

---

## Where in SCM

Strata Cloud Manager → **Insights → Prisma AIRS → AI Red Teaming**
(the existing red-teaming deployment profile authorizes this).

---

## Step 1 — Add a Target

- **Targets → Add Target**
- **Name:** `BleepBloopBot` (or per-route, e.g. `BleepBloopBot-azure-o4mini`)
- **Type:** Application
- **Connection Method:** REST API
- **Endpoint accessibility:** Public (`chatbot.demo-networks.com` over TLS)

## Step 2 — Import via cURL

Use the **Import via cURL** option and paste:

```bash
curl -X POST https://chatbot.demo-networks.com/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "model": "azure/o4-mini",
    "messages": [{ "role": "user", "content": "{INPUT}" }]
  }'
```

- No auth header — `/api/chat` is unauthenticated (`backend/app.py:349`).
- `{INPUT}` = where AI Red Teaming injects each attack prompt.
- Swap `"model"` per scan to test each route: `ollama`, `azure/o4-mini`, or
  `AIGW/<model>` (the Portkey AI gateway).
  - Ollama models use their exact name from `GET /api/models`, e.g.
    `hf.co/unsloth/SmolLM3-3B-GGUF:latest` (note `SmolLM3` casing — a typo
    returns `{"error": ...}` with no `content`, failing SCM validation).
    SmolLM3 runs on CPU: keep the rate limit low and the timeout generous. Its
    replies start with an empty `<think></think>` block — harmless.
  - ⚠️ Gateway routes are scanned *inside* the gateway (`backend/app.py:358`),
    so an `AIGW/` scan tests gateway-guardrail + model, not the raw model.

## Step 3 — Response mapping

On success the app returns:

```json
{ "content": "<model reply>", "verdict": {}, "debug": {} }
```

In the response-config step, mark the reply field as:

```json
"content": "{RESPONSE}"
```

So `{RESPONSE}` ← `content` (`backend/app.py:445`). This is the same for every
model route — don't reuse the n8n target's `output` mapping here, or validation
fails with `response key 'output' not found`.

## Step 4 — Guardrail methodology (important for this app)

The app's **own** AIRS runtime scan blocks malicious prompts before the model and
returns `{"blocked": true, ...}` with **no `content` field** (`backend/app.py:378`).
That breaks `{RESPONSE}` extraction on blocked turns — which AI Red Teaming reads
as a refusal/empty (correct: attack stopped). Run **two scans** to separate model
risk from guardrail value:

| Scan         | App state                                       | Measures                  |
|--------------|-------------------------------------------------|---------------------------|
| A — baseline | AIRS **off** (`POST /api/airs/toggle`, `app.py:163`) | Raw model vulnerability   |
| B — protected| AIRS **on**                                     | How much AIRS mitigates   |

Comparing attack-success-rate A vs B is the guardrail efficacy number.

## Step 5 — Advanced + submit

- Set a **rate limit** (Azure o4-mini / Ollama throttle under hundreds of
  attacks — keep it modest).
- Add **Target Background** (industry/use case: real-estate chatbot demo) —
  improves attack relevance.
- **Multi-turn:** supported for REST. The app is stateless (full `messages`
  history per call), so AI Red Teaming replays accumulated turns into the array.
  Enable multi-turn if you want conversational jailbreaks.
- **Submit**, then **Launch Scan** against the target and review the **Scan
  Report** (attack success rates + per-attack breakdown).

---

## Pre-launch checklist

1. `chatbot.demo-networks.com/api/chat` reachable from the internet ✅ (public)
2. Pick the model route for this scan (set in the cURL body)
3. Toggle AIRS off for scan A / on for scan B
4. Rate limit set so you don't hammer the model backend

---

---

# n8n Agent target

The second app: an n8n **AI Agent** workflow exposed via a **Chat Trigger** node,
with the **stocks-mcp** MCP tool attached. The workflow lives in the `n8n_data`
volume (not the repo), so the values below come from the Chat Trigger node in n8n.

- **Type:** Agent
- **Connection Method:** REST API
- **Endpoint accessibility:** Public (`n8n.demo-networks.com` over TLS, via Caddy)
- **Chat URL:** `https://n8n.demo-networks.com/webhook/e5616171-e3b5-4c39-81d4-67409f9fa60a/chat`
- **Auth:** Basic Auth on the Chat Trigger node (credential `Chat Trigger Basic Auth`).
  Username/password are `N8N_CHAT_BASIC_USER` / `N8N_CHAT_BASIC_PASSWORD` in
  `~/AIRS/.env` — enter them in SCM; don't commit them here.
- Workflow must be **Active** for the production `/webhook/` path to respond
  (otherwise it's `/webhook-test/`, live only while the node is listening).

## Import via cURL

```bash
curl -X POST https://n8n.demo-networks.com/webhook/e5616171-e3b5-4c39-81d4-67409f9fa60a/chat \
  -H "Content-Type: application/json" \
  -u "$N8N_CHAT_BASIC_USER:$N8N_CHAT_BASIC_PASSWORD" \
  -d '{
    "action": "sendMessage",
    "sessionId": "airs-redteam-001",
    "chatInput": "{INPUT}"
  }'
```

- `chatInput` carries each attack prompt (`{INPUT}`).
- `action: "sendMessage"` matches the n8n hosted-chat protocol.
- `sessionId` gives the agent memory — keep constant within a scan for multi-turn
  jailbreaks, or let AIRS vary it per conversation.
- If the cURL import doesn't carry the credential, add a custom header:
  `Authorization: Basic <base64(username:password)>`.

## Response mapping

An AI Agent behind a Chat Trigger returns:

```json
{ "output": "<agent reply>" }
```

So mark `"output": "{RESPONSE}"`.

## Agent-specific scope

This target has **tool access** (stocks-mcp MCP node), so red-teaming covers more
than the model: tool-abuse, excessive-agency, and SSRF-via-tool attacks are in
scope (they are not for BleepBloopBot). Add this to the target **Background**
(use case: stock-info agent with MCP tool access) so AIRS selects relevant attacks.

## Guardrail layer

The agent's LLM calls are routed **through the Portkey gateway**, so a guardrail
layer sits in front of the model (Portkey-side checks, incl. the AIRS guardrail).
Caveat: the Portkey AIRS guardrail is **US-only** and the project key is
German-region (403), so the *effective* guardrail is whatever else is active in
the Portkey config — not the AIRS guardrail. So an n8n scan tests
model + tools + Portkey guardrail together.

For a baseline-vs-protected comparison (like the AIRS on/off split on
BleepBloopBot), toggle the guardrail in the **Portkey config** attached to the
agent's API key — there is no app-side toggle for the n8n path.

---

# n8n Agent target — native n8n connection method

Alternative to the REST target above, using AI Red Teaming's built-in **n8n**
connection method. It runs as a **separate workflow** so the Chat Trigger path
above keeps working unchanged:

| Workflow (n8n)                       | ID                 | Trigger                         | Path |
|--------------------------------------|--------------------|---------------------------------|------|
| `SE Roundtable`                      | `OMB6hw7URGliSmqM` | Chat Trigger (REST target above)| `/webhook/e5616171-…/chat` |
| `SE Roundtable (AIRT n8n target)`    | `AirtSERoundtbl01` | Webhook + Respond to Webhook    | `/webhook/airt-se-roundtable` |

The new workflow is a copy of the original (same agent, model via Portkey, tools,
memory) with these changes:

- **Webhook** node: `POST`, path `airt-se-roundtable`, Respond = *Using 'Respond to
  Webhook' Node*, Auth = **Header Auth** (credential `AIRT Webhook Header Auth`).
- Agent prompt = `{{ $('Webhook').item.json.body.chatInput }}`.
- Simple Memory session key = `{{ $('Webhook').item.json.body.sessionId }}`
  (multi-turn context per AIRT conversation).
- **Respond to Webhook** → `{ "output": <agent reply> }` (HTTP 200).
- Agent error output → **Respond Guardrail Block** → HTTP **446**
  `{ "error": "blocked by guardrail", "detail": "..." }`. Portkey returns 446 when
  its guardrail fails; without this branch a block came back as an empty 200.

## SCM target settings

- **Target Type:** Agent · **Connection Method:** n8n
- **Modality:** Text (the workflow has no file-extraction nodes — leave Files/Images off)
- **Endpoint accessibility:** Public
- **Webhook URL:** `https://n8n.demo-networks.com/webhook/airt-se-roundtable`
- **Supports Streaming:** No
- **Authentication:** Header — name `X-AIRT-Key`, value = `N8N_AIRT_HEADER_SECRET`
  from `~/AIRS/.env` (not committed)
- **Supports Multi-Turn:** Yes (default)
- **Request / Response JSON:** leave defaults (`chatInput` + `sessionId` in,
  `output` out)
- **Guardrails/Content Filters:** Error Code `446`, Sample Exception JSON:
  `{ "error": "blocked by guardrail", "detail": "Your request is invalid or could not be processed by the service" }`
- **Background:** same as the REST n8n target (stock-info agent with MCP tool access).

Quick check:

```bash
curl -X POST https://n8n.demo-networks.com/webhook/airt-se-roundtable \
  -H "Content-Type: application/json" -H "X-AIRT-Key: $N8N_AIRT_HEADER_SECRET" \
  -d '{"chatInput":"Reply with just OK","sessionId":"test-1","files":[]}'
# → {"output":"OK"}
```

Editing the agent (prompt, tools, model) in one workflow does **not** change the
other — keep them in sync manually if you want comparable scans.

---

## Reference

- Scan endpoint targeted: `POST https://chatbot.demo-networks.com/api/chat`
- n8n agent endpoint: `POST https://n8n.demo-networks.com/webhook/e5616171-e3b5-4c39-81d4-67409f9fa60a/chat` (Basic Auth)
- n8n agent endpoint (native n8n target): `POST https://n8n.demo-networks.com/webhook/airt-se-roundtable` (Header `X-AIRT-Key`)
- Guardrail toggle: `POST https://chatbot.demo-networks.com/api/airs/toggle`
- Status: `GET https://chatbot.demo-networks.com/api/status`

Programmatic alternative (not used here): the AI Red Teaming REST API at
`https://api.sase.paloaltonetworks.com/ai-red-teaming` (OAuth 2.0 bearer),
operations: create target → launch scan → retrieve report.

Docs:
- https://docs.paloaltonetworks.com/ai-runtime-security/ai-red-teaming/identify-ai-system-risks-with-ai-red-teaming/get-started-with-prisma-airs-ai-red-teaming/targets/add-a-target-rest-api-or-streaming-cm
- https://docs.paloaltonetworks.com/ai-runtime-security/ai-red-teaming/identify-ai-system-risks-with-ai-red-teaming/get-started-with-prisma-airs-ai-red-teaming
- https://pan.dev/prisma-airs-redteam/api/ai-integration/introduction/
