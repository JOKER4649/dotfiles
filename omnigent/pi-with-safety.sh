#!/bin/sh
set -eu

# OmniGent gateway 每次都会生成 models.json，补入必需的终端用户标识。
if [ -n "${PI_CODING_AGENT_DIR:-}" ] && [ -f "$PI_CODING_AGENT_DIR/models.json" ]; then
    python3 - "$PI_CODING_AGENT_DIR/models.json" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    config = json.loads(path.read_text())
except (OSError, json.JSONDecodeError):
    raise SystemExit(0)
changed = False
for provider in config.get("providers", {}).values():
    if provider.get("api") != "openai-responses":
        continue
    for model in provider.get("models", []):
        if not model.get("id"):
            continue
        params = model.setdefault("samplingParams", {})
        if params.get("safety_identifier") != "omnigent-trial":
            params["safety_identifier"] = "omnigent-trial"
            changed = True

if changed:
    path.write_text(json.dumps(config, separators=(",", ":")))
PY
fi

exec /usr/local/bin/pi "$@"
