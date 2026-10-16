#!/usr/bin/env python3
"""Independent structural verifier for Rust World v9 .map files.

Schema: Facepunch/Rust.World Assets/Plugins/Rust.Data/ProtoBuf.cs.
Stream: MiloszKrajewski/lz4net src/LZ4/LZ4Stream.cs legacy chunks.
Does not verify runtime monument assets, collisions, puzzles, or NPC navigation.
"""
import ctypes
import ctypes.util
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

import numpy as np


def varint(data, p):
    value = 0
    for shift in range(0, 70, 7):
        assert p < len(data), 'Truncated varint'
        b = data[p]
        p += 1
        value |= (b & 0x7f) << shift
        if b < 128:
            return value, p
    raise AssertionError('Varint exceeds 64 bits')


def fields(data):
    result = {}
    p = 0
    while p < len(data):
        key, p = varint(data, p)
        number, wire = key >> 3, key & 7
        assert number > 0, 'Invalid field number'
        if wire == 0:
            value, p = varint(data, p)
        elif wire == 2:
            length, p = varint(data, p)
            end = p + length
            assert end <= len(data), 'Truncated length-delimited field'
            value = data[p:end]
            p = end
        elif wire in (1, 5):
            end = p + (8 if wire == 1 else 4)
            assert end <= len(data), 'Truncated fixed-width field'
            value = data[p:end]
            p = end
        else:
            raise AssertionError(f'Unsupported wire type {wire}')
        result.setdefault(number, []).append((wire, value))
    return result


def one(f, n, wire, default=None):
    if n not in f:
        return default
    assert len(f[n]) == 1 and f[n][0][0] == wire, f'Bad field {n}'
    return f[n][0][1]


def repeated(f, n):
    result = []
    for wire, val in f.get(n, []):
        assert wire == 2, f'Wrong message wire type {wire}'
        result.append(fields(val))
    return result


def vector(f):
    result = []
    for n in (1, 2, 3):
        raw = one(f, n, 5)
        result.append(0.0 if raw is None else struct.unpack('<f', raw)[0])
    assert all(math.isfinite(v) for v in result), 'Nonfinite vector component'
    return result


def legacy_stream(data):
    p = 4
    blocks = []
    raw_count = compressed_count = 0
    lib = None
    while p < len(data):
        flags, p = varint(data, p)
        length, p = varint(data, p)
        assert flags < 4, 'Unsupported multiple compression passes'
        assert 0 < length <= 1024 ** 3, 'Invalid chunk size'
        packed = bool(flags & 1)
        stored = length
        if packed:
            stored, p = varint(data, p)
            assert 0 < stored <= length, 'Invalid compressed size'
        end = p + stored
        assert end <= len(data), 'Truncated compressed chunk'
        block = data[p:end]
        p = end
        if packed:
            if lib is None:
                lib = ctypes.CDLL(ctypes.util.find_library('lz4') or 'liblz4.so.1')
                lib.LZ4_decompress_safe.argtypes = [ctypes.c_char_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
                lib.LZ4_decompress_safe.restype = ctypes.c_int
            output = ctypes.create_string_buffer(length)
            actual = lib.LZ4_decompress_safe(block, output, len(block), length)
            assert actual == length, f'LZ4 decode size mismatch: {actual} != {length}'
            block = output.raw
            compressed_count += 1
        else:
            raw_count += 1
        blocks.append(block)
    return b''.join(blocks), {'raw': raw_count, 'compressed': compressed_count}


def dimension(data, dtype, channels):
    values = np.frombuffer(data, dtype=dtype)
    assert values.size % channels == 0, 'Invalid channel count'
    res = math.isqrt(values.size // channels)
    assert res * res * channels == values.size, 'Nonsquare layer'
    return res, values.reshape(channels, res, res)


def verify(path):
    content = path.read_bytes()
    assert len(content) > 6, 'Empty map file'
    version = struct.unpack_from('<I', content)[0]
    assert version == 9, f'Unsupported map version {version}'
    payload, chunks = legacy_stream(content)
    world = fields(payload)
    size = one(world, 1, 0)
    assert size and 100 <= size <= 100000, 'Invalid world size'
    maps = {}
    for f in repeated(world, 2):
        name = one(f, 1, 2).decode('utf-8')
        assert name not in maps, f'Duplicate map layer {name}'
        maps[name] = one(f, 2, 2)
    required = {'terrain', 'height', 'water', 'splat', 'biome', 'alpha', 'topology'}
    assert required <= set(maps), f'Missing layers {required - set(maps)}'
    assert maps['terrain'] == maps['height'], 'terrain and height layers differ'
    schema = {'terrain': ('<i2', 1), 'height': ('<i2', 1), 'water': ('<i2', 1),
              'splat': ('u1', 8), 'biome': ('u1', 4), 'alpha': ('u1', 1), 'topology': ('<u4', 1)}
    decoded = {}
    dims = {}
    for name, (dtype, channels) in schema.items():
        dims[name], decoded[name] = dimension(maps[name], dtype, channels)
    assert dims['terrain'] == dims['height'] == dims['water'], 'Height resolutions differ'
    assert len({dims[n] for n in ('splat', 'biome', 'alpha', 'topology')}) == 1, 'Texture resolutions differ'
    res = dims['height']
    assert res > 2 and (res - 1) & (res - 2) == 0, 'Height resolution must be power of two plus one'
    res = dims['splat']
    assert res > 1 and res & (res - 1) == 0, 'Texture resolution must be power of two'
    assert decoded['height'].min() >= 0, 'Invalid negative height encoding'
    assert decoded['water'].min() >= 0, 'Invalid negative water encoding'
    for name in ('splat', 'biome'):
        sums = decoded[name].sum(axis=0)
        assert np.all(sums == 255), f'{name} weights do not sum to 255 in {np.count_nonzero(sums != 255)} pixels'
    assert set(np.unique(decoded['alpha'])).issubset({0, 255}), 'Nonbinary alpha layer'
    physical_height = decoded['height'].astype(float) / 32766 * 1000 - 500
    physical_water = decoded['water'].astype(float) / 32766 * 1000 - 500
    assert np.any(physical_height > physical_water), 'No land above water'
    assert np.any(physical_height < physical_water), 'No ocean below water'
    prefabs = []
    for f in repeated(world, 3):
        category = one(f, 1, 2, b'').decode('utf-8')
        prefab_id = one(f, 2, 0, 0)
        assert 0 < prefab_id < 2 ** 32, f'Invalid prefab id {prefab_id}'
        position = vector(fields(one(f, 3, 2, b'')))
        rotation = vector(fields(one(f, 4, 2, b'')))
        scale = vector(fields(one(f, 5, 2, b'')))
        assert all(v > 0 for v in scale), f'Invalid prefab scale {scale}'
        prefabs.append({'category': category, 'id': prefab_id, 'position': position, 'rotation': rotation, 'scale': scale})
    paths = []
    for f in repeated(world, 4):
        name = one(f, 1, 2, b'').decode('utf-8')
        nodes = [vector(n) for n in repeated(f, 15)]
        assert len(nodes) >= 2, f'Path {name} has fewer than two nodes'
        paths.append({'name': name, 'node_count': len(nodes), 'first_node': nodes[0], 'last_node': nodes[-1]})
    top = decoded['topology'][0]
    return {'file': str(path), 'sha256': hashlib.sha256(content).hexdigest(), 'size_bytes': len(content),
            'version': version, 'world_size_meters': size, 'protobuf_bytes': len(payload), 'stream_chunks': chunks,
            'layer_resolutions': dims, 'height_range_meters': [float(physical_height.min()), float(physical_height.max())],
            'water_range_meters': [float(physical_water.min()), float(physical_water.max())],
            'above_water_fraction': float(np.mean(physical_height > physical_water)),
            'biome_weight_sums': decoded['biome'].sum(axis=(1, 2)).tolist(),
            'ocean_topology_pixels': int(np.count_nonzero(top & (1 << 7))),
            'monument_topology_pixels': int(np.count_nonzero(top & (1 << 10))),
            'prefab_count': len(prefabs), 'prefabs': prefabs, 'paths': paths,
            'verified': 'v9 framing, LZ4 decoding, protobuf structure, layer dimensions and weights, height/water, prefab transforms, paths',
            'not_verified': 'RustEdit/server loading, installed-game asset compatibility, monument terrain stamps, collisions, loot/puzzles, navigation'}


if __name__ == '__main__':
    assert len(sys.argv) == 2, 'Usage: verify_rust_map.py MAP_PATH'
    print(json.dumps(verify(Path(sys.argv[1])), indent=2))
