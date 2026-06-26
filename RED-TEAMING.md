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
  `portkey/<model>`.
  - ⚠️ Portkey routes are scanned *inside* the gateway (`backend/app.py:364`),
    so a Portkey scan tests gateway-guardrail + model, not the raw model.

## Step 3 — Response mapping

On success the app returns:

```json
{ "content": "<model reply>", "verdict": {}, "debug": {} }
```

In the response-config step, mark the reply field as:

```json
"content": "{RESPONSE}"
```

So `{RESPONSE}` ← `content` (`backend/app.py:445`).

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

## Reference

- Scan endpoint targeted: `POST https://chatbot.demo-networks.com/api/chat`
- Guardrail toggle: `POST https://chatbot.demo-networks.com/api/airs/toggle`
- Status: `GET https://chatbot.demo-networks.com/api/status`

Programmatic alternative (not used here): the AI Red Teaming REST API at
`https://api.sase.paloaltonetworks.com/ai-red-teaming` (OAuth 2.0 bearer),
operations: create target → launch scan → retrieve report.

Docs:
- https://docs.paloaltonetworks.com/ai-runtime-security/ai-red-teaming/identify-ai-system-risks-with-ai-red-teaming/get-started-with-prisma-airs-ai-red-teaming/targets/add-a-target-rest-api-or-streaming-cm
- https://docs.paloaltonetworks.com/ai-runtime-security/ai-red-teaming/identify-ai-system-risks-with-ai-red-teaming/get-started-with-prisma-airs-ai-red-teaming
- https://pan.dev/prisma-airs-redteam/api/ai-integration/introduction/
