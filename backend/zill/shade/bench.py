"""Raymarch performance benchmark on a SYNTHETIC city (random boxes + one 828 m tower).

    python -m zill.shade.bench [--boxes 2500] [--core 1300]
"""

from __future__ import annotations

import argparse
import os
import time

from zill.shade.heightmap import GridSpec, build_caster, building_mask
from zill.shade.raymarch import compute_sun_fraction
from zill.shade.synthetic import random_city

CASES = ((60.0, 180.0), (35.0, 110.0), (20.0, 250.0), (8.0, 100.0), (3.0, 290.0), (85.0, 200.0))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--boxes", type=int, default=2500)
    ap.add_argument("--core", type=int, default=1300, help="core grid size in cells (square)")
    a = ap.parse_args(argv)
    res = 2.0
    half = a.core * res / 2
    core = GridSpec(-half, -half, a.core, a.core, res)
    pad = 900.0
    n = int((2 * half + 2 * pad) / res)
    cas = GridSpec(-half - pad, -half - pad, n, n, res)
    blds = random_city(a.boxes, half + pad)
    t = time.perf_counter()
    caster = build_caster(cas, blds)
    mask = building_mask(core, blds)
    print(f"cpus={os.cpu_count()} core={core.shape} caster={cas.shape} boxes={len(blds)} "
          f"raster={time.perf_counter() - t:.2f}s")
    compute_sun_fraction(caster, core, 45.0, 135.0, mask)  # JIT warm-up
    for alt, az in CASES:
        t = time.perf_counter()
        compute_sun_fraction(caster, core, alt, az, mask)
        print(f"alt={alt:5.1f} az={az:5.1f} step={time.perf_counter() - t:.3f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
