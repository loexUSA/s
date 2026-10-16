#!/usr/bin/env python3
"""Query an actual Rust server via Valve A2S_INFO UDP (stdlib only)."""
import argparse
import json
import socket
import struct
import sys


def query(host, port, timeout):
    request = b'\xff\xff\xff\xffTSource Engine Query\x00'
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.connect((host, port))
        sock.send(request)
        response = sock.recv(65535)
        if response[:5] == b'\xff\xff\xff\xffA':
            if len(response) != 9:
                raise ValueError('Malformed A2S challenge')
            sock.send(request + response[5:9])
            response = sock.recv(65535)
    if response[:5] != b'\xff\xff\xff\xffI':
        raise ValueError('Expected a complete A2S_INFO response')
    offset = 6  # header, response type, protocol byte

    def string():
        nonlocal offset
        end = response.index(0, offset)
        value = response[offset:end].decode('utf-8', errors='replace')
        offset = end + 1
        return value

    name, map_name, folder, game = [string() for _ in range(4)]
    app_id, players, maximum, bots = struct.unpack_from('<HBBB', response, offset)
    if 'rust' not in game.lower() and 'rust' not in folder.lower():
        raise ValueError(f'Responding game is not Rust: {game!r}, {folder!r}')
    return dict(host=host, port=port, name=name, map=map_name, folder=folder,
                game=game, app_id_low16=app_id, players=players, maximum=maximum, bots=bots)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=28017)
    parser.add_argument('--timeout', type=float, default=5)
    args = parser.parse_args()
    try:
        print(json.dumps(query(args.host, args.port, args.timeout), indent=2))
    except (OSError, ValueError, IndexError, struct.error) as exc:
        print(f'Rust server query failed: {exc}', file=sys.stderr)
        sys.exit(1)
