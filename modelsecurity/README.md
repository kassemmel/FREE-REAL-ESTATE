# Prisma AIRS — AI Model Security

Scan AI models for threats with Palo Alto Prisma AIRS AI Model Security.

## Contents

- `.env` — all configuration and credentials (git-ignored; not committed)
- `scan.py` — runs a scan via the `model-security-client` SDK; exits non-zero if a model is unsafe
- `pypiurl.sh` — fetches the private PyPI URL for installing the client (see below)

## Setup

Requires **Python 3.11 or 3.12**.

The `model-security-client` package is served from a private PyPI index. Get
its URL either from the SCM "Install AI Model Security" page or with
`pypiurl.sh`, which uses the same service account as `scan.py`:

```sh
cd ~/AIRS/modelsecurity
set -a; . ./.env; set +a          # export MODEL_SECURITY_CLIENT_ID/SECRET, TSG_ID

pip install "model-security-client[all]" --extra-index-url "$(./pypiurl.sh)"
```

`pypiurl.sh` requires `curl` and `jq`. It gets an SCM OAuth2 token
(client-credentials, scope `tsg_id:$TSG_ID`), then calls
`GET $MODEL_SECURITY_API_ENDPOINT/mgmt/v1/pypi/authenticate` and prints the
returned `url`. Optional overrides: `MODEL_SECURITY_API_ENDPOINT` (default
`https://api.sase.paloaltonetworks.com/aims`) and `MODEL_SECURITY_TOKEN_ENDPOINT`
(default `https://auth.apps.paloaltonetworks.com/oauth2/access_token`). It exits
non-zero with an error on stderr if either call fails. The printed URL grants
access to the index — don't commit or paste it anywhere.

`Error: Failed to retrieve PyPI URL` means the token worked but the PyPI call
was rejected. A `403 license_not_found` ("No active license found") response
means the tenant has no active AI Model Security license; activate it in SCM.

Fill in `.env`:

| Variable | Description |
| --- | --- |
| `MODEL_SECURITY_CLIENT_ID` | SCM service-account client id |
| `MODEL_SECURITY_CLIENT_SECRET` | SCM service-account secret |
| `TSG_ID` | Tenant service group id |
| `MODEL_SECURITY_API_ENDPOINT` | API endpoint (default is prefilled) |
| `SECURITY_GROUP_UUID` | Security group holding your model-security rules |
| `MODEL_URI` / `MODEL_PATH` | Scan target — remote URI or local path |
| `MODEL_VERSION` / `MODEL_NAME` / `MODEL_AUTHOR` / `MODEL_LABELS` | Optional metadata |

## Usage

```sh
cd ~/AIRS/modelsecurity

python scan.py                                       # uses MODEL_URI/MODEL_PATH from .env
python scan.py --model-uri https://huggingface.co/microsoft/DialoGPT-medium
python scan.py --model-path ./my-local-model         # scan a local model
python scan.py --model-uri <uri> -l env=staging -l team=ml
```

The script exits `0` when the model passes and non-zero when it fails or is
misconfigured, so it can gate a CI/CD pipeline.

## Notes

- Outbound HTTPS is required to `https://api.sase.paloaltonetworks.com/aims` and
  `https://auth.apps.paloaltonetworks.com`.
- Limits: up to 1,000 files and 50 labels per scan; scans cannot be deleted.
