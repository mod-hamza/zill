"""Shadow raymarch (PRD 7.3), numba-parallel.

For every core-grid cell, march from the pedestrian (h0 = PED_H above ground) TOWARD the sun.
Horizontal direction in grid space: col += sin(az), row += -cos(az) (row grows southward, +z).
Step = one cell (GRID_RES_M). Buildings block fully; tree canopies multiply transmission by
(1 - block) once per distinct tree crossed. Empty space is skipped using max-filtered height
grids (safe because the ray height only increases along the march).

Soft, anti-aliased edges: the sun disc (0.53 deg) is sampled at its centre plus 4 points on its rim;
each rim sample also starts its ray from a sub-cell offset (+/-0.35 cell in the sun-aligned frame),
which supersamples the cell footprint. The transmissions are averaged. Offsets are defined relative
to the sun direction so the raster stays exactly equivariant under 90-degree scene rotations.
"""

from __future__ import annotations

import math

import numpy as np
from numba import njit, prange

from zill import config
from zill.shade.heightmap import SKIP_RADII, CasterGrid, GridSpec

DISC_SAMPLES = 5
JITTER_CELLS = 0.5  # rim samples' ray origins sit on a circle of this radius (cells), sun-aligned


def disc_samples(alt_deg: float, az_deg: float, n: int = DISC_SAMPLES
                 ) -> list[tuple[float, float, float, float]]:
    """(alt, az, origin_perp, origin_along) samples: disc centre + n-1 rim points of the sun disc."""
    out = [(alt_deg, az_deg, 0.0, 0.0)]
    rad = config.SUN_DISC_DEG / 2.0
    cos_alt = max(math.cos(math.radians(alt_deg)), 1e-3)
    for i in range(n - 1):
        th = 2 * math.pi * i / (n - 1) + math.pi / 4
        op = round(JITTER_CELLS * math.cos(th), 9)
        oa = round(JITTER_CELLS * math.sin(th), 9)
        a = alt_deg + rad * math.sin(th)
        z = az_deg + rad * math.cos(th) / cos_alt
        if a > 90.0:  # sample past the zenith -> reflect to the other side
            a, z = 180.0 - a, z + 180.0
        out.append((a, z % 360.0, op, oa))
    return out


@njit(cache=True, fastmath=True, nogil=True)
def _march(ri0, ci0, fr, fc, drow, dcol, tan_alt, res, h0, max_steps, scene_max,
           hmax, hmin, top, bottom, blk, tid, skip1, skip2, R1, R2):
    """Transmission (0..1) of direct sun reaching a pedestrian at caster cell (ri0, ci0) + (fr, fc)."""
    rows, cols = hmax.shape
    trans = 1.0
    last_tree = -1
    half = 0.5 * res * tan_alt
    k = 0
    while k <= max_steps:
        # round the offset half-away-from-zero so that ties (e.g. az = 120 deg, cos = -0.5) break
        # symmetrically and the raster is exactly equivariant under 90-degree scene rotations
        orow = fr + k * drow
        ocol = fc + k * dcol
        r = ri0 + (int(math.floor(orow + 0.5)) if orow >= 0 else -int(math.floor(-orow + 0.5)))
        c = ci0 + (int(math.floor(ocol + 0.5)) if ocol >= 0 else -int(math.floor(-ocol + 0.5)))
        if r < 0 or c < 0 or r >= rows or c >= cols:
            break
        hc = h0 + k * res * tan_alt
        h_lo = hc - half if k > 0 else h0
        if h_lo > scene_max:
            break
        # empty-space skipping (the ray only climbs, so anything below h_lo is irrelevant)
        if h_lo > skip2[r, c] and k > 0:
            k += R2 - 1
            continue
        if h_lo > skip1[r, c] and k > 0:
            k += R1 - 1
            continue
        hm = hmax[r, c]
        if hm > 0.0:
            hb = hmin[r, c]
            if hb <= h0:
                if hm > hc and k > 0:
                    return 0.0
            else:
                if hm > h_lo and hb <= hc + half:
                    return 0.0
        ct = top[r, c]
        if ct > 0.0:
            t = tid[r, c]
            if t != last_tree and ct > h_lo and bottom[r, c] <= hc + half:
                trans *= 1.0 - blk[r, c]
                last_tree = t
        k += 1
    return trans


@njit(parallel=True, cache=True, fastmath=True, nogil=True)
def _sun_fraction_kernel(core_x0, core_z0, core_res, rows, cols, cas_x0, cas_z0, cas_res,
                         alts, azs, operp, oalong, h0, max_dist, hmax, hmin, top, bottom, blk, tid,
                         skip1, skip2, R1, R2, out):
    ns = alts.shape[0]
    scene_max = 0.0
    for r in range(skip2.shape[0]):
        for c in range(skip2.shape[1]):
            if skip2[r, c] > scene_max:
                scene_max = skip2[r, c]
    max_steps = int(max_dist / cas_res)
    for r in prange(rows):
        z = core_z0 + (r + 0.5) * core_res
        rf0 = (z - cas_z0) / cas_res - 0.5
        ri0 = int(math.floor(rf0 + 0.5))
        for c in range(cols):
            x = core_x0 + (c + 0.5) * core_res
            cf0 = (x - cas_x0) / cas_res - 0.5
            ci0 = int(math.floor(cf0 + 0.5))
            acc = 0.0
            for s in range(ns):
                a = math.radians(alts[s])
                if a <= 0.0:
                    continue
                zr = math.radians(azs[s])
                # quantise the direction (1e-12) so sin/cos of rotated azimuths agree bit-for-bit
                drow = math.floor(-math.cos(zr) * 1e12 + 0.5) * 1e-12
                dcol = math.floor(math.sin(zr) * 1e12 + 0.5) * 1e-12
                # sub-cell origin offset in the sun-aligned frame (perp = dir rotated by -90 deg)
                fr = rf0 - ri0 + operp[s] * dcol + oalong[s] * drow
                fc = cf0 - ci0 - operp[s] * drow + oalong[s] * dcol
                acc += _march(ri0, ci0, fr, fc, drow, dcol, math.tan(a), cas_res, h0, max_steps,
                              scene_max, hmax, hmin, top, bottom, blk, tid, skip1, skip2, R1, R2)
            v = acc / ns * 255.0 + 0.5
            out[r, c] = np.uint8(min(255.0, max(0.0, v)))


def compute_sun_fraction(caster: CasterGrid, core: GridSpec, alt_deg: float, az_deg: float,
                         mask: np.ndarray | None = None, samples: int = DISC_SAMPLES) -> np.ndarray:
    """uint8 [rows, cols] sun fraction on the core grid (0 = full shade, 255 = full sun).

    alt <= SUN_MIN_ALT_DEG -> all zeros (night/twilight). Cells where `mask` != 0 (buildings) -> 0.
    """
    out = np.zeros(core.shape, np.uint8)
    if alt_deg <= config.SUN_MIN_ALT_DEG:
        return out
    ss = disc_samples(alt_deg, az_deg, samples) if samples > 1 else [(alt_deg, az_deg, 0.0, 0.0)]
    alts = np.asarray([s[0] for s in ss], np.float64)
    azs = np.asarray([s[1] for s in ss], np.float64)
    operp = np.asarray([s[2] for s in ss], np.float64)
    oalong = np.asarray([s[3] for s in ss], np.float64)
    cs = caster.spec
    _sun_fraction_kernel(core.x0, core.z0, core.res, core.rows, core.cols, cs.x0, cs.z0, cs.res,
                         alts, azs, operp, oalong, float(config.H0), float(config.MAX_SHADOW_M),
                         caster.hmax, caster.hmin, caster.canopy_top, caster.canopy_bottom,
                         caster.canopy_block, caster.tree_id, caster.skip[0], caster.skip[1],
                         SKIP_RADII[0], SKIP_RADII[1], out)
    if mask is not None:
        out[mask != 0] = 0
    return out
