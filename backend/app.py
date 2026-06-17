import os
import uuid
import json
import logging
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

OLLAMA_URL   = os.environ.get('OLLAMA_URL', 'http://ollama:11434')

# --- Azure AI Foundry / Azure OpenAI ---
# ENDPOINT is the resource endpoint, e.g. https://my-foundry.openai.azure.com
# DEPLOYMENTS is a comma-separated list of deployment names you created in the
# portal (e.g. "gpt-o4,gpt-4o-mini"). Each is offered in the UI as "azure/<name>".
AZURE_ENDPOINT    = os.environ.get('AZURE_OPENAI_ENDPOINT', '').rstrip('/')
AZURE_API_KEY     = os.environ.get('AZURE_OPENAI_API_KEY', '')
AZURE_API_VERSION = os.environ.get('AZURE_OPENAI_API_VERSION', '2024-10-21')
AZURE_DEPLOYMENTS = [d.strip() for d in os.environ.get('AZURE_OPENAI_DEPLOYMENTS', '').split(',') if d.strip()]

# Models surfaced to the UI as "azure/<deployment>" route to Azure; the rest to Ollama.
AZURE_PREFIX = 'azure/'

# --- Portkey AI gateway (OpenAI-compatible) ---
# BASE_URL is the gateway root, e.g. https://api.portkey.ai/v1 (hosted) or a
# self-hosted gateway. MODELS is a comma-separated list of model names to offer;
# each shows up in the UI as "portkey/<name>" and is sent through the gateway.
# A virtual key / config / provider selects the downstream provider in Portkey.
PORTKEY_BASE_URL    = os.environ.get('PORTKEY_BASE_URL', 'https://api.portkey.ai/v1').rstrip('/')
PORTKEY_API_KEY     = os.environ.get('PORTKEY_API_KEY', '')
PORTKEY_VIRTUAL_KEY = os.environ.get('PORTKEY_VIRTUAL_KEY', '')
PORTKEY_PROVIDER    = os.environ.get('PORTKEY_PROVIDER', '')
PORTKEY_CONFIG      = os.environ.get('PORTKEY_CONFIG', '')
PORTKEY_MODELS      = [m.strip() for m in os.environ.get('PORTKEY_MODELS', '').split(',') if m.strip()]

# Models surfaced as "portkey/<model>" route through the Portkey gateway.
PORTKEY_PREFIX = 'portkey/'

AIRS_URL     = os.environ.get('PRISMA_AIRS_URL', 'https://service-de.api.aisecurity.paloaltonetworks.com')
AIRS_API_KEY = os.environ.get('PRISMA_AIRS_API_KEY', '')
AIRS_PROFILE = os.environ.get('PRISMA_AIRS_PROFILE', '')

airs_enabled = True  # runtime toggle; True = scanning active


def _ai_profile():
    """Build the ai_profile reference for AIRS.

    PRISMA_AIRS_PROFILE may be either a profile UUID or a profile name.
    If it parses as a UUID we send it as profile_id, otherwise as profile_name.
    """
    try:
        uuid.UUID(AIRS_PROFILE)
        return {'profile_id': AIRS_PROFILE}
    except (ValueError, AttributeError, TypeError):
        return {'profile_name': AIRS_PROFILE}

PROMPTS_FILE = '/app/data/prompts.json'


def _load_prompts():
    os.makedirs(os.path.dirname(PROMPTS_FILE), exist_ok=True)
    try:
        with open(PROMPTS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_prompts(prompts):
    os.makedirs(os.path.dirname(PROMPTS_FILE), exist_ok=True)
    with open(PROMPTS_FILE, 'w') as f:
        json.dump(prompts, f, indent=2)


def airs_scan(prompt=None, response=None, model='ollama'):
    """Scan content via Prisma AIRS. Returns (result, debug) tuple.
    Falls through with action=allow if AIRS is not configured."""
    if not AIRS_API_KEY or not AIRS_PROFILE:
        app.logger.warning('AIRS not configured — skipping scan')
        return {'action': 'allow', 'configured': False}, None

    tr_id = str(uuid.uuid4())
    content = {}
    if prompt:
        content['prompt'] = prompt[:10000]
    if response:
        content['response'] = response[:20000]

    payload = {
        'tr_id': tr_id,
        'ai_profile': _ai_profile(),
        'metadata': {
            'app_name': 'BleepBloopBot',
            'ai_model': model,
        },
        'contents': [content],
    }

    req_headers = {
        'x-pan-token': f'***REDACTED*** ({len(AIRS_API_KEY)} chars)',
        'Content-Type': 'application/json',
    }
    scan_url = f'{AIRS_URL}/v1/scan/sync/request'

    r = requests.post(
        scan_url,
        json=payload,
        headers={'x-pan-token': AIRS_API_KEY, 'Content-Type': 'application/json'},
        timeout=30,
    )

    debug = {
        'request': {
            'url':     scan_url,
            'method':  'POST',
            'headers': req_headers,
            'body':    payload,
        },
        'response': {
            'status':  r.status_code,
            'headers': dict(r.headers),
            'body':    None,
        },
    }

    if not r.ok:
        app.logger.error('AIRS HTTP %s — body: %s', r.status_code, r.text[:500])
        debug['response']['body'] = r.text[:2000]
        r.raise_for_status()

    try:
        result = r.json()
    except Exception:
        app.logger.error('AIRS non-JSON response (status %s): %s', r.status_code, r.text[:500])
        debug['response']['body'] = r.text[:2000]
        raise ValueError(f'AIRS returned non-JSON response: {r.text[:200]}')

    debug['response']['body'] = result
    result['configured'] = True
    result.setdefault('report_id', tr_id)
    return result, debug


def _verdict_dict(scan, detected_key):
    return {
        'action':     scan.get('action', 'allow'),
        'detected':   scan.get(detected_key, {}),
        'session_id': scan.get('report_id', ''),
    }


@app.route('/api/status')
def status():
    return jsonify({
        'airs_configured': bool(AIRS_API_KEY and AIRS_PROFILE),
        'airs_enabled':    airs_enabled,
        'airs_profile':    AIRS_PROFILE,
    })


@app.route('/api/airs/toggle', methods=['POST'])
def toggle_airs():
    global airs_enabled
    airs_enabled = not airs_enabled
    app.logger.info('AIRS scanning %s', 'enabled' if airs_enabled else 'disabled')
    return jsonify({
        'airs_configured': bool(AIRS_API_KEY and AIRS_PROFILE),
        'airs_enabled':    airs_enabled,
    })


@app.route('/api/prompts', methods=['GET'])
def get_prompts():
    return jsonify(_load_prompts())


@app.route('/api/prompts', methods=['POST'])
def create_prompt():
    body = request.get_json(force=True)
    name = (body.get('name') or '').strip()
    text = (body.get('text') or '').strip()
    if not name or not text:
        return jsonify({'error': 'name and text are required'}), 400
    prompts = _load_prompts()
    prompt = {'id': str(uuid.uuid4()), 'name': name, 'text': text}
    prompts.append(prompt)
    _save_prompts(prompts)
    return jsonify(prompt), 201


@app.route('/api/prompts/<prompt_id>', methods=['DELETE'])
def delete_prompt(prompt_id):
    prompts = _load_prompts()
    prompts = [p for p in prompts if p.get('id') != prompt_id]
    _save_prompts(prompts)
    return jsonify({'ok': True})


class ContentFilterError(Exception):
    """Raised when a provider's own content filter blocks a request (HTTP 400).
    Distinct from a generic failure so the API can surface it as a block.
    `source` is a human label for where the block came from (e.g. 'Azure')."""
    def __init__(self, detections, source='Provider'):
        super().__init__(f'{source} content filter blocked the request')
        self.detections = detections
        self.source = source


def _content_filter_detections(r):
    """If an OpenAI-style 400 response is a content-filter block, return the
    fired categories (e.g. {'violence': True}); otherwise return None."""
    if r.status_code != 400:
        return None
    try:
        err = r.json().get('error', {})
    except Exception:
        return None
    if err.get('code') != 'content_filter':
        return None
    cf = (err.get('innererror') or {}).get('content_filter_result', {})
    fired = {k: v.get('filtered') for k, v in cf.items() if isinstance(v, dict) and v.get('filtered')}
    return fired or {'content_filter': True}


def _portkey_guardrail_detections(body):
    """Summarise a Portkey guardrail denial (HTTP 446) into fired check names,
    pulled from the response's hook_results."""
    hooks = body.get('hook_results') or {}
    fired = {}
    for phase in ('before_request_hooks', 'after_request_hooks'):
        for hook in hooks.get(phase) or []:
            for chk in hook.get('checks') or []:
                if chk.get('verdict') is False or chk.get('passed') is False:
                    fired[chk.get('id') or chk.get('check') or 'guardrail'] = True
    return fired or {'guardrail': True}


def _call_ollama(model, messages):
    r = requests.post(
        f'{OLLAMA_URL}/api/chat',
        json={'model': model, 'messages': messages, 'stream': False},
        timeout=300,
    )
    r.raise_for_status()
    return r.json().get('message', {}).get('content') or ''


def _call_azure(deployment, messages):
    # Two endpoint styles are supported:
    #   * v1 / OpenAI-compatible (endpoint ends with /openai/v1): model in body, no api-version
    #   * classic Azure OpenAI: deployment in the URL path + api-version query param
    if AZURE_ENDPOINT.rstrip('/').endswith('/openai/v1'):
        url     = f'{AZURE_ENDPOINT}/chat/completions'
        params  = {}
        payload = {'model': deployment, 'messages': messages}
    else:
        url     = f'{AZURE_ENDPOINT}/openai/deployments/{deployment}/chat/completions'
        params  = {'api-version': AZURE_API_VERSION}
        payload = {'messages': messages}
    r = requests.post(
        url,
        params=params,
        headers={'api-key': AZURE_API_KEY, 'Content-Type': 'application/json'},
        json=payload,
        timeout=300,
    )
    fired = _content_filter_detections(r)
    if fired is not None:
        raise ContentFilterError(fired, source='Azure content filter')
    r.raise_for_status()
    return r.json()['choices'][0]['message']['content']


def _call_portkey(model, messages):
    # OpenAI-compatible: model in the body, routed by the gateway to the
    # downstream provider selected via virtual key / config / provider header.
    headers = {'Content-Type': 'application/json'}
    if PORTKEY_API_KEY:
        headers['x-portkey-api-key'] = PORTKEY_API_KEY
    if PORTKEY_VIRTUAL_KEY:
        headers['x-portkey-virtual-key'] = PORTKEY_VIRTUAL_KEY
    if PORTKEY_PROVIDER:
        headers['x-portkey-provider'] = PORTKEY_PROVIDER
    if PORTKEY_CONFIG:
        headers['x-portkey-config'] = PORTKEY_CONFIG
    r = requests.post(
        f'{PORTKEY_BASE_URL}/chat/completions',
        headers=headers,
        json={'model': model, 'messages': messages},
        timeout=300,
    )
    if r.status_code == 446:
        # A Portkey guardrail (e.g. the Prisma AIRS guardrail) denied the request.
        try:
            body = r.json()
        except Exception:
            body = {}
        raise ContentFilterError(_portkey_guardrail_detections(body),
                                 source='Prisma AIRS (Portkey gateway)')
    fired = _content_filter_detections(r)
    if fired is not None:
        raise ContentFilterError(fired, source='Portkey content filter')
    r.raise_for_status()
    return r.json()['choices'][0]['message']['content']


def _sanitize_messages(messages):
    """Coerce every message to {role, content:str}. A null/missing content
    (e.g. an Ollama turn that produced nothing) makes Azure reject the whole
    request, which would otherwise poison the rest of the conversation."""
    clean = []
    for m in messages:
        clean.append({'role': m.get('role', 'user'), 'content': m.get('content') or ''})
    return clean


def call_model(model, messages):
    """Route a chat request to the right backend based on the selected model.
    'azure/<deployment>' goes to Azure AI Foundry; everything else to Ollama."""
    messages = _sanitize_messages(messages)
    if model.startswith(AZURE_PREFIX):
        return _call_azure(model[len(AZURE_PREFIX):], messages)
    if model.startswith(PORTKEY_PREFIX):
        return _call_portkey(model[len(PORTKEY_PREFIX):], messages)
    return _call_ollama(model, messages)


@app.route('/api/models')
def models():
    out = []
    # Ollama models — best-effort so Azure still works if Ollama is unreachable.
    try:
        r = requests.get(f'{OLLAMA_URL}/api/tags', timeout=10)
        r.raise_for_status()
        out.extend(r.json().get('models', []))
    except Exception as e:
        app.logger.warning('Ollama tags unavailable: %s', e)
    # Azure AI Foundry deployments, prefixed so /api/chat can route them.
    if AZURE_ENDPOINT and AZURE_API_KEY:
        out.extend({'name': f'{AZURE_PREFIX}{dep}'} for dep in AZURE_DEPLOYMENTS)
    # Portkey gateway models, prefixed so /api/chat routes them through the gateway.
    if PORTKEY_BASE_URL and PORTKEY_MODELS:
        out.extend({'name': f'{PORTKEY_PREFIX}{m}'} for m in PORTKEY_MODELS)
    return jsonify({'models': out})


@app.route('/api/chat', methods=['POST'])
def chat():
    body = request.get_json(force=True)
    messages = body.get('messages', [])
    model    = body.get('model', '')

    last_prompt = next(
        (m['content'] for m in reversed(messages) if m['role'] == 'user'), ''
    )

    prompt_verdict = None
    debug          = {}

    # Portkey-routed traffic is scanned by the AIRS guardrail *inside* the gateway,
    # so skip the app-side scan and let every prompt reach the gateway.
    gateway_scanned = model.startswith(PORTKEY_PREFIX)

    # --- Scan prompt ---
    if airs_enabled and not gateway_scanned:
        try:
            scan, dbg = airs_scan(prompt=last_prompt, model=model)
        except Exception as e:
            app.logger.error('AIRS prompt scan error: %s', e)
            return jsonify({'error': 'Security scan unavailable'}), 502

        if dbg:
            debug['prompt_scan'] = dbg
        prompt_verdict = _verdict_dict(scan, 'prompt_detected')

        if scan.get('action') == 'block':
            app.logger.info('Prompt blocked by AIRS: %s', scan.get('prompt_detected'))
            return jsonify({
                'blocked':    True,
                'stage':      'prompt',
                'detections': scan.get('prompt_detected', {}),
                'session_id': prompt_verdict['session_id'],
                'verdict':    {'prompt': prompt_verdict},
                'debug':      debug,
            })

    # --- Call the model (Ollama or Azure AI Foundry, by model name) ---
    try:
        assistant_text = call_model(model, messages)
    except ContentFilterError as e:
        # The provider's own content filter blocked the prompt (separate from AIRS).
        # Surface it as a block so the AIRS verdict stays visible to the user.
        app.logger.info('Prompt blocked by %s content filter: %s', e.source, e.detections)
        return jsonify({
            'blocked':    True,
            'stage':      'prompt',
            'filter':     e.source,
            'detections': e.detections,
            'session_id': prompt_verdict['session_id'] if prompt_verdict else '',
            'verdict':    {'prompt': prompt_verdict} if prompt_verdict else {},
            'debug':      debug or None,
        })
    except Exception as e:
        app.logger.error('Model request error (%s): %s', model, e)
        # Keep the AIRS verdict/debug so a model failure doesn't blank the panel.
        return jsonify({
            'error':   'Model request failed',
            'verdict': {'prompt': prompt_verdict} if prompt_verdict else None,
            'debug':   debug or None,
        }), 502

    response_verdict = None

    # --- Scan response --- (skipped for Portkey; its output guardrail handles it)
    if airs_enabled and not gateway_scanned:
        try:
            scan, dbg = airs_scan(response=assistant_text, model=model)
        except Exception as e:
            app.logger.error('AIRS response scan error: %s', e)
            return jsonify({'error': 'Security scan unavailable'}), 502

        if dbg:
            debug['response_scan'] = dbg
        response_verdict = _verdict_dict(scan, 'response_detected')

        if scan.get('action') == 'block':
            app.logger.info('Response blocked by AIRS: %s', scan.get('response_detected'))
            return jsonify({
                'blocked':    True,
                'stage':      'response',
                'detections': scan.get('response_detected', {}),
                'session_id': response_verdict['session_id'],
                'verdict':    {'prompt': prompt_verdict, 'response': response_verdict},
                'debug':      debug,
            })

    verdict = {}
    if prompt_verdict:
        verdict['prompt'] = prompt_verdict
    if response_verdict:
        verdict['response'] = response_verdict

    return jsonify({
        'content': assistant_text,
        'verdict': verdict or None,
        'debug':   debug or None,
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
