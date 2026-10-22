"""Visual QA previews of shade rasters (PRD 18.3). Requires matplotlib (dev dependency).

    python -m zill.shade.qa --city dubai_downtown --out docs/qa/phase2

The map is drawn north-up: PNG row 0 (min z) is the top edge, east is to the right. Buildings are
drawn in a warm sandstone tone over the sun-fraction raster (dark = shade). Arrows show north and
the horizontal direction TOWARD the sun; shadows must extend the opposite way.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np

from zill import config
from zill.shade.heightmap import GridSpec

SAND = (0.80, 0.62, 0.42)
SHADE = (0.17, 0.20, 0.26)
SUN = (0.98, 0.95, 0.88)


def render_preview(sf: np.ndarray, mask: np.ndarray, spec: GridSpec, alt: float, az: float, title: str,
                   path: Path, crop_m: float | None = None, centre: tuple[float, float] = (0.0, 0.0)) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    f = sf.astype(np.float32)[..., None] / 255.0
    rgb = np.asarray(SHADE)[None, None, :] * (1 - f) + np.asarray(SUN)[None, None, :] * f
    rgb[mask != 0] = SAND
    x1 = spec.x0 + spec.cols * spec.res
    z1 = spec.z0 + spec.rows * spec.res
    # imshow with origin="upper": row 0 at the top. y axis = northing = -z, so top = -z0.
    extent = (spec.x0, x1, -z1, -spec.z0)
    fig, ax = plt.subplots(figsize=(10, 10), dpi=110)
    ax.imshow(rgb, origin="upper", extent=extent, interpolation="nearest")
    if crop_m:
        cx, cz = centre
        ax.set_xlim(cx - crop_m, cx + crop_m)
        ax.set_ylim(-cz - crop_m, -cz + crop_m)
    xl, yl = ax.get_xlim(), ax.get_ylim()
    w = xl[1] - xl[0]
    # north arrow (top-left)
    nx, ny = xl[0] + 0.07 * w, yl[0] + 0.80 * (yl[1] - yl[0])
    ax.annotate("", xy=(nx, ny + 0.12 * w), xytext=(nx, ny),
                arrowprops={"arrowstyle": "-|>", "color": "black", "lw": 2.5})
    ax.text(nx, ny + 0.14 * w, "N", ha="center", va="bottom", fontsize=16, weight="bold")
    # sun arrow (top-right): horizontal direction toward the sun = (sin az, cos az) in (east, north)
    sx, sy = xl[0] + 0.83 * w, yl[0] + 0.83 * (yl[1] - yl[0])
    L = 0.11 * w
    dx, dy = math.sin(math.radians(az)) * L, math.cos(math.radians(az)) * L
    ax.annotate("", xy=(sx + dx, sy + dy), xytext=(sx, sy),
                arrowprops={"arrowstyle": "-|>", "color": "#c8641e", "lw": 3})
    ax.plot([sx + dx], [sy + dy], "o", color="#e8a33a", ms=16)
    ax.text(sx, sy - 0.05 * w, f"toward sun\naz {az:.0f}°, alt {alt:.0f}°", ha="center", va="top",
            fontsize=10, color="#7a3a10", bbox={"facecolor": "white", "alpha": 0.85, "edgecolor": "none"})
    ax.set_xlabel("east  x (m)")
    ax.set_ylabel("north  -z (m)")
    ax.set_title(title)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def main(argv: list[str] | None = None) -> int:
    from zill.shade.cache import get_city_shade, get_shade_step, plan_steps, resolve_date

    ap = argparse.ArgumentParser()
    ap.add_argument("--city", default=config.DEFAULT_CITY)
    ap.add_argument("--out", default=str(config.REPO_ROOT / "docs" / "qa" / "phase2"))
    a = ap.parse_args(argv)
    sc = get_city_shade(a.city)
    out = Path(a.out)
    for date_key, hhmm in (("hackathon", "1200"), ("hackathon", "1600"), ("summer", "1330"),
                           ("hackathon", "0800")):
        tgt = resolve_date(a.city, date_key)
        st = next(s for s in plan_steps(sc, tgt.iso) if s["hhmm"] == hhmm)
        sf = get_shade_step(a.city, date_key, hhmm)
        title = f"{sc.meta.get('name', a.city)} — {date_key} {tgt.iso} {hhmm[:2]}:{hhmm[2:]} (shade raster)"
        render_preview(sf, sc.mask, sc.core, st["alt"], st["az"], title, out / f"{date_key}_{hhmm}_full.png")
        render_preview(sf, sc.mask, sc.core, st["alt"], st["az"], title + " — Burj Khalifa crop",
                       out / f"{date_key}_{hhmm}_burj.png", crop_m=450.0)
        print("wrote", out / f"{date_key}_{hhmm}_full.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
