import json

import numpy as np

from zill import config
from zill.geo import to_local, to_wgs84

ORIGIN = (config.ORIGIN_LAT, config.ORIGIN_LON)


def test_origin_maps_to_zero():
    x, z = to_local(config.ORIGIN_LAT, config.ORIGIN_LON, ORIGIN)
    assert abs(x) < 1e-9 and abs(z) < 1e-9


def test_axes_east_x_south_z():
    x, z = to_local(config.ORIGIN_LAT, config.ORIGIN_LON + 0.01, ORIGIN)
    assert x > 0 and abs(z) < 1e-9
    x, z = to_local(config.ORIGIN_LAT + 0.01, config.ORIGIN_LON, ORIGIN)
    assert z < 0 and abs(x) < 1e-9


def test_round_trip_1000_random_points():
    rng = np.random.default_rng(42)
    x = rng.uniform(-5000, 5000, 1000)
    z = rng.uniform(-5000, 5000, 1000)
    lat, lon = to_wgs84(x, z, ORIGIN)
    x2, z2 = to_local(lat, lon, ORIGIN)
    assert np.max(np.hypot(x2 - x, z2 - z)) < 0.01
    # scalar path agrees with vector path
    for i in range(10):
        la, lo = to_wgs84(float(x[i]), float(z[i]), {"lat": ORIGIN[0], "lon": ORIGIN[1]})
        assert abs(la - lat[i]) < 1e-12 and abs(lo - lon[i]) < 1e-12


def test_golden_file():
    pts = json.loads((config.DATA_DIR / "curated" / "geo_golden.json").read_text())
    assert len(pts["points"]) == 10
    o = pts["origin"]
    for p in pts["points"]:
        x, z = to_local(p["lat"], p["lon"], o)
        assert abs(x - p["x"]) < 0.001 and abs(z - p["z"]) < 0.001
