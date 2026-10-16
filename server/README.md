# Rust Dedicated Server

Install on a Linux x86_64 host and run the repository's custom map:

```sh
bash server/install.sh
bash server/start.sh
```

The default installer uses **SteamRE DepotDownloader 3.4.0** to fetch official
Linux Steam app **258550** content using anonymous login. It works through the
workspace's existing HTTP(S) proxy and keeps Steam manifest/chunk/file
validation enabled. Its self-contained native Linux x64 executable needs no
separate .NET installation. The official HTTPS release archive has a pinned
SHA-256 recorded from the verified download; this is a reproducibility pin,
not a publisher signature. The download tool's .NET storage stays under its
runtime directory, without changing `HOME` or copying authentication values.
See the scripts' `--help` output.
The runtime directory defaults to `.runtime/rust-server`, outside version control.
Set `RUST_SERVER_DIR` to put it elsewhere, using the same value for both scripts.
Set `DEPOTDOWNLOADER_DIR` to reuse the download tool and archive elsewhere.
The workspace uses `/workspace/rust-server/depotdownloader` for the tool and
`/workspace/rust-server/game` for the server files.

## Optional SteamCMD method

On a host where SteamCMD works normally, choose `RUST_INSTALLER=steamcmd`.
An existing SteamCMD executable/wrapper can be selected with
`STEAMCMD_EXECUTABLE`. The current-package bootstrap helper preserves existing
nonempty destinations; choose a new `STEAMCMD_DIR` rather than overwriting an
unrelated or older installation.

To download and verify just the current official SteamCMD launcher packages:

```sh
python3 server/bootstrap_current_steamcmd.py --directory .runtime/steamcmd
```

This step has been tested successfully. It prepares SteamCMD, not RustDedicated.
The workspace's native 64-bit SteamCMD launch succeeds, but its updater still
fails with an online-update error. This does not block the default
DepotDownloader method.
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

In this workspace the complete 6.1 GB server installation and a second content
validation passed. Rust loaded the custom map, spawned 484 map entities,
finished navigation generation and reported `Server startup complete`. A real
local A2S_INFO query returned `Mixed Biome Rust`, `Custom Map`, capacity 30.
The launch script supplies a writable Unity config directory and the bundled
Steam library search path. It records a PID in `logs/server.pid`; confirm that
the PID still belongs to the expected server before using it to stop anything.
Steam later reported `NoConnection`, and optional backend image upload was
refused. Public reachability and online Steam registration are not established.

## Connections

Expose **28015/UDP** for game traffic and **28017/UDP** for server queries on
the hosting machine, its firewall and any upstream NAT/router. The default
script binds RCON to loopback and omits its password argument, leaving RCON
disabled on a fresh identity. Existing identity configuration can enable it
locally. Do not pass an empty RCON password argument: current Rust bootstrap
fails while masking that empty value for logging. RCON TCP and Rust+
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
