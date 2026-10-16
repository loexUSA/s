# Rust Dedicated Server

Install on a Linux x86_64 host and run the repository's custom map:

```sh
bash server/install.sh
bash server/start.sh
```

The installer uses Valve's current HTTPS SteamCMD manifest and checks each
package's exact SHA-256 hash and size before extracting it. It selects the
native `linux64` launcher provided by the current official packages, then uses
anonymous Steam app **258550** with Steam content validation enabled. TLS and
the SteamCMD updater's own checks stay enabled. An older, preinstalled SteamCMD
may still require 32-bit libraries; the current bundled launcher avoids that
requirement on this workspace. See both scripts' `--help` output.
The runtime directory defaults to `.runtime/rust-server`, outside version control.
Set `RUST_SERVER_DIR` to put it elsewhere, using the same value for both scripts.
An existing SteamCMD executable/wrapper can be selected with `STEAMCMD_EXECUTABLE`.
The bootstrap helper preserves existing nonempty destinations; choose a new
`STEAMCMD_DIR` rather than overwriting an unrelated or older installation.

To download and verify just the current official SteamCMD launcher packages:

```sh
python3 server/bootstrap_current_steamcmd.py --directory .runtime/steamcmd
```

This step has been tested successfully. It prepares SteamCMD, not RustDedicated.
The workspace's native 64-bit SteamCMD launch succeeds, but its updater still
fails with an online-update error. Consequently no actual Rust server files
have yet been installed and no server is currently running here.
The updater reports `http error 0` for official manifests even though the same
HTTPS manifest is reachable with Python. A focused trace showed DNS activity
without a subsequent TCP/TLS connection; native resolver/proxy compatibility
remains unresolved. Neither TLS verification nor artifact checks were disabled.

The server runs in the foreground. A service manager on a persistent host is
needed for continuous hosting; no background service is silently installed.
Logs are in `$RUST_SERVER_DIR/logs/server.log`; saves/configuration use
`$RUST_SERVER_DIR/server/onegrid/`. Server binaries, credentials, logs and player
saves are not part of the GitHub project.

## Check startup

Check the **current run's** log for successful custom-map loading and
`Server startup complete`. Then query the running server:

```sh
python3 server/query.py --host 127.0.0.1 --port 28017
```

A log message, listening socket, or successful installation alone does not
establish gameplay readiness. Join the server with a Rust client and validate
monument placement, puzzles, loot, AI, spawn positions and resource respawning.
The map is still a draft until those checks pass.

## Connections

Expose **28015/UDP** for game traffic and **28017/UDP** for server queries on
the hosting machine, its firewall and any upstream NAT/router. The default
script sets RCON's address to loopback and leaves its password empty, disabling
RCON by default even with a reused configuration. RCON TCP and Rust+
are optional and need their own configuration if used. An HTTP-only preview
does not provide Rust UDP hosting.

SteamCMD needs access to Valve's content and Steam services, including
`steamcdn-a.akamaihd.net`, `*.steampowered.com`, `*.steamstatic.com`,
`*.steamcontent.com`, and `*.steamserver.net`. Domain permission does not by
itself prove Steam's native network protocols or incoming game traffic work.
The map URL also requires `raw.githubusercontent.com`.

See `setup_status.json` for the observed status in the cloud workspace. Do not
interpret checked-in scripts as proof that server files were downloaded or a
public server is running.
