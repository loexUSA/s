Use the existing checkout at /workspace/s. Each cloud task is already isolated; do not create a Git worktree unless the user explicitly requests one.

This project contains a 1500m experimental Rust map and Rust Dedicated Server setup tools. Read server/README.md and server/setup_status.json, then verify current runtime state rather than assuming an old status report is still accurate. The map passes binary checks, but RustEdit integration and actual gameplay remain unvalidated.

Dependencies and runtime files:
- Map Python environment: /workspace/s/.venv (numpy/scipy from requirements.txt).
- Official SteamCMD: /workspace/rust-server/current-steamcmd. Its current packages provide native linux64/steamcmd; install.sh selects that launcher.
- Rust server install, saves and logs: /workspace/rust-server/game. Binaries, packages, saves and credentials are intentionally not committed.
- The prior onboarding attempt downloaded and hash-verified SteamCMD, but native SteamCMD's updater failed to retrieve official manifests with "http error 0" before TCP/TLS connections. Consequently RustDedicated was not installed and no game server was running. Investigate current state; do not describe that unresolved prerequisite as completed.
- Normal SteamCMD logging is /home/agent/Steam/logs. Creating that directory required scoped filesystem access. Do not change HOME, disable TLS/signature/checksum verification, or use skip-update flags.

Install or refresh:
cd /workspace/s
RUST_SERVER_DIR=/workspace/rust-server/game STEAMCMD_DIR=/workspace/rust-server/current-steamcmd bash server/install.sh
Preserve the command exit status and inspect the current install log. A zero SteamCMD exit or pre-existing binary is insufficient; the installer also requires the completed app 258550 validation marker. If the same native networking failure persists, report it and continue only independent work; do not repeat an unchanged failed command.

Startup after successful installation:
1. Confirm /workspace/rust-server/game/RustDedicated exists and is executable.
2. From /workspace/s launch RUST_SERVER_DIR=/workspace/rust-server/game bash server/start.sh in a persistent execution session. Capture that session ID. Retained files and dependencies do not imply live processes survive a new task.
3. Inspect only the current run's /workspace/rust-server/game/logs/server.log for successful custom-map loading and "Server startup complete"; distinguish appended old output from this run.
4. Run /workspace/s/.venv/bin/python /workspace/s/server/query.py --host 127.0.0.1 --port 28017. Require an actual Rust A2S_INFO response, not merely a PID or open port.
5. Test monument ground integration, puzzles, loot, AI navigation, player spawns, buildable areas and resource respawning with RustEdit/current game clients before claiming gameplay readiness.

Default map URL: https://raw.githubusercontent.com/loexUSA/s/refs/heads/main/onegrid_mixed_draft.map
Default identity: onegrid; max players: 30. The launcher binds game UDP 28015 and query UDP 28017; RCON stays disabled with loopback binding and an empty password.
Public hosting additionally requires a persistent host and externally verified inbound routing/firewall access for those UDP ports. Neither a local query nor an HTTP preview proves public reachability. Do not create localhost preview links. Stop only services started by this task when troubleshooting.
