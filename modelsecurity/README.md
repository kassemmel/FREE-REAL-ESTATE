# Prisma AIRS — AI Model Security

Scan AI models for threats with Palo Alto Prisma AIRS AI Model Security.

## Contents

- `.env` — all configuration and credentials (git-ignored; not committed)
- `scan.py` — runs a scan via the `model-security-client` SDK; exits non-zero if a model is unsafe

## Setup

Requires **Python 3.11 or 3.12**.

```sh
# Install the client. The --extra-index-url is shown on the SCM
# "Install AI Model Security" page.
pip install "model-security-client[all]" --extra-index-url <URL from SCM>
```

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
