#!/usr/bin/env python3
"""Fetch Valve's current SteamCMD packages over verified HTTPS, checking SHA256.

This prepares official launcher files; it does not disable SteamCMD's normal
updater, claim an installed update state, or download a game server.
"""

import argparse
import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shutil
import ssl
import stat
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile


BASE_URL = "https://steamcdn-a.akamaihd.net/client/"
MANIFEST_URL = BASE_URL + "steam_cmd_linux"
PACKAGES = (
    "steamcmd_public_all", "steamcmd_bins_linux",
    "steamcmd_siteserverui_linux", "steamcmd_linux",
)
MAX_MANIFEST = 1024 * 1024
MAX_PACKAGE = 512 * 1024 * 1024
MAX_EXTRACTED = 1024 * 1024 * 1024


class HTTPSRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme != "https":
            raise ValueError("Refusing a redirect away from HTTPS")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def parse_manifest(raw):
    """Parse Valve's quoted KeyValues format without ignoring unexpected input."""
    source = raw.decode("utf-8")
    tokens = []
    pattern = re.compile(r'\s+|//[^\n]*|"([^"\\]*)"|([{}])')
    position = 0
    while position < len(source):
        match = pattern.match(source, position)
        if match is None:
            raise ValueError("Unsupported or malformed manifest syntax")
        position = match.end()
        if match.group(1) is not None:
            tokens.append(("string", match.group(1)))
        elif match.group(2):
            tokens.append((match.group(2), match.group(2)))
    index = 0

    def object_(nested=False):
        nonlocal index
        result = {}
        while index < len(tokens):
            kind, key = tokens[index]
            index += 1
            if kind == "}" and nested:
                return result
            if kind != "string" or key in result or index >= len(tokens):
                raise ValueError("Malformed or duplicate manifest entry")
            kind, value = tokens[index]
            index += 1
            if kind == "{":
                result[key] = object_(True)
            elif kind == "string":
                result[key] = value
            else:
                raise ValueError("Malformed manifest value")
        if nested:
            raise ValueError("Unclosed manifest object")
        return result

    manifest = object_()
    linux = manifest.get("linux", {})
    if not isinstance(linux, dict) or not str(linux.get("version", "")).isdigit():
        raise ValueError("Manifest does not contain a Linux version")
    packages = []
    for name in PACKAGES:
        entry = linux.get(name, {})
        if not isinstance(entry, dict):
            raise ValueError("Malformed package entry: " + name)
        filename = entry.get("file", "")
        digest = entry.get("sha2", "")
        size = entry.get("size", "")
        if not re.fullmatch(re.escape(name) + r"\.zip\.[0-9a-f]{40}", filename):
            raise ValueError("Unexpected package filename: " + name)
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("Missing package SHA256: " + name)
        if not size.isdigit() or not 0 < int(size) <= MAX_PACKAGE:
            raise ValueError("Invalid package size: " + name)
        packages.append(dict(name=name, file=filename, size=int(size), sha256=digest))
    return linux["version"], packages


def download_package(opener, package, target):
    digest = hashlib.sha256()
    count = 0
    with opener.open(BASE_URL + package["file"], timeout=60) as response:
        with target.open("xb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                count += len(chunk)
                if count > package["size"]:
                    raise ValueError("Package exceeds manifest size: " + package["name"])
                digest.update(chunk)
                output.write(chunk)
    if count != package["size"] or digest.hexdigest() != package["sha256"]:
        raise ValueError("Package SHA256/size verification failed: " + package["name"])
    print("Verified official package: " + package["name"], flush=True)


def extract_packages(packages, downloads, destination):
    total = 0
    files = set()
    for package in packages:
        with zipfile.ZipFile(downloads / package["file"]) as archive:
            for entry in archive.infolist():
                # Valve ZIPs contain some directory entries using backslashes.
                path = PurePosixPath(entry.filename.replace("\\", "/"))
                mode = entry.external_attr >> 16
                if (path.is_absolute() or ".." in path.parts
                        or PureWindowsPath(entry.filename).drive
                        or stat.S_ISLNK(mode)
                        or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR))):
                    raise ValueError("Unsafe archive entry: " + entry.filename)
                if not path.parts:
                    continue
                target = destination.joinpath(*path.parts)
                if entry.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                if path in files:
                    raise ValueError("Duplicate archive file: " + str(path))
                files.add(path)
                total += entry.file_size
                if total > MAX_EXTRACTED:
                    raise ValueError("Packages exceed extracted size limit")
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry) as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output)
                target.chmod(0o644 | (mode & 0o111))
    for name in ("steamcmd.sh", "linux32/steamcmd", "linux64/steamcmd",
                 "linux32/steamerrorreporter", "linux64/steamerrorreporter"):
        target = destination / name
        if target.is_file():
            target.chmod(target.stat().st_mode | 0o100)


def bootstrap(directory):
    directory = directory.absolute()
    if directory.exists() and (not directory.is_dir() or any(directory.iterdir())):
        raise ValueError("Destination must be absent or empty; existing files are preserved")
    directory.parent.mkdir(parents=True, exist_ok=True)
    opener = urllib.request.build_opener(
        HTTPSRedirects(), urllib.request.HTTPSHandler(context=ssl.create_default_context())
    )
    with opener.open(MANIFEST_URL, timeout=60) as response:
        manifest = response.read(MAX_MANIFEST + 1)
    if len(manifest) > MAX_MANIFEST:
        raise ValueError("Manifest exceeds size limit")
    version, packages = parse_manifest(manifest)
    with tempfile.TemporaryDirectory(prefix=".steamcmd-bootstrap-", dir=directory.parent) as temporary:
        temporary = Path(temporary)
        downloads = temporary / "downloads"
        files = temporary / "files"
        downloads.mkdir()
        files.mkdir()
        for package in packages:
            download_package(opener, package, downloads / package["file"])
        extract_packages(packages, downloads, files)
        native64 = files / "linux64/steamcmd"
        if not native64.is_file():
            raise ValueError("Official packages did not contain linux64/steamcmd")
        evidence = files / "bootstrap-evidence"
        evidence.mkdir()
        (evidence / "steam_cmd_linux.manifest").write_bytes(manifest)
        metadata = dict(
            fetched_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            manifest_url=MANIFEST_URL, manifest_sha256=hashlib.sha256(manifest).hexdigest(),
            version=version, packages=packages, native_linux64=True,
            verification="Verified HTTPS plus official manifest SHA256 and size for every package",
            note="Manifest signatures not independently checked. SteamCMD updater remains enabled. "
                 "No installed-state marker was manufactured. This is not RustDedicated.",
        )
        (evidence / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
        if directory.exists():
            directory.rmdir()
        files.rename(directory)
    print("SteamCMD files prepared at: " + str(directory))
    print("Use STEAM_PLATFORM=linux64 with the official steamcmd.sh launcher.")
    print("Evidence: " + str(directory / "bootstrap-evidence/metadata.json"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True,
                        help="An absent or empty runtime directory outside version control")
    args = parser.parse_args()
    try:
        bootstrap(args.directory)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        print("SteamCMD bootstrap failed: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
