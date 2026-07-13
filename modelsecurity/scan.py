#!/usr/bin/env python3
"""Scan an AI model with Prisma AIRS AI Model Security.

Reads credentials and scan defaults from the .env file next to this script, then
runs a scan via the model-security-client SDK. Exits non-zero when the model is
found unsafe, so it can gate a CI/CD pipeline.

Prereqs:
    Python 3.11 or 3.12
    pip install "model-security-client[all]" --extra-index-url <URL from SCM>

Usage:
    python scan.py                                  # uses MODEL_URI / MODEL_PATH from .env
    python scan.py --model-uri https://huggingface.co/microsoft/DialoGPT-medium
    python scan.py --model-path ./my-local-model
    python scan.py --model-uri <uri> -l env=staging -l team=ml
"""

import argparse
import os
import sys
from pathlib import Path

ENV_FILE = Path(__file__).with_name(".env")


def load_env(path: Path) -> None:
    """Minimal .env loader so we don't need python-dotenv. Does not overwrite
    variables already present in the real environment."""
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def parse_labels(items) -> dict:
    """Turn ['env=production', 'team=ml'] into {'env': 'production', 'team': 'ml'}."""
    labels = {}
    for item in items or []:
        for pair in item.split(","):
            pair = pair.strip()
            if not pair:
                continue
            k, _, v = pair.partition("=")
            if k.strip():
                labels[k.strip()] = v.strip()
    return labels


def build_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Scan an AI model with Prisma AIRS.")
    p.add_argument("--model-uri", default=os.getenv("MODEL_URI") or None,
                   help="Remote model URI (e.g. a Hugging Face URL).")
    p.add_argument("--model-path", default=os.getenv("MODEL_PATH") or None,
                   help="Path to a local model file or directory.")
    p.add_argument("--security-group-uuid", default=os.getenv("SECURITY_GROUP_UUID") or None,
                   help="Security group UUID holding your model-security rules.")
    p.add_argument("--model-version", default=os.getenv("MODEL_VERSION") or None)
    p.add_argument("--model-name", default=os.getenv("MODEL_NAME") or None)
    p.add_argument("--model-author", default=os.getenv("MODEL_AUTHOR") or None)
    p.add_argument("-l", "--label", action="append", default=[],
                   help="Label as key=value (repeatable). Adds to MODEL_LABELS from .env.")
    p.add_argument("--poll-interval-secs", type=int, default=10)
    p.add_argument("--poll-timeout-secs", type=int, default=900)
    return p.parse_args()


def main() -> int:
    load_env(ENV_FILE)
    args = build_args()

    # model-security-client reads these from the environment for OAuth2.
    required = ["MODEL_SECURITY_CLIENT_ID", "MODEL_SECURITY_CLIENT_SECRET", "TSG_ID"]
    missing = [v for v in required if not os.getenv(v)]
    if missing:
        print(f"ERROR: missing required env vars in {ENV_FILE}: {', '.join(missing)}",
              file=sys.stderr)
        return 2

    if not args.security_group_uuid:
        print("ERROR: no security group UUID (set SECURITY_GROUP_UUID or pass "
              "--security-group-uuid).", file=sys.stderr)
        return 2

    if not args.model_uri and not args.model_path:
        print("ERROR: no scan target (set MODEL_URI/MODEL_PATH or pass "
              "--model-uri/--model-path).", file=sys.stderr)
        return 2

    try:
        from model_security_client.api import ModelSecurityAPIClient
    except ImportError:
        print('ERROR: model-security-client not installed. Run:\n'
              '  pip install "model-security-client[all]" --extra-index-url <URL from SCM>',
              file=sys.stderr)
        return 2

    base_url = os.getenv("MODEL_SECURITY_API_ENDPOINT",
                         "https://api.sase.paloaltonetworks.com/aims")
    client = ModelSecurityAPIClient(base_url=base_url)

    labels = parse_labels([os.getenv("MODEL_LABELS", "")] + args.label)

    scan_kwargs = {
        "security_group_uuid": args.security_group_uuid,
        "poll_interval_secs": args.poll_interval_secs,
        "poll_timeout_secs": args.poll_timeout_secs,
    }
    if args.model_uri:
        scan_kwargs["model_uri"] = args.model_uri
    if args.model_path:
        scan_kwargs["model_path"] = args.model_path
    for key, value in (
        ("model_version", args.model_version),
        ("model_name", args.model_name),
        ("model_author", args.model_author),
    ):
        if value:
            scan_kwargs[key] = value
    if labels:
        scan_kwargs["labels"] = labels

    target = args.model_uri or args.model_path
    print(f"Scanning model: {target}")
    result = client.scan(**scan_kwargs)

    outcome = getattr(result, "eval_outcome", result)
    print(f"Scan outcome: {outcome}")

    # Treat anything that isn't an explicit pass as a failure for pipeline gating.
    is_safe = str(outcome).strip().lower() in {"pass", "passed", "safe", "success"}
    if not is_safe:
        print("Model FAILED the security scan.", file=sys.stderr)
        return 1
    print("Model passed the security scan.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
