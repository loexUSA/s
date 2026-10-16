Use the existing checkout at /workspace/s. Each cloud task is already isolated; do not create a Git worktree unless the user explicitly requests one.

This project contains a 1500m experimental Rust map and an installed Linux Rust Dedicated Server. Read server/README.md, server/setup_status.json and server/startup_verification.json. Verify current runtime state instead of treating a saved report as live status. Installation, custom-map loading, navmesh generation and a local A2S_INFO query passed in onboarding. RustEdit geometry, puzzles and client gameplay remain untested. Public access and Steam registration are not confirmed; SteamServer NoConnection was observed after local startup.

Retained files and dependencies:
- Repository and map: /workspace/s; Python environment: /workspace/s/.venv.
- Rust Dedicated Server app 258550: /workspace/rust-server/game (about 6.1 GB installed).
- SteamRE DepotDownloader 3.4.0: /workspace/rust-server/depotdownloader. It uses the configured proxy and anonymous login; no secret is required. Its .NET data stays under that directory via XDG_DATA_HOME.
- Native SteamCMD is also retained at /workspace/rust-server/current-steamcmd, but its updater failed in this environment. The default installer now uses DepotDownloader successfully instead.
- Never assume processes, sessions or connections survive a new task or publication. Do not commit runtime binaries, saves, credentials or full logs.

Install or refresh if needed:
cd /workspace/s
RUST_SERVER_DIR=/workspace/rust-server/game DEPOTDOWNLOADER_DIR=/workspace/rust-server/depotdownloader bash server/install.sh
This downloads the official SteamRE release over verified HTTPS, checks its pinned archive hash, and validates both official Linux Steam depots. It was tested with a complete download and a second validation that reused all existing files. Preserve exit status and inspect the current install log plus game/logs/installation-result.json. A pre-existing binary alone does not establish successful installation.

Startup:
1. Confirm /workspace/rust-server/game/RustDedicated is executable. Check for this task's existing live server before starting a duplicate; validate any recorded PID against its command and identity.
2. From /workspace/s launch RUST_SERVER_DIR=/workspace/rust-server/game bash server/start.sh in a persistent execution session. Record the session ID. The script records its PID in game/logs/server.pid.
3. The script supplies a writable Unity XDG_CONFIG_HOME and adds the validated server/Plugins library directories to LD_LIBRARY_PATH so steamclient.so loads. Do not change HOME. RCON binds only to loopback and no password argument is passed; an explicit empty RCON password crashes current Rust bootstrap.
4. Read the current run's game/logs/server.log for successful custom-map loading and Server startup complete. Navmesh building may take time on a fresh save. Do not accept a marker from an older appended log.
5. Run /workspace/s/.venv/bin/python /workspace/s/server/query.py --host 127.0.0.1 --port 28017. Require an actual Rust A2S_INFO response. The validated response was Mixed Biome Rust, Custom Map, capacity 30.
6. A local query does not prove Steam authentication, server-list registration or public reachability. Inspect current Steam connection errors separately and test from an external Rust client on a persistent UDP-capable host before claiming public hosting works.

Defaults: identity onegrid, 30 players, UDP game port 28015 and query port 28017. Map URL: https://raw.githubusercontent.com/loexUSA/s/refs/heads/main/onegrid_mixed_draft.map
Saves/configuration use game/server/onegrid/; logs use game/logs/. Stop only services this task started. Do not create localhost preview links. Keep TLS, artifact hashes and Steam content validation enabled. Geometry, terrain stamps, monument puzzles/loot, player spawns and resource respawning still need in-game checks.
