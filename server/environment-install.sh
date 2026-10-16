#!/usr/bin/env bash
set -euo pipefail
cd /workspace/s
python3 -m venv .venv
PIP_CACHE_DIR=/workspace/.cache/pip .venv/bin/python -m pip install --disable-pip-version-check -r requirements.txt
.venv/bin/python verify_map.py onegrid_mixed_draft.map > /tmp/rust-map-structure-check.json
export RUST_SERVER_DIR=/workspace/rust-server/game
export STEAMCMD_DIR=/workspace/rust-server/current-steamcmd
# Current SteamCMD is bootstrapped from official HTTPS packages with SHA256/size checks.
# server/install.sh selects its native linux64 launcher and uses Steam validation.
# SteamCMD logs require writable /home/agent/Steam/logs. Obtain scoped filesystem
# access if needed; do not redefine HOME or weaken verification.
bash server/install.sh
