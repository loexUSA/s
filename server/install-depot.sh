#!/usr/bin/env bash
# Install official Steam app content through SteamRE's proxy-compatible client.
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
server_dir=${RUST_SERVER_DIR:-"$repo_dir/.runtime/rust-server"}
tool_dir=${DEPOTDOWNLOADER_DIR:-"$repo_dir/.runtime/depotdownloader"}
if [[ ${1:-} == --help ]]; then
  cat <<'EOF'
Usage: bash server/install-depot.sh
Options are environment variables:
  RUST_SERVER_DIR        Runtime/server install directory (outside Git).
  DEPOTDOWNLOADER_DIR    Download tool, cache and local .NET data directory.
Installs and validates public Linux Rust Dedicated Server (Steam app 258550).
Uses anonymous Steam login, SteamRE DepotDownloader 3.4.0 and the configured
HTTP(S) proxy. Requires Linux x86_64, curl, Python 3 and 15 GiB free disk.
EOF
  exit 0
fi
[[ $# -eq 0 ]] || { echo 'Use --help for supported options.' >&2; exit 1; }
[[ $(uname -s) == Linux && $(uname -m) == x86_64 ]] || {
  echo 'This installer requires Linux x86_64.' >&2; exit 1;
}
command -v curl >/dev/null || { echo 'curl is required.' >&2; exit 1; }
command -v python3 >/dev/null || { echo 'Python 3 is required.' >&2; exit 1; }
mkdir -p -- "$server_dir" "$tool_dir"
server_dir=$(cd -- "$server_dir" && pwd)
tool_dir=$(cd -- "$tool_dir" && pwd)
available_kib=$(df -Pk -- "$server_dir" | awk 'NR == 2 {print $4}')
if [[ $available_kib -lt 15728640 ]]; then
  echo 'At least 15 GiB free disk is required; allow additional room for updates and saves.' >&2
  exit 1
fi

release=DepotDownloader_3.4.0
archive="$tool_dir/$release-linux-x64.zip"
# Recorded from the official SteamRE GitHub release fetched with verified HTTPS
# on 2026-10-16. This is a reproducibility pin, not a publisher-signed checksum.
archive_sha256=a999dec66b4850fc961bd50366696d23c2d0fad7b18790e6a5647b2f19097a53
archive_url="https://github.com/SteamRE/DepotDownloader/releases/download/$release/DepotDownloader-linux-x64.zip"
temp_dir=$(mktemp -d "$tool_dir/.download.XXXXXX")
trap 'rm -rf -- "$temp_dir"' EXIT
if [[ ! -f $archive ]]; then
  curl --fail --location --proto '=https' --proto-redir '=https' \
    --tlsv1.2 --retry 3 --connect-timeout 30 \
    --output "$temp_dir/release.zip" "$archive_url"
  archive_input="$temp_dir/release.zip"
else
  archive_input=$archive
fi

python3 - "$archive_input" "$archive_sha256" "$tool_dir" "$temp_dir" <<'PY'
import hashlib
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import zipfile

archive = Path(sys.argv[1])
expected = sys.argv[2]
tool_dir = Path(sys.argv[3])
temp_dir = Path(sys.argv[4])
digest = hashlib.sha256(archive.read_bytes()).hexdigest()
if digest != expected:
    raise SystemExit("DepotDownloader archive SHA-256 mismatch; refusing to execute it.")
with zipfile.ZipFile(archive) as package:
    members = package.infolist()
    names = set()
    for member in members:
        path = PurePosixPath(member.filename)
        if (path.is_absolute() or '..' in path.parts or '\\' in member.filename
                or member.filename not in {'DepotDownloader', 'LICENSE'}
                or member.filename in names
                or stat.S_ISLNK(member.external_attr >> 16)):
            raise SystemExit("Unexpected or unsafe path in DepotDownloader release archive.")
        names.add(member.filename)
    if names != {'DepotDownloader', 'LICENSE'}:
        raise SystemExit("DepotDownloader release archive is missing required files.")
    for member in members:
        staged = temp_dir / member.filename
        staged.write_bytes(package.read(member))  # Zip CRC is also checked.
        staged.chmod(0o755 if member.filename == 'DepotDownloader' else 0o644)
        os.replace(staged, tool_dir / member.filename)
print("DepotDownloader 3.4.0 archive SHA-256 verified.")
PY
if [[ $archive_input != "$archive" ]]; then
  mv -- "$archive_input" "$archive"
fi

# .NET isolated storage must be writable; keep HOME and injected auth untouched.
mkdir -p -- "$tool_dir/data" "$server_dir/logs"
install_log=$(mktemp "$server_dir/logs/depot-install.XXXXXX.log")
(
  cd -- "$tool_dir"
  XDG_DATA_HOME="$tool_dir/data" ./DepotDownloader \
    -app 258550 -os linux -osarch 64 -dir "$server_dir" -validate
) 2>&1 | tee "$install_log"

# Check this invocation's completion records, rather than accepting an old binary.
python3 - "$install_log" "$server_dir" <<'PY'
from pathlib import Path
import datetime
import hashlib
import json
import os
import re
import sys

log = Path(sys.argv[1])
server = Path(sys.argv[2])
text = log.read_text(errors='replace')
summary = re.search(
    r'Total downloaded: [0-9]+ bytes \([0-9]+ bytes uncompressed\) from ([0-9]+) depots',
    text,
)
completed = set(re.findall(r'Depot ([0-9]+) - Downloaded [0-9]+ bytes', text))
required = {'258552', '258554'}  # Official Linux and shared Rust server depots.
if (not summary or int(summary.group(1)) < 2 or not required <= completed
        or 'was not completely downloaded' in text):
    raise SystemExit(f"Rust depot download/validation did not complete. See {log}")
launcher = server / 'RustDedicated'
if (not launcher.is_file() or not (server / 'RustDedicated_Data').is_dir()
        or not (server / 'UnityPlayer.so').is_file()):
    raise SystemExit(f"Rust server runtime files are missing after download. See {log}")
# This depot can omit the executable permission. Preserve validated file bytes
# and all existing permission bits while making the native launcher runnable.
launcher.chmod(launcher.stat().st_mode | 0o100)
if not os.access(launcher, os.X_OK):
    raise SystemExit(f"RustDedicated is not executable after installation. See {log}")
proof = dict(
    checked_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    app_id=258550, platform='linux', architecture=64,
    method='SteamRE DepotDownloader 3.4.0', validation='passed',
    completed_depots=sorted(required), install_log=str(log),
    executable=str(launcher), executable_sha256=hashlib.sha256(launcher.read_bytes()).hexdigest(),
)
(server / 'logs' / 'installation-result.json').write_text(json.dumps(proof, indent=2) + '\n')
PY
echo "RustDedicated installed and Steam-content-validated at: $server_dir"
echo 'The server has not been started. Run bash server/start.sh next.'
