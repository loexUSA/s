#!/usr/bin/env bash
# Fetch official Rust Dedicated Server app 258550 with SteamCMD's validation.
set -euo pipefail
repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
server_dir=${RUST_SERVER_DIR:-"$repo_dir/.runtime/rust-server"}
steam_dir=${STEAMCMD_DIR:-"$repo_dir/.runtime/steamcmd"}
if [[ ${1:-} == --help ]]; then
  cat <<'EOF'
Usage: bash server/install.sh
Options are environment variables:
  RUST_SERVER_DIR        Runtime/server install directory (outside Git).
  STEAMCMD_DIR           Local SteamCMD install directory.
  STEAMCMD_EXECUTABLE    Existing SteamCMD executable or wrapper, if available.
Installs current public Rust Dedicated Server (Steam app 258550), anonymously.
Requires Linux x86_64, Python 3, Steam access and ample disk.
EOF
  exit 0
fi
[[ $(uname -s) == Linux && $(uname -m) == x86_64 ]] || {
  echo 'This installer requires Linux x86_64.' >&2; exit 1;
}
mkdir -p -- "$server_dir" "$steam_dir"
server_dir=$(cd -- "$server_dir" && pwd)
steam_dir=$(cd -- "$steam_dir" && pwd)
if [[ -n ${STEAMCMD_EXECUTABLE:-} ]]; then
  steam_executable=$STEAMCMD_EXECUTABLE
elif command -v steamcmd >/dev/null 2>&1; then
  steam_executable=$(command -v steamcmd)
else
  steam_executable="$steam_dir/steamcmd.sh"
  if [[ ! -x $steam_executable ]]; then
    python3 "$repo_dir/server/bootstrap_current_steamcmd.py" --directory "$steam_dir"
  fi
fi
[[ -x $steam_executable ]] || { echo "SteamCMD is not executable: $steam_executable" >&2; exit 1; }
available_kib=$(df -Pk -- "$server_dir" | awk 'NR == 2 {print $4}')
if [[ $available_kib -lt 15728640 ]]; then
  echo 'At least 15 GiB free disk is required; allow additional room for updates and saves.' >&2
  exit 1
fi
mkdir -p -- "$server_dir/logs"
install_log=$(mktemp "$server_dir/logs/install.XXXXXX.log")
steam_command=("$steam_executable" +force_install_dir "$server_dir" +login anonymous
  +app_update 258550 validate +quit)
if [[ -x $(dirname -- "$steam_executable")/linux64/steamcmd ]]; then
  STEAM_PLATFORM=linux64 "${steam_command[@]}" 2>&1 | tee "$install_log"
else
  "${steam_command[@]}" 2>&1 | tee "$install_log"
fi
if ! grep -Fq "Success! App '258550' fully installed." "$install_log"; then
  echo "SteamCMD did not confirm completed installation/validation. See $install_log" >&2
  exit 1
fi
[[ -x $server_dir/RustDedicated ]] || {
  echo 'SteamCMD exited without installing RustDedicated; inspect its logs.' >&2; exit 1;
}
echo "RustDedicated installed and Steam-validated at: $server_dir"
echo 'The server has not been started. Run bash server/start.sh next.'
