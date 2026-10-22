"""Per-edge sun exposure (PRD 7.5).

Each edge polyline is sampled every EXPOSURE_SAMPLE_M (>= 2 samples, endpoints included). Each
sample is bilinearly interpolated from the sun-fraction raster using only OUTDOOR neighbour cells
(weights renormalised), so walls do not darken pavements next to them. Samples whose cell lies
inside a building footprint (digitising noise, edge not tagged indoor) take the nearest outdoor
cell within 3 m; beyond that they keep the raster value (0 = shade: such a path runs under a
building mass, e.g. an arcade). Edges with cls covered / indoor / ac_link are 0 regardless.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy import ndimage

from zill import config
from zill.shade.heightmap import GridSpec

log = logging.getLogger(__name__)

SHELTERED = {"covered", "indoor", "ac_link"}
NEAREST_OUTDOOR_M = 3.0


@dataclass
class ExposureSampler:
    n_edges: int
    idx: np.ndarray  # int64 [n_samples, 4] flat raster indices
    w: np.ndarray  # float32 [n_samples, 4] weights (rows sum to 1)
    edge_of_sample: np.ndarray  # int64 [n_samples]
    counts: np.ndarray  # float64 [n_edges]
    sheltered: np.ndarray  # bool [n_edges]
    stats: dict[str, int] = field(default_factory=dict)

    def exposure(self, sun_fraction: np.ndarray) -> np.ndarray:
        """float32 [n_edges] in [0, 1] for one uint8 sun-fraction raster."""
        flat = sun_fraction.ravel().astype(np.float32)
        vals = (flat[self.idx] * self.w).sum(axis=1) / 255.0
        sums = np.bincount(self.edge_of_sample, weights=vals, minlength=self.n_edges)
        out = (sums / np.maximum(self.counts, 1)).astype(np.float32)
        out[self.sheltered] = 0.0
        return np.clip(out, 0.0, 1.0)


def _sample_polyline(coords: list[float], step: float) -> np.ndarray:
    pts = np.asarray(coords, np.float64).reshape(-1, 2)
    if len(pts) == 1:
        return np.vstack([pts, pts])
    seg = np.hypot(*np.diff(pts, axis=0).T)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    total = cum[-1]
    n = max(2, int(math.ceil(total / step)) + 1)
    s = np.linspace(0.0, total, n)
    if total <= 0:
        return np.repeat(pts[:1], n, axis=0)
    return np.column_stack([np.interp(s, cum, pts[:, 0]), np.interp(s, cum, pts[:, 1])])


def build_sampler(core: GridSpec, mask: np.ndarray, edges: dict[str, Any],
                  step_m: float = config.EXPOSURE_SAMPLE_M) -> ExposureSampler:
    geoms = edges["geom"]
    n_edges = len(geoms)
    cls = edges.get("cls") or ["open"] * n_edges
    pts_list, eos_list = [], []
    for i, g in enumerate(geoms):
        p = _sample_polyline(g, step_m)
        pts_list.append(p)
        eos_list.append(np.full(len(p), i, np.int64))
    pts = np.vstack(pts_list) if pts_list else np.zeros((0, 2))
    eos = np.concatenate(eos_list) if eos_list else np.zeros(0, np.int64)
    rows, cols = core.shape
    # continuous cell coordinates (integer = cell centre)
    fc = (pts[:, 0] - core.x0) / core.res - 0.5
    fr = (pts[:, 1] - core.z0) / core.res - 0.5
    outside = (fc < -0.5) | (fr < -0.5) | (fc > cols - 0.5) | (fr > rows - 0.5)
    fc = np.clip(fc, 0, cols - 1)
    fr = np.clip(fr, 0, rows - 1)
    c0 = np.clip(np.floor(fc).astype(np.int64), 0, max(cols - 2, 0))
    r0 = np.clip(np.floor(fr).astype(np.int64), 0, max(rows - 2, 0))
    tc = np.clip(fc - c0, 0, 1)
    tr = np.clip(fr - r0, 0, 1)
    rr = np.stack([r0, r0, r0 + 1, r0 + 1], axis=1)
    cc = np.stack([c0, c0 + 1, c0, c0 + 1], axis=1)
    w = np.stack([(1 - tr) * (1 - tc), (1 - tr) * tc, tr * (1 - tc), tr * tc], axis=1)
    inb = mask[rr, cc] != 0
    w = np.where(inb, 0.0, w)
    wsum = w.sum(axis=1)
    # sample's own cell inside a building -> nearest outdoor cell within 3 m
    own_r = np.clip(np.floor(fr + 0.5).astype(np.int64), 0, rows - 1)
    own_c = np.clip(np.floor(fc + 0.5).astype(np.int64), 0, cols - 1)
    own_in = mask[own_r, own_c] != 0
    need = own_in | (wsum <= 1e-9)
    sheltered = np.array([c in SHELTERED for c in cls], bool)
    need_open = need & ~sheltered[eos]
    stats = {"samples": int(len(pts)), "outside_grid": int(outside.sum()),
             "in_building": int(need_open.sum()),
             "snapped_to_outdoor": 0, "left_shaded": 0}
    idx = rr * cols + cc
    if need.any():
        dist, (nr, nc) = ndimage.distance_transform_edt(mask != 0, return_indices=True)
        sel = np.nonzero(need)[0]
        d = dist[own_r[sel], own_c[sel]] * core.res
        ok = d <= NEAREST_OUTDOOR_M
        near = nr[own_r[sel], own_c[sel]] * cols + nc[own_r[sel], own_c[sel]]
        good = sel[ok]
        idx[good] = near[ok][:, None]
        w[good] = np.array([1.0, 0.0, 0.0, 0.0])
        bad = sel[~ok]
        # keep the raw raster value (0 inside buildings): the path runs under a building mass
        idx[bad] = (own_r[bad] * cols + own_c[bad])[:, None]
        w[bad] = np.array([1.0, 0.0, 0.0, 0.0])
        stats["snapped_to_outdoor"] = int((ok & ~sheltered[eos[sel]]).sum())
        stats["left_shaded"] = int((~ok & ~sheltered[eos[sel]]).sum())
    wsum = w.sum(axis=1, keepdims=True)
    w = (w / np.where(wsum > 0, wsum, 1.0)).astype(np.float32)
    counts = np.bincount(eos, minlength=n_edges).astype(np.float64)
    log.info("exposure sampler: %s", stats)
    return ExposureSampler(n_edges, idx, w, eos, counts, sheltered, stats)
