"""Caster heightmap rasterisation (PRD 7.2, CONTRACTS 2).

Grid convention (BOTH grids): array shape [rows, cols]; row 0 = north edge (min z), col 0 = west
edge (min x). Cell (r, c) centre: x = x0 + (c + 0.5)*res, z = z0 + (r + 0.5)*res.

Rasterisation samples cell centres (even-odd rule across all rings, so holes are handled).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from numba import njit
from scipy import ndimage

from zill import config

NO_BUILDING = -1
HMIN_EMPTY = np.float32(1e9)
_H0 = float(config.H0)  # numba-visible constant
SKIP_RADII = (6, 40)  # cells; max-filter levels used by the raymarcher to skip empty space


@dataclass(frozen=True)
class GridSpec:
    x0: float
    z0: float
    rows: int
    cols: int
    res: float = config.GRID_RES_M

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> GridSpec:
        return cls(float(d["x0"]), float(d["z0"]), int(d["rows"]), int(d["cols"]), float(d.get("res_m", 2.0)))

    def to_dict(self) -> dict[str, Any]:
        return {"x0": self.x0, "z0": self.z0, "rows": self.rows, "cols": self.cols, "res_m": self.res}

    @classmethod
    def covering(cls, xmin: float, zmin: float, xmax: float, zmax: float, res: float = config.GRID_RES_M):
        cols = int(math.ceil((xmax - xmin) / res))
        rows = int(math.ceil((zmax - zmin) / res))
        return cls(float(xmin), float(zmin), rows, cols, res)

    def cell_centre(self, r: int | np.ndarray, c: int | np.ndarray):
        return self.x0 + (np.asarray(c) + 0.5) * self.res, self.z0 + (np.asarray(r) + 0.5) * self.res

    def cell_of(self, x: float | np.ndarray, z: float | np.ndarray):
        """(row, col) integer cell containing local point(s) (x, z) (may be out of range)."""
        c = np.floor((np.asarray(x) - self.x0) / self.res).astype(np.int64)
        r = np.floor((np.asarray(z) - self.z0) / self.res).astype(np.int64)
        return r, c

    @property
    def shape(self) -> tuple[int, int]:
        return (self.rows, self.cols)


@dataclass
class CasterGrid:
    spec: GridSpec
    hmax: np.ndarray  # float32 top of building mass per cell (0 = empty)
    hmin: np.ndarray  # float32 bottom of building mass (HMIN_EMPTY if empty)
    bid: np.ndarray  # int32 id of tallest building covering the cell, -1 if none
    canopy_top: np.ndarray  # float32
    canopy_bottom: np.ndarray  # float32
    canopy_block: np.ndarray  # float32 in [0, TREE_BLOCK]
    tree_id: np.ndarray  # int32, -1 if none
    skip: list[np.ndarray] = field(default_factory=list)  # max-filtered obstacle tops per SKIP_RADII
    max_height: float = 0.0

    def finalize(self) -> CasterGrid:
        top = np.maximum(self.hmax, self.canopy_top).astype(np.float32)
        self.skip = [ndimage.maximum_filter(top, size=2 * r + 1, mode="nearest") for r in SKIP_RADII]
        self.max_height = float(top.max()) if top.size else 0.0
        return self


# ------------------------------------------------------------------------------------------------
# polygon scanline fill (cell-centre sampling, even-odd)
# ------------------------------------------------------------------------------------------------
@njit(cache=True)
def _poly_spans(vx, vz, ring_off, r0_ring, r1_ring, x0, z0, res, rows, cols, out_r, out_c0, out_c1):
    """Write (row, c0, c1) half-open spans of cells whose centres lie inside the polygon. Returns count."""
    zmin = 1e30
    zmax = -1e30
    for ri in range(r0_ring, r1_ring):
        for i in range(ring_off[ri], ring_off[ri + 1]):
            if vz[i] < zmin:
                zmin = vz[i]
            if vz[i] > zmax:
                zmax = vz[i]
    ra = max(0, int(math.floor((zmin - z0) / res - 0.5)))
    rb = min(rows - 1, int(math.ceil((zmax - z0) / res - 0.5)))
    n = 0
    xs = np.empty(256, dtype=np.float64)
    for r in range(ra, rb + 1):
        zc = z0 + (r + 0.5) * res
        k = 0
        for ri in range(r0_ring, r1_ring):
            s = ring_off[ri]
            e = ring_off[ri + 1]
            m = e - s
            for j in range(m):
                ax = vx[s + j]
                az = vz[s + j]
                bx = vx[s + (j + 1) % m]
                bz = vz[s + (j + 1) % m]
                if (az <= zc < bz) or (bz <= zc < az):
                    if k >= xs.shape[0]:
                        nxs = np.empty(xs.shape[0] * 2, dtype=np.float64)
                        nxs[: xs.shape[0]] = xs
                        xs = nxs
                    xs[k] = ax + (zc - az) * (bx - ax) / (bz - az)
                    k += 1
        if k < 2:
            continue
        sx = np.sort(xs[:k])
        for p in range(0, k - 1, 2):
            # cells whose centre x0 + (c+0.5)res lies in [sx[p], sx[p+1])
            c0 = int(math.ceil((sx[p] - x0) / res - 0.5))
            c1 = int(math.ceil((sx[p + 1] - x0) / res - 0.5))
            if c0 < 0:
                c0 = 0
            if c1 > cols:
                c1 = cols
            if c1 > c0:
                if n >= out_r.shape[0]:
                    return -1
                out_r[n] = r
                out_c0[n] = c0
                out_c1[n] = c1
                n += 1
    return n


@njit(cache=True)
def _rasterise_buildings(vx, vz, ring_off, poly_ring_off, heights, min_heights, ids,
                         x0, z0, res, hmax, hmin, bid, ground_only, mask):
    rows, cols = hmax.shape
    cap = 1 << 16
    out_r = np.empty(cap, dtype=np.int64)
    out_c0 = np.empty(cap, dtype=np.int64)
    out_c1 = np.empty(cap, dtype=np.int64)
    for p in range(heights.shape[0]):
        n = _poly_spans(vx, vz, ring_off, poly_ring_off[p], poly_ring_off[p + 1], x0, z0, res, rows, cols,
                        out_r, out_c0, out_c1)
        while n < 0:
            cap *= 2
            out_r = np.empty(cap, dtype=np.int64)
            out_c0 = np.empty(cap, dtype=np.int64)
            out_c1 = np.empty(cap, dtype=np.int64)
            n = _poly_spans(vx, vz, ring_off, poly_ring_off[p], poly_ring_off[p + 1], x0, z0, res, rows,
                            cols, out_r, out_c0, out_c1)
        h = heights[p]
        mh = min_heights[p]
        for q in range(n):
            r = out_r[q]
            for c in range(out_c0[q], out_c1[q]):
                if ground_only:
                    if mh <= _H0:
                        mask[r, c] = 255
                    continue
                if h > hmax[r, c]:
                    hmax[r, c] = h
                    bid[r, c] = ids[p]
                if mh < hmin[r, c]:
                    hmin[r, c] = mh



@njit(cache=True)
def _rasterise_trees(tx, tz, tr, th, block, x0, z0, res, top, bottom, blk, tid):
    rows, cols = top.shape
    for i in range(tx.shape[0]):
        r = tr[i]
        ca = max(0, int(math.floor((tx[i] - r - x0) / res)))
        cb = min(cols - 1, int(math.ceil((tx[i] + r - x0) / res)))
        ra = max(0, int(math.floor((tz[i] - r - z0) / res)))
        rb = min(rows - 1, int(math.ceil((tz[i] + r - z0) / res)))
        hb = th[i] * 0.35
        for rr in range(ra, rb + 1):
            zc = z0 + (rr + 0.5) * res
            for cc in range(ca, cb + 1):
                xc = x0 + (cc + 0.5) * res
                if (xc - tx[i]) ** 2 + (zc - tz[i]) ** 2 <= r * r:
                    if th[i] > top[rr, cc]:
                        top[rr, cc] = th[i]
                    if bottom[rr, cc] == 0.0 or hb < bottom[rr, cc]:
                        bottom[rr, cc] = hb
                    if block > blk[rr, cc]:
                        blk[rr, cc] = block
                    tid[rr, cc] = i


# ------------------------------------------------------------------------------------------------
def _flatten(buildings: list[dict[str, Any]]):
    vx: list[float] = []
    vz: list[float] = []
    ring_off = [0]
    poly_ring_off = [0]
    heights, mins, ids = [], [], []
    for b in buildings:
        rings = [b["footprint"], *(b.get("holes") or [])]
        for ring in rings:
            if len(ring) < 3:
                continue
            for x, z in ring:
                vx.append(float(x))
                vz.append(float(z))
            ring_off.append(len(vx))
        poly_ring_off.append(len(ring_off) - 1)
        heights.append(float(b["height"]))
        mins.append(float(b.get("min_height") or 0.0))
        ids.append(int(b["id"]))
    return (
        np.asarray(vx, np.float64), np.asarray(vz, np.float64), np.asarray(ring_off, np.int64),
        np.asarray(poly_ring_off, np.int64), np.asarray(heights, np.float32),
        np.asarray(mins, np.float32), np.asarray(ids, np.int32),
    )


def build_caster(spec: GridSpec, buildings: list[dict[str, Any]], trees: list[dict[str, Any]] | None = None
                 ) -> CasterGrid:
    shape = spec.shape
    hmax = np.zeros(shape, np.float32)
    hmin = np.full(shape, HMIN_EMPTY, np.float32)
    bid = np.full(shape, NO_BUILDING, np.int32)
    mask_dummy = np.zeros((1, 1), np.uint8)
    if buildings:
        vx, vz, ro, pro, hs, ms, ids = _flatten(buildings)
        _rasterise_buildings(vx, vz, ro, pro, hs, ms, ids, spec.x0, spec.z0, spec.res, hmax, hmin, bid,
                             False, mask_dummy)
    top = np.zeros(shape, np.float32)
    bottom = np.zeros(shape, np.float32)
    blk = np.zeros(shape, np.float32)
    tid = np.full(shape, -1, np.int32)
    if trees:
        tx = np.asarray([t["x"] for t in trees], np.float64)
        tz = np.asarray([t["z"] for t in trees], np.float64)
        tr = np.asarray([t.get("r") or config.TREE_RADIUS_M for t in trees], np.float64)
        th = np.asarray([t.get("h") or config.TREE_HEIGHT_M for t in trees], np.float64)
        _rasterise_trees(tx, tz, tr, th, np.float32(config.TREE_BLOCK), spec.x0, spec.z0, spec.res,
                         top, bottom, blk, tid)
    return CasterGrid(spec, hmax, hmin, bid, top, bottom, blk, tid).finalize()


def building_mask(spec: GridSpec, buildings: list[dict[str, Any]]) -> np.ndarray:
    """uint8 mask (255 = inside a ground-touching building, not walkable) on `spec`."""
    mask = np.zeros(spec.shape, np.uint8)
    if buildings:
        vx, vz, ro, pro, hs, ms, ids = _flatten(buildings)
        dummy_f = np.zeros((1, 1), np.float32)
        dummy_i = np.zeros((1, 1), np.int32)
        # ground_only=True: only `mask` is written; pass real shape via a zero array of spec size
        hm = np.zeros(spec.shape, np.float32)
        _rasterise_buildings(vx, vz, ro, pro, hs, ms, ids, spec.x0, spec.z0, spec.res, hm, dummy_f,
                             dummy_i, True, mask)
    return mask


def load_city_inputs(city_dir: Path) -> dict[str, Any]:
    meta = json.loads((city_dir / "meta.json").read_text(encoding="utf-8"))
    buildings = json.loads((city_dir / "buildings.json").read_text(encoding="utf-8"))["buildings"]
    trees_p = city_dir / "trees.json"
    trees = json.loads(trees_p.read_text(encoding="utf-8"))["trees"] if trees_p.exists() else []
    return {"meta": meta, "buildings": buildings, "trees": trees}
