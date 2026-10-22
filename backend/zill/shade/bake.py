"""Shade bake CLI (PRD 7.4).

    python -m zill.shade.bake --city dubai_downtown [--dates summer,hackathon] [--date 2026-03-03] [--force]
    python -m zill.shade.bake --city dubai_downtown --exposure-only   # graph.json changed: ~seconds

Writes `building_mask.png`, `shade/<date_id>/step_HHMM.png` + `index.json`,
`exposure_<date_id>.npz` and `shade/bake_log.json` (merged into meta.build_log by the API).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from zill import config
from zill.shade.cache import compute_date, get_city_shade, resolve_date, write_png

log = logging.getLogger("zill.shade.bake")


def _dir_mb(paths: list[Path]) -> float:
    return sum(p.stat().st_size for p in paths if p.exists()) / 1e6


def bake(city_id: str, date_keys: list[str], force: bool = False, exposure_only: bool = False) -> dict:
    t_all = time.perf_counter()
    sc = get_city_shade(city_id)
    entries = []
    if exposure_only:
        return _refresh_exposure(city_id, date_keys)
    t = time.perf_counter()
    caster = sc.caster
    entries.append({"t_ms": 0, "step": "shadow_precompute", "count": int((caster.hmax > 0).sum()),
                    "label": f"Rasterised {len(sc.buildings)} buildings and {len(sc.trees)} trees into a "
                             f"{caster.spec.rows}x{caster.spec.cols} caster grid ({caster.spec.res:g} m)",
                    "duration_ms": int((time.perf_counter() - t) * 1000)})
    write_png(sc.city_dir / "building_mask.png", sc.mask)
    sampler = sc.sampler
    summary: dict = {"city_id": city_id, "core_grid": sc.core.to_dict(),
                     "caster_grid": sc.caster_spec.to_dict(),
                     "max_height_m": caster.max_height, "dates": {}}
    if sampler is not None:
        summary["exposure_sampler"] = sampler.stats
        summary["n_edges"] = sampler.n_edges
    for key in date_keys:
        tgt = resolve_date(city_id, key)
        t = time.perf_counter()

        def progress(done: int, total: int, hhmm: str, _key: str = key) -> None:
            if done == 1 or done % 10 == 0 or done == total:
                log.info("%s %s: %d/%d (%s)", city_id, _key, done, total, hhmm)

        index = compute_date(city_id, key, progress, force=force, exposure_only=exposure_only)
        pngs = [tgt.out_dir / s["file"] for s in index["steps"]]
        info = {
            "iso": tgt.iso,
            "steps": len(index["steps"]),
            "day_steps": sum(1 for s in index["steps"] if not s["night"]),
            "first": index["steps"][0]["hhmm"],
            "last": index["steps"][-1]["hhmm"],
            "png_mb": round(_dir_mb(pngs), 2),
            "npz_mb": round(_dir_mb([tgt.npz_path]), 3),
            "timing": index.get("timing"),
        }
        summary["dates"][key] = info
        entries.append({"t_ms": int((t - t_all) * 1000), "step": "shadow_precompute", "count": info["steps"],
                        "label": f"Sun-shadow rasters for {tgt.date_id} ({tgt.iso}): {info['steps']} "
                                 f"ten-minute steps {info['first']}-{info['last']}",
                        "duration_ms": int((time.perf_counter() - t) * 1000), "date_id": tgt.date_id})
    summary["total_png_mb"] = round(sum(d["png_mb"] for d in summary["dates"].values()), 2)
    summary["total_npz_mb"] = round(sum(d["npz_mb"] for d in summary["dates"].values()), 3)
    summary["total_s"] = round(time.perf_counter() - t_all, 1)
    log_path = sc.city_dir / "shade" / "bake_log.json"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps({"generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
                                    "build_log": entries, "summary": summary}, indent=1), encoding="utf-8")
    return summary


def _refresh_exposure(city_id: str, date_keys: list[str]) -> dict:
    """Rebuild only the exposure tables from the existing PNGs; keep the raster build_log."""
    t_all = time.perf_counter()
    sc = get_city_shade(city_id)
    sampler = sc.sampler
    if sampler is None:
        raise SystemExit(f"no graph.json for {city_id}")
    log_path = sc.city_dir / "shade" / "bake_log.json"
    doc: dict = {"build_log": [], "summary": {"dates": {}}}
    if log_path.exists():
        doc = json.loads(log_path.read_text(encoding="utf-8"))
    summary = doc.setdefault("summary", {"dates": {}})
    for key in date_keys:
        tgt = resolve_date(city_id, key)
        compute_date(city_id, key, exposure_only=True)
        summary.setdefault("dates", {}).setdefault(key, {})["npz_mb"] = round(_dir_mb([tgt.npz_path]), 3)
    summary["exposure_sampler"] = sampler.stats
    summary["n_edges"] = sampler.n_edges
    summary["total_npz_mb"] = round(sum(d.get("npz_mb", 0) for d in summary["dates"].values()), 3)
    doc["exposure_refreshed_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    return {"city_id": city_id, "n_edges": sampler.n_edges, "exposure_sampler": sampler.stats,
            "dates": {k: summary["dates"][k] for k in date_keys},
            "total_s": round(time.perf_counter() - t_all, 1)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--city", default=config.DEFAULT_CITY)
    ap.add_argument("--dates", default=",".join(config.PRESET_DATES), help="comma-separated preset ids")
    ap.add_argument("--date", default=None, help="one extra ISO date (on-demand cache)")
    ap.add_argument("--force", action="store_true", help="recompute rasters even if PNGs exist")
    ap.add_argument("--exposure-only", action="store_true",
                    help="rebuild exposure_<date>.npz from existing PNGs (after graph.json changes)")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    keys = [k for k in a.dates.split(",") if k] if a.date is None else [a.date]
    summary = bake(a.city, keys, a.force, a.exposure_only)
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
