#!/usr/bin/env bash
# Foreground startup; use a service manager on a persistent hosting machine.
set -euo pipefail
repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
server_dir=${RUST_SERVER_DIR:-"$repo_dir/.runtime/rust-server"}
identity=${RUST_IDENTITY:-onegrid}
hostname=${RUST_SERVER_NAME:-Mixed Biome Rust}
game_port=${RUST_GAME_PORT:-28015}
query_port=${RUST_QUERY_PORT:-28017}
max_players=${RUST_MAX_PLAYERS:-30}
map_url=${RUST_MAP_URL:-https://raw.githubusercontent.com/loexUSA/s/refs/heads/main/onegrid_mixed_draft.map}
if [[ ${1:-} == --help ]]; then
  cat <<'EOF'
Usage: bash server/start.sh
Starts RustDedicated in the foreground with the repository's custom map.
RUST_SERVER_DIR overrides the runtime directory. Optional settings:
RUST_IDENTITY, RUST_SERVER_NAME, RUST_GAME_PORT, RUST_QUERY_PORT,
RUST_MAX_PLAYERS, RUST_MAP_URL (a reachable HTTPS map URL).
Default ports: 28015/UDP (game), 28017/UDP (query). RCON is not enabled.
EOF
  exit 0
fi
[[ $identity =~ ^[A-Za-z0-9_-]+$ ]] || { echo 'Invalid server identity.' >&2; exit 1; }
for port in "$game_port" "$query_port"; do
  [[ $port =~ ^[0-9]{1,5}$ ]] && ((10#$port > 0 && 10#$port <= 65535)) || {
    echo 'Ports must be integers from 1 through 65535.' >&2; exit 1;
  }
done
game_port=$((10#$game_port))
query_port=$((10#$query_port))
[[ $game_port != "$query_port" ]] || { echo 'Game and query ports must differ.' >&2; exit 1; }
[[ $max_players =~ ^[0-9]{1,4}$ ]] && ((10#$max_players > 0)) || { echo 'Invalid player limit.' >&2; exit 1; }
[[ $map_url == https://* ]] || { echo 'Map URL must use HTTPS.' >&2; exit 1; }
[[ -x $server_dir/RustDedicated ]] || {
  echo "RustDedicated is not installed at $server_dir. Run bash server/install.sh first." >&2
  exit 1
}
server_dir=$(cd -- "$server_dir" && pwd)
mkdir -p -- "$server_dir/logs"
cd -- "$server_dir"
exec ./RustDedicated -batchmode -nographics \
  +server.identity "$identity" +server.hostname "$hostname" \
  +server.level 'Procedural Map' +server.levelurl "$map_url" \
  +server.ip 0.0.0.0 +server.port "$game_port" +server.queryport "$query_port" \
  +rcon.ip 127.0.0.1 +rcon.password '' \
  +server.maxplayers "$max_players" \
  -logfile "$server_dir/logs/server.log"

