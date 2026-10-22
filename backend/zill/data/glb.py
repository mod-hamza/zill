"""Flat-roof building extrusions -> buildings.glb (CONTRACTS 3).

One mesh node per 250 m tile (``tile_<i>_<j>``), Y-up local metres, holes handled via earcut.
Vertex attributes: POSITION, NORMAL, _BUILDING_ID (float), _HEIGHT (float). Floors are skipped.
"""

from __future__ import annotations

import json
import math
import struct
from collections import defaultdict
from pathlib import Path
from typing import Any

import mapbox_earcut as earcut
import numpy as np
import shapely
from shapely.geometry import Polygon

TILE_M = 250.0


def _ring_arrays(poly: Polygon) -> tuple[np.ndarray, list[np.ndarray]]:
    p = shapely.geometry.polygon.orient(poly, sign=1.0)  # exterior CCW (x,z math sense), holes CW
    ext = np.asarray(p.exterior.coords)[:-1]
    holes = [np.asarray(r.coords)[:-1] for r in p.interiors]
    return ext, holes


def extrude(poly: Polygon, y0: float, y1: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (positions [n,3], normals [n,3], indices [m]) for walls + roof of one footprint."""
    ext, holes = _ring_arrays(poly)
    pos: list[np.ndarray] = []
    nor: list[np.ndarray] = []
    idx: list[np.ndarray] = []
    base = 0
    for ring in [ext, *holes]:
        q = np.roll(ring, -1, axis=0)
        d = q - ring
        ln = np.hypot(d[:, 0], d[:, 1])
        ok = ln > 1e-6
        p_, q_, d_, ln_ = ring[ok], q[ok], d[ok], ln[ok]
        k = len(p_)
        if k == 0:
            continue
        n = np.column_stack([d_[:, 1] / ln_, np.zeros(k), -d_[:, 0] / ln_])
        pb = np.column_stack([p_[:, 0], np.full(k, y0), p_[:, 1]])
        qb = np.column_stack([q_[:, 0], np.full(k, y0), q_[:, 1]])
        qt = np.column_stack([q_[:, 0], np.full(k, y1), q_[:, 1]])
        pt = np.column_stack([p_[:, 0], np.full(k, y1), p_[:, 1]])
        v = np.stack([pb, qb, qt, pt], axis=1).reshape(-1, 3)
        pos.append(v)
        nor.append(np.repeat(n, 4, axis=0))
        b = base + np.arange(k)[:, None] * 4
        tri = np.concatenate([b + [0, 2, 1], b + [0, 3, 2]], axis=1).reshape(-1)
        idx.append(tri)
        base += 4 * k
    # roof
    rings = [ext, *holes]
    verts2d = np.concatenate(rings, axis=0)
    ends = np.cumsum([len(r) for r in rings]).astype(np.uint32)
    tri = np.asarray(earcut.triangulate_float64(verts2d.astype(np.float64), ends), dtype=np.int64)
    if len(tri):
        t = tri.reshape(-1, 3)
        a, b_, c = verts2d[t[:, 0]], verts2d[t[:, 1]], verts2d[t[:, 2]]
        # y component of (b-a)x(c-a) in 3D with (x,y,z)=(x,const,z) is -(cross2d in x,z)
        cross2d = (b_[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b_[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
        flip = cross2d > 0
        t[flip] = t[flip][:, [0, 2, 1]]
        roof = np.column_stack([verts2d[:, 0], np.full(len(verts2d), y1), verts2d[:, 1]])
        pos.append(roof)
        nor.append(np.tile([0.0, 1.0, 0.0], (len(roof), 1)))
        idx.append(t.reshape(-1) + base)
    if not pos:
        return np.zeros((0, 3)), np.zeros((0, 3)), np.zeros(0, dtype=np.int64)
    return np.concatenate(pos), np.concatenate(nor), np.concatenate(idx)


def write_glb(buildings: list[Any], path: Path, origin_xz: tuple[float, float]) -> dict[str, Any]:
    """buildings: objects with .id .poly .height .min_height .in_scene. Returns a report dict."""
    tiles: dict[tuple[int, int], list[Any]] = defaultdict(list)
    x0, z0 = origin_xz
    for b in buildings:
        if not b.in_scene:
            continue
        rp = b.poly.representative_point()
        tiles[(int(math.floor((rp.x - x0) / TILE_M)), int(math.floor((rp.y - z0) / TILE_M)))].append(b)
    blob = bytearray()
    buffer_views: list[dict[str, Any]] = []
    accessors: list[dict[str, Any]] = []
    meshes: list[dict[str, Any]] = []
    nodes: list[dict[str, Any]] = []
    report_tiles = []

    def add_view(arr: np.ndarray, target: int) -> int:
        while len(blob) % 4:
            blob.append(0)
        off = len(blob)
        data = arr.tobytes()
        blob.extend(data)
        buffer_views.append({"buffer": 0, "byteOffset": off, "byteLength": len(data), "target": target})
        return len(buffer_views) - 1

    def add_acc(arr: np.ndarray, comp: int, typ: str, target: int, minmax: bool = False) -> int:
        bv = add_view(arr, target)
        acc: dict[str, Any] = {
            "bufferView": bv,
            "componentType": comp,
            "count": int(arr.shape[0]),
            "type": typ,
        }
        if minmax:
            acc["min"] = [float(v) for v in arr.min(axis=0)]
            acc["max"] = [float(v) for v in arr.max(axis=0)]
        accessors.append(acc)
        return len(accessors) - 1

    for i, j in sorted(tiles):
        P, N, B, H, IDX = [], [], [], [], []
        base = 0
        for b in tiles[(i, j)]:
            y0 = float(b.min_height)
            y1 = float(max(b.height, y0 + 0.5))
            p, n, ix = extrude(b.poly, y0, y1)
            if len(p) == 0:
                continue
            P.append(p)
            N.append(n)
            B.append(np.full(len(p), float(b.id)))
            H.append(np.full(len(p), y1))
            IDX.append(ix + base)
            base += len(p)
        if not P:
            continue
        pos = np.concatenate(P).astype(np.float32)
        nor = np.concatenate(N).astype(np.float32)
        bid = np.concatenate(B).astype(np.float32)
        hgt = np.concatenate(H).astype(np.float32)
        ind = np.concatenate(IDX).astype(np.uint32)
        attrs = {
            "POSITION": add_acc(pos, 5126, "VEC3", 34962, minmax=True),
            "NORMAL": add_acc(nor, 5126, "VEC3", 34962),
            "_BUILDING_ID": add_acc(bid, 5126, "SCALAR", 34962),
            "_HEIGHT": add_acc(hgt, 5126, "SCALAR", 34962),
        }
        ia = add_acc(ind, 5125, "SCALAR", 34963)
        meshes.append(
            {"name": f"tile_{i}_{j}", "primitives": [{"attributes": attrs, "indices": ia, "material": 0}]}
        )
        nodes.append({"name": f"tile_{i}_{j}", "mesh": len(meshes) - 1})
        report_tiles.append(
            {
                "name": f"tile_{i}_{j}",
                "buildings": len(tiles[(i, j)]),
                "vertices": int(len(pos)),
                "triangles": int(len(ind) // 3),
                "bounds": [
                    [round(float(v), 2) for v in pos.min(axis=0)],
                    [round(float(v), 2) for v in pos.max(axis=0)],
                ],
            }
        )
    while len(blob) % 4:
        blob.append(0)
    gltf = {
        "asset": {"version": "2.0", "generator": "zill.data.glb"},
        "scene": 0,
        "scenes": [{"nodes": list(range(len(nodes)))}],
        "nodes": nodes,
        "meshes": meshes,
        "materials": [
            {
                "name": "building",
                "pbrMetallicRoughness": {
                    "baseColorFactor": [0.93, 0.89, 0.82, 1.0],
                    "metallicFactor": 0.0,
                    "roughnessFactor": 0.9,
                },
            }
        ],
        "accessors": accessors,
        "bufferViews": buffer_views,
        "buffers": [{"byteLength": len(blob)}],
    }
    js = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    js += b" " * ((4 - len(js) % 4) % 4)
    total = 12 + 8 + len(js) + 8 + len(blob)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, total))
        f.write(struct.pack("<II", len(js), 0x4E4F534A))
        f.write(js)
        f.write(struct.pack("<II", len(blob), 0x004E4942))
        f.write(bytes(blob))
    return {
        "tiles": len(nodes),
        "tile_size_m": TILE_M,
        "vertices": sum(t["vertices"] for t in report_tiles),
        "triangles": sum(t["triangles"] for t in report_tiles),
        "bytes": total,
        "tile_list": report_tiles,
    }


def verify_glb(path: Path) -> dict[str, Any]:
    """Round-trip load with trimesh; returns counts and bounds."""
    import trimesh

    sc = trimesh.load(str(path), force="scene")
    geoms = list(sc.geometry.values())
    v = sum(len(g.vertices) for g in geoms)
    f = sum(len(g.faces) for g in geoms)
    b = sc.bounds
    return {
        "loaded": True,
        "geometries": len(geoms),
        "vertices": int(v),
        "faces": int(f),
        "bounds": [[round(float(x), 2) for x in b[0]], [round(float(x), 2) for x in b[1]]],
    }
