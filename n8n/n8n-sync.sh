#!/usr/bin/env bash
# Sync the n8n workflows/credentials between this repo and the running n8n container.
#
#   n8n/n8n-sync.sh export   # running n8n -> n8n/workflows/*.json (sanitized, no secrets)
#   n8n/n8n-sync.sh import   # repo + .env -> running n8n, publish, restart n8n
#
# Credentials are never stored in the repo: credentials.template.json holds
# ${VAR} placeholders that are filled from .env at import time. Workflows
# reference credentials by the fixed IDs in that template.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$HERE")"
CONTAINER="${N8N_CONTAINER:-bleepbloopbot-n8n}"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"
WF_DIR="$HERE/workflows"

n8n() { docker exec "$CONTAINER" n8n "$@" 2>&1 | grep -vE 'PostHog|Rudder|Error tracking|ECONNREFUSED' || true; }
# /tmp files in the container are root-owned after docker cp; remove as root.
cleanup() { docker exec -u 0 "$CONTAINER" rm -rf /tmp/n8n-sync >/dev/null 2>&1 || true; }

cmd_export() {
  cleanup; trap cleanup EXIT
  docker exec "$CONTAINER" mkdir -p /tmp/n8n-sync/wf
  n8n export:workflow --all --separate --output=/tmp/n8n-sync/wf/ >/dev/null
  local tmp; tmp="$(mktemp -d)"
  docker cp "$CONTAINER:/tmp/n8n-sync/wf/." "$tmp/"
  rm -f "$WF_DIR"/*.json; mkdir -p "$WF_DIR"
  python3 - "$tmp" "$WF_DIR" <<'PY'
import json, os, re, sys
src, dst = sys.argv[1:]
# Instance/runtime state that differs per install or would leak account info.
DROP = {"shared", "versionId", "activeVersionId", "versionCounter", "triggerCount",
        "createdAt", "updatedAt", "versionMetadata", "staticData", "pinData", "active"}
for f in sorted(os.listdir(src)):
    w = json.load(open(os.path.join(src, f)))
    for k in DROP: w.pop(k, None)
    w["tags"] = [{"id": t["id"], "name": t["name"]} for t in w.get("tags", [])]
    slug = re.sub(r"[^a-z0-9]+", "-", w["name"].lower()).strip("-")
    json.dump(w, open(os.path.join(dst, f"{slug}.json"), "w"), indent=2, ensure_ascii=False)
    open(os.path.join(dst, f"{slug}.json"), "a").write("\n")
    print(f"exported {w['id']}  {w['name']}  -> n8n/workflows/{slug}.json")
PY
  rm -rf "$tmp"
}

cmd_import() {
  [ -f "$ENV_FILE" ] || { echo "missing $ENV_FILE" >&2; exit 1; }
  cleanup; trap 'cleanup; rm -rf "${tmp:-}"' EXIT
  tmp="$(mktemp -d)"
  # Fill ${VAR} placeholders from .env; fail on any missing/empty value.
  python3 - "$HERE/credentials.template.json" "$ENV_FILE" "$tmp/credentials.json" <<'PY'
import json, re, sys
tpl, envf, out = sys.argv[1:]
env = {}
for line in open(envf):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1); env[k] = v.strip().strip('"').strip("'")
missing = set()
def sub(m):
    v = env.get(m.group(1), "")
    if not v: missing.add(m.group(1))
    return json.dumps(v)[1:-1]
data = re.sub(r"\$\{([A-Z0-9_]+)\}", sub, open(tpl).read())
if missing: sys.exit(f"missing in .env: {', '.join(sorted(missing))}")
json.dump(json.loads(data), open(out, "w"))
PY
  docker exec "$CONTAINER" mkdir -p /tmp/n8n-sync
  docker cp "$tmp/credentials.json" "$CONTAINER:/tmp/n8n-sync/credentials.json"
  docker cp "$WF_DIR/." "$CONTAINER:/tmp/n8n-sync/wf/"
  n8n import:credentials --input=/tmp/n8n-sync/credentials.json
  n8n import:workflow --separate --input=/tmp/n8n-sync/wf/
  for f in "$WF_DIR"/*.json; do
    n8n publish:workflow --id="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["id"])' "$f")"
  done
  cleanup
  # Published state is only picked up on start.
  echo "restarting $CONTAINER ..."
  local since logs=""; since="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  docker restart "$CONTAINER" >/dev/null
  for _ in $(seq 1 60); do
    logs="$(docker logs --since "$since" "$CONTAINER" 2>&1)"
    [[ "$logs" == *"Editor is now accessible"* ]] && break; sleep 2
  done
  grep 'Activated workflow' <<<"$logs" || echo "warning: no workflows reported active" >&2
}

case "${1:-}" in
  export) cmd_export ;;
  import) cmd_import ;;
  *) echo "usage: $0 export|import" >&2; exit 2 ;;
esac
