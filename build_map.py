"""Build a Rust World v9 terrain/layout draft, using documented SDK serialization.

Requires numpy/scipy and system liblz4. Does not require or distribute game assets.
Prefab IDs are provided separately by prefab_catalog.json with source provenance.
"""
from pathlib import Path
import ctypes
import ctypes.util
import hashlib
import json
import math
import struct

import numpy as np
from scipy.interpolate import CubicSpline
from scipy.ndimage import gaussian_filter1d, map_coordinates
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parent
SIZE, HEIGHT_RES, TEXTURE_RES = 1500, 2049, 1024
RNG = np.random.default_rng(91724)


def varint(n):
    out = bytearray()
    while n > 127:
        out.append((n & 127) | 128)
        n >>= 7
    out.append(n)
    return bytes(out)


def uint(tag, value):
    return varint(tag << 3) + varint(value)


def blob(tag, value):
    if isinstance(value, str):
        value = value.encode()
    return varint((tag << 3) | 2) + varint(len(value)) + value


def real(tag, value):
    return varint((tag << 3) | 5) + struct.pack('<f', value)


def vector(x, y, z):
    return real(1, x) + real(2, y) + real(3, z)


def smooth(low, high, value):
    a = np.clip((value - low) / (high - low), 0, 1)
    return a * a * (3 - 2 * a)


def grid(res):
    return np.meshgrid(np.linspace(-SIZE / 2, SIZE / 2, res),
                       np.linspace(-SIZE / 2, SIZE / 2, res))


X, Z = grid(HEIGHT_RES)
angle = np.arctan2(Z, X)
radius = np.hypot(X / 1.02, Z / 0.98)
coast = (535 + 23 * np.sin(3 * angle + .6) + 17 * np.cos(5 * angle)
         + 11 * np.sin(9 * angle))
shore = coast - radius
land = smooth(-6, 68, shore)
rolling = 12 + 3 * np.sin(X / 91) * np.cos(Z / 83) + 2 * np.sin((X + Z) / 43)
snow_hills = (93 * np.exp(-((X + 270) / 155)**2 - ((Z - 330) / 133)**2)
              + 45 * np.exp(-((X + 410) / 104)**2 - ((Z - 190) / 168)**2))
H = -34 + land * (34 + rolling + snow_hills)
# Shallow sandy shoreline and safe deeper water toward the map border.
H += 3.8 * np.sin(X / 47) * np.sin(Z / 67) * land * (1 - land)

MONUMENTS = [
    dict(key='powerplant', label='Power Plant', x=-25., z=230., y=18., rx=205., rz=155., yaw=0.),
    dict(key='military', label='Abandoned Military Base', x=260., z=-220., y=13., rx=160., rz=145., yaw=0.),
    dict(key='lighthouse', label='Lighthouse', x=-375., z=-335., y=14., rx=48., rz=48., yaw=0.),
    dict(key='oilrig', label='Small Oil Rig', x=645., z=440., y=0., rx=0., rz=0., yaw=0.),
]
DISTANCES = {}
for m in MONUMENTS[:3]:
    # Conservative rectangular terrain pads; actual prefab stamps require RustEdit.
    q = np.maximum(np.abs((X - m['x']) / m['rx']), np.abs((Z - m['z']) / m['rz']))
    blend = 1 - smooth(.9, 1.25, q)
    H = H * (1 - blend) + m['y'] * blend
    DISTANCES[m['key']] = q


def sample_height(x, z):
    ix = (np.asarray(x) / SIZE + .5) * (HEIGHT_RES - 1)
    iz = (np.asarray(z) / SIZE + .5) * (HEIGHT_RES - 1)
    return map_coordinates(H, [np.atleast_1d(iz), np.atleast_1d(ix)], order=1, mode='nearest')


ROAD_GUIDES = [
    [(-347, -320), (-288, -260), (-240, -170), (-220, -65), (-205, 17), (-140, 56), (-85, 67)],
    [(-85, 67), (-12, 39), (72, 12), (146, -15), (220, -45), (260, -63)],
]
roads = []
for guides in ROAD_GUIDES:
    guides = np.asarray(guides, dtype=float)
    steps = np.r_[0, np.cumsum(np.linalg.norm(np.diff(guides, axis=0), axis=1))]
    t = np.linspace(0, steps[-1], int(steps[-1] / 3) + 1)
    xz = CubicSpline(steps, guides, axis=0, bc_type='natural')(t)
    yy = gaussian_filter1d(sample_height(xz[:, 0], xz[:, 1]), 3)
    roads.append(np.column_stack([xz[:, 0], yy, xz[:, 1]]))
all_road_nodes = np.concatenate(roads)
road_tree = cKDTree(all_road_nodes[:, [0, 2]])
road_dist, road_idx = road_tree.query(np.column_stack([X.ravel(), Z.ravel()]))
road_dist = road_dist.reshape(X.shape)
road_y = all_road_nodes[road_idx, 1].reshape(X.shape)
carve = (1 - smooth(4, 11, road_dist))
H = H * (1 - carve) + road_y * carve

TX, TZ = grid(TEXTURE_RES)
TH = sample_height(TX.ravel(), TZ.ravel()).reshape(TX.shape)
td, _ = road_tree.query(np.column_stack([TX.ravel(), TZ.ravel()]))
td = td.reshape(TX.shape)
desert = smooth(25, 220, TX - TZ * .12)
snow = smooth(120, 265, TZ - TX * .26) * (1 - smooth(-40, 100, TX))
temperate = (1 - desert) * (1 - snow)
arctic = snow * (1 - desert)
tundra = 4 * arctic * temperate * .35
weights = np.stack([desert, temperate, tundra, arctic])
weights /= weights.sum(axis=0)


def pack_weights(f):
    """Channel-major uint8 weights, exactly 255 per terrain pixel."""
    f = np.maximum(f, 0)
    f /= np.maximum(f.sum(axis=0), 1e-12)
    b = np.floor(f * 255).astype(np.uint8)
    winner = np.argmax(f, axis=0)
    missing = 255 - b.sum(axis=0, dtype=np.uint16)
    np.put_along_axis(b, winner[None], np.take_along_axis(b, winner[None], axis=0) + missing[None], axis=0)
    return b


biome = pack_weights(weights)
gy, gx = np.gradient(TH, SIZE / (TEXTURE_RES - 1))
slope = np.hypot(gx, gy)
beach = 1 - smooth(1, 8, TH)
rock = smooth(.35, .95, slope)
road = 1 - smooth(3.2, 5.5, td)
splat = np.zeros((8, TEXTURE_RES, TEXTURE_RES))
splat[0] = .06
splat[1] = weights[3]
splat[2] = weights[0] + beach * 3
splat[3] = rock * 2
splat[4] = weights[1] * .68 + weights[2] * .32
splat[5] = weights[1] * .26
splat[6] = .03
splat[7] = .025
for m in MONUMENTS[:2]:
    q = np.maximum(np.abs((TX - m['x']) / m['rx']), np.abs((TZ - m['z']) / m['rz']))
    pad = 1 - smooth(.9, 1.2, q)
    splat[0] += pad * 1.3
    splat[7] += pad * .6
splat *= (1 - road)[None]
splat[7] += road
splat = pack_weights(splat)

topology = np.zeros(TX.shape, dtype='<i4')
ocean = TH < -.2
dry = TH > .2
topology[ocean] |= (1 << 7) | (1 << 18)
topology[(TH > -6) & (TH < 0)] |= 1 << 8
topology[dry] |= (1 << 29) | (1 << 9) | (1 << 24) | (1 << 26)
topology[(TH >= 0) & (TH < 3)] |= 1 << 4
topology[(TH >= 3) & (TH < 7)] |= 1 << 3
forest = dry & (weights[1] > .55) & (TH > 7) & (slope < .55)
topology[forest] |= (1 << 5) | (1 << 6)
topology[dry & ~forest] |= 1 << 0
topology[(slope > .7) & dry] |= 1 << 1
topology[(TH > 65)] |= 1 << 23
topology[(td < 4)] |= 1 << 11
topology[(td >= 4) & (td < 12)] |= 1 << 12
for m in MONUMENTS[:3]:
    q = np.maximum(np.abs((TX - m['x']) / m['rx']), np.abs((TZ - m['z']) / m['rz']))
    area = q < 1.1
    topology[area] = (1 << 10) | (1 << 21) | (1 << 29) | (1 << 28)

catalog = json.loads((ROOT / 'prefab_catalog.json').read_text())
prefabs = []


def add_prefab(entry, category, x, y, z, yaw=0, scale=1):
    prefabs.append(dict(id=int(entry['id']), path=entry['path'], category=category,
                        position=[float(x), float(y), float(z)], rotation=[0., float(yaw), 0.],
                        scale=[float(scale)] * 3))


for m in MONUMENTS:
    add_prefab(catalog['monuments'][m['key']], 'Monument', m['x'], m['y'], m['z'], m['yaw'])

# Authenticated manifest IDs, never invented identifiers. Leave roads and monument pads clear.
decor = catalog.get('decor', {})
for attempt in range(1400):
    x, z = RNG.uniform(-535, 535, 2)
    y = float(sample_height(x, z)[0])
    if y < 5 or y > 95:
        continue
    if any(max(abs((x - m['x']) / (m['rx'] + 12)), abs((z - m['z']) / (m['rz'] + 12))) < 1.25
           for m in MONUMENTS[:3]):
        continue
    if road_tree.query([x, z])[0] < 15:
        continue
    # Keep broad western forest and snow-foothill clearings available for bases.
    if (x + 260)**2 / 100**2 + (z + 130)**2 / 105**2 < 1:
        continue
    region = 'snow' if z - x * .26 > 190 and x < 60 else 'desert' if x - z * .12 > 130 else 'forest'
    options = decor.get(region, [])
    if not options:
        continue
    # Sparse forest, desert palms, and rocks rather than cluttered base terrain.
    if region == 'desert' and RNG.random() > .35:
        continue
    entry = options[int(RNG.integers(len(options)))]
    add_prefab(entry, 'Decor', x, y, z, RNG.uniform(0, 360))

# Initial harvestable stone, metal and sulfur nodes, using native prefab scale.
ore_positions = []
for attempt in range(4000):
    if len(ore_positions) >= 110:
        break
    x, z = RNG.uniform(-510, 510, 2)
    y = float(sample_height(x, z)[0])
    if not 5 < y < 100:
        continue
    if any(max(abs((x - m['x']) / (m['rx'] + 15)), abs((z - m['z']) / (m['rz'] + 15))) < 1.25
           for m in MONUMENTS[:3]):
        continue
    if road_tree.query([x, z])[0] < 13:
        continue
    if any((x - px)**2 + (z - pz)**2 < 27**2 for px, pz in ore_positions):
        continue
    nearby = sample_height(np.array([x - 2, x + 2, x, x]), np.array([z, z, z - 2, z + 2]))
    if np.hypot((nearby[1] - nearby[0]) / 4, (nearby[3] - nearby[2]) / 4) > .4:
        continue
    region = 'snow' if z - x * .26 > 190 and x < 60 else 'desert' if x - z * .12 > 130 else 'forest'
    options = catalog.get('resources', {}).get(region, [])
    if options:
        add_prefab(options[len(ore_positions) % len(options)], 'Decor', x, y, z, RNG.uniform(0, 360))
        ore_positions.append((x, z))


height = np.rint((H + 500) / 1000 * 32766).astype('<i2').tobytes()
water = np.full((HEIGHT_RES, HEIGHT_RES), 16383, dtype='<i2').tobytes()
maps = dict(terrain=height, height=height, water=water,
            splat=splat.tobytes(), biome=biome.tobytes(),
            alpha=np.full((TEXTURE_RES, TEXTURE_RES), 255, dtype=np.uint8).tobytes(),
            topology=topology.tobytes())
world = bytearray(uint(1, SIZE))
for name, data in maps.items():
    world.extend(blob(2, blob(1, name) + blob(2, data)))
for p in prefabs:
    data = blob(1, p['category']) + uint(2, p['id'])
    for tag, key in [(3, 'position'), (4, 'rotation'), (5, 'scale')]:
        data += blob(tag, vector(*p[key]))
    world.extend(blob(3, data))
for i, nodes in enumerate(roads):
    data = blob(1, f'Road {i}') + uint(2, 1) + uint(3, 0) + uint(4, 0)
    for tag, val in [(5, 7), (6, 1), (7, 2), (8, 1), (9, 3), (10, 1), (11, .05), (12, 0)]:
        data += real(tag, val)
    data += uint(13, 1 << 7) + uint(14, 1 << 11)
    for x, y, z in nodes:
        data += blob(15, vector(x, y, z))
    world.extend(blob(4, data))

# Legacy LZ4Stream block envelope used by Facepunch's SDK, not LZ4 frame format.
lz4 = ctypes.CDLL(ctypes.util.find_library('lz4'))
lz4.LZ4_compressBound.argtypes = [ctypes.c_int]
lz4.LZ4_compressBound.restype = ctypes.c_int
lz4.LZ4_compress_default.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
lz4.LZ4_compress_default.restype = ctypes.c_int
out = bytearray(struct.pack('<I', 9))
for start in range(0, len(world), 1 << 20):
    data = bytes(world[start:start + (1 << 20)])
    target = ctypes.create_string_buffer(lz4.LZ4_compressBound(len(data)))
    count = lz4.LZ4_compress_default(data, target, len(data), len(target))
    if 0 < count < len(data):
        out.extend(varint(1) + varint(len(data)) + varint(count) + target.raw[:count])
    else:
        out.extend(varint(0) + varint(len(data)) + data)
target = ROOT / 'onegrid_mixed_draft.map'
target.write_bytes(out)
manifest = dict(filename=target.name, format_version=9, world_size_metres=SIZE,
                height_resolution=HEIGHT_RES, texture_resolution=TEXTURE_RES,
                prefab_count=len(prefabs), prefabs=prefabs, monuments=MONUMENTS,
                road_count=len(roads), initial_ore_nodes=len(ore_positions),
                layer_bytes={k: len(v) for k, v in maps.items()},
                sha256=hashlib.sha256(out).hexdigest(),
                status='Draft: structurally checked; not loaded in RustEdit or RustDedicated',
                limitations=['1500m world: not a literal single grid',
                             'Monument terrain stamps, entry heights, puzzles, loot, AI and spawns need in-game validation',
                             'No RustEdit extension IO metadata, navmesh or server runtime verification'])
(ROOT / 'map_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps({k: v for k, v in manifest.items() if k not in ('prefabs', 'monuments')}, indent=2))
