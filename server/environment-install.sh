#!/usr/bin/env bash
set -euo pipefail
cd /workspace/s
python3 -m venv .venv
PIP_CACHE_DIR=/workspace/.cache/pip .venv/bin/python -m pip install --disable-pip-version-check -r requirements.txt
.venv/bin/python verify_map.py onegrid_mixed_draft.map > /tmp/rust-map-structure-check.json
export RUST_SERVER_DIR=/workspace/rust-server/game
export DEPOTDOWNLOADER_DIR=/workspace/rust-server/depotdownloader
export RUST_INSTALLER=depot
# Uses SteamRE's official HTTPS release and validates Steam app 258550 content.
# Local .NET storage is kept writable without redefining HOME.
bash server/install.sh
