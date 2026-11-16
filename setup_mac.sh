#!/usr/bin/env bash
# One-time setup on macOS: venv, deps, seed data, and register the server with Claude Desktop.
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"

PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null && "$c" -c 'import sys; sys.exit(sys.version_info < (3,10))'; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  echo "Python 3.10+ is needed. Install it with:  brew install python@3.12   then re-run this script."; exit 1
fi
echo "Using $($PY --version)"

"$PY" -m venv venv
./venv/bin/pip install -q -r requirements.txt
./venv/bin/python -m dispatch_mcp.db
./venv/bin/python -m pytest -q

CFG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
mkdir -p "$(dirname "$CFG")"
[ -f "$CFG" ] && cp "$CFG" "$CFG.bak" && echo "Backed up existing config to $CFG.bak"
./venv/bin/python - "$CFG" "$ROOT" <<'EOF'
import json, sys, os
cfg, root = sys.argv[1], sys.argv[2]
data = json.load(open(cfg)) if os.path.exists(cfg) and os.path.getsize(cfg) else {}
data.setdefault("mcpServers", {})["dispatch-assistant"] = {
    "command": f"{root}/venv/bin/python",
    "args": ["-m", "dispatch_mcp.server"],
    "cwd": root,
    "env": {"PYTHONPATH": root},
}
json.dump(data, open(cfg, "w"), indent=2)
print("Registered 'dispatch-assistant' in", cfg)
EOF
echo "Done. Quit Claude Desktop fully (Cmd+Q) and reopen it."
