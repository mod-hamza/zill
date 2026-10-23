"""Low sun angles (high latitudes, Stream D): long shadows, caster ring, night flags.

At Oslo's winter-solstice noon the sun is ~6.6 deg high, so shadows are ~8.6x building height.
The engine measures shade on a pedestrian at h0 = PED_H, so a box of height h shades a pedestrian
up to (h - h0)/tan(alt) from its wall (the ground shadow h/tan(alt) is h0/tan(alt) longer).
Synthetic scenes only (clearly not real data).
"""

from __future__ import annotations

import math
from datetime import date, datetime
from zoneinfo import ZoneInfo

import numpy as np
import pytest

from zill import config
from zill.data.cities import CitySpec, expand_bbox, get_city_spec
from zill.shade.cache import ExposureTable
from zill.shade.heightmap import build_caster, building_mask
from zill.shade.raymarch import compute_sun_fraction
from zill.shade.synthetic import box, square_grid
from zill.sun.position import step_times, sun_position, sun_positions, sun_times

OSLO = (59.9100, 10.7440)
OSLO_TZ = "Europe/Oslo"
SUNLIT = 128
RES = config.GRID_RES_M


def _north_run(sf: np.ndarray, r: int, c: int) -> float:
    """Length (m) of the contiguous shaded run going north (decreasing row) from (r, c)."""
    n = 0
    while r >= 0 and sf[r, c] < SUNLIT:
        n += 1
        r -= 1
    return n * RES


def _first_outside_north(mask: np.ndarray, r: int, c: int) -> int:
    while mask[r, c]:
        r -= 1
    return r


def test_oslo_midwinter_noon_altitude_is_about_6_6_deg():
    st = sun_times(date(2026, 12, 21), *OSLO, OSLO_TZ)
    sp = sun_position(st["solar_noon"], *OSLO, OSLO_TZ)
    assert 6.3 <= sp.alt_deg <= 6.9, sp.alt_deg
    assert 175.0 <= sp.az_deg <= 185.0  # due south at solar noon
    assert not sp.is_night
    # shadow multiple 1/tan(alt) ~ 8.6x height
    assert 8.2 <= 1.0 / math.tan(math.radians(sp.alt_deg)) <= 9.0


@pytest.mark.parametrize("h", [20.0, 60.0])
def test_box_shadow_length_at_6_6_deg(h: float):
    alt = 6.6
    spec = square_grid(700.0)  # 1.4 km square: room for a 60 m box's ~500 m shadow
    blds = [box(1, -10, -10, 10, 10, h)]
    caster, mask = build_caster(spec, blds), building_mask(spec, blds)
    sf = compute_sun_fraction(caster, spec, alt, 180.0, mask)  # sun due south -> shadow north
    rc, cc = spec.rows // 2, spec.cols // 2
    r = _first_outside_north(mask, rc, cc)
    length = _north_run(sf, r, cc)
    expected = (h - config.H0) / math.tan(math.radians(alt))
    assert abs(length - expected) <= RES + 0.5, (h, length, expected)
    # consistent with the ground shadow h/tan(alt) minus the pedestrian-height offset
    cot = 1.0 / math.tan(math.radians(alt))
    assert abs(length + config.H0 * cot - h * cot) <= RES + 0.5
    # the sun side (south of the box) is fully lit
    assert sf[rc + 8:, :].min() == 255


def test_very_low_sun_long_shadow_within_ray_cap():
    alt = 3.0
    h = 40.0  # (40 - 1.5)/tan(3 deg) = 735 m, below MAX_SHADOW_M
    expected = (h - config.H0) / math.tan(math.radians(alt))
    assert expected < config.MAX_SHADOW_M
    spec = square_grid(900.0)
    blds = [box(1, -10, 700, 10, 720, h)]  # box near the south edge, shadow runs north
    caster, mask = build_caster(spec, blds), building_mask(spec, blds)
    sf = compute_sun_fraction(caster, spec, alt, 180.0, mask)
    r0, c0 = spec.cell_of(0.0, 710.0)
    r = _first_outside_north(mask, int(r0), int(c0))
    length = _north_run(sf, r, int(c0))
    assert abs(length - expected) <= RES + 0.5, (length, expected)


def test_caster_outside_core_shades_core_at_low_sun():
    """Buildings in the caster ring (outside the output grid) must still cast into it."""
    alt, h = 6.6, 80.0  # shadow (80 - 1.5)/tan(6.6) = 678 m
    caster_spec = square_grid(1000.0)
    core = square_grid(200.0)
    blds = [box(1, -20, 590, 20, 610, h)]  # 390 m south of the core's south edge
    caster = build_caster(caster_spec, blds)
    sf = compute_sun_fraction(caster, core, alt, 180.0, building_mask(core, blds))
    reach_z = 590.0 - (h - config.H0) / math.tan(math.radians(alt))  # ~ -88 m (inside the core)
    r_in, c = core.cell_of(0.0, reach_z + 6.0)
    # beyond the soft edge: the 0.53 deg sun disc smears the tip by +/-(h-h0)*0.265deg/sin^2(alt) ~ 28 m
    r_out, _ = core.cell_of(0.0, reach_z - 35.0)
    r_edge, _ = core.cell_of(0.0, 198.0)
    assert sf[int(r_edge), int(c)] < SUNLIT and sf[int(r_in), int(c)] < SUNLIT
    assert sf[int(r_out), int(c)] == 255
    # a column well to the side of the box stays lit
    _, c_side = core.cell_of(100.0, 0.0)
    assert sf[:, int(c_side)].min() == 255


@pytest.mark.parametrize("alt", [-10.0, -0.5, 0.0, 1.0, config.SUN_MIN_ALT_DEG])
def test_sun_below_threshold_is_night_not_raytraced(alt: float):
    spec = square_grid(100.0)
    blds = [box(1, -10, -10, 10, 10, 20)]
    sf = compute_sun_fraction(build_caster(spec, blds), spec, alt, 180.0, building_mask(spec, blds))
    assert sf.max() == 0


def test_oslo_midwinter_steps_flag_night():
    d = date(2026, 12, 21)
    times = step_times(d, *OSLO, OSLO_TZ)
    pos = sun_positions(times, *OSLO, OSLO_TZ)
    night = [p.is_night for p in pos]
    assert night[0] and night[-1]  # padded steps around sunrise/sunset are night
    assert not all(night) and any(night)
    assert max(p.alt_deg for p in pos) < 7.0
    # 08:00 local is before sunrise (~09:18): night; 12:30 is day
    zi = ZoneInfo(OSLO_TZ)
    assert sun_position(datetime(2026, 12, 21, 8, 0, tzinfo=zi), *OSLO, OSLO_TZ).is_night
    assert not sun_position(datetime(2026, 12, 21, 12, 30, tzinfo=zi), *OSLO, OSLO_TZ).is_night


def test_exposure_table_night_lookup():
    expo = np.zeros((2, 3), np.float32)
    t = ExposureTable("x", "2026-12-21", expo, np.array([900, 910, 920], np.int16),
                      np.array([540, 550, 560], np.int16), np.array([True, False, False]))
    assert t.is_night(541.0) and not t.is_night(552.0)
    legacy = ExposureTable("x", "2026-12-21", expo, np.array([900], np.int16), np.array([540], np.int16))
    assert legacy.is_night(540.0) is False  # unknown -> not claimed as night


def test_city_spec_caster_buffer_override():
    b = {"s": 59.903, "w": 10.724, "n": 59.917, "e": 10.764}
    default = CitySpec("t", "T", b, {"lat": 59.91, "lon": 10.744}, OSLO_TZ)
    wide = CitySpec("t", "T", b, {"lat": 59.91, "lon": 10.744}, OSLO_TZ, 1500.0)
    assert default.bbox_caster == expand_bbox(b, config.CASTER_BUFFER_M)
    assert wide.bbox_caster["s"] < default.bbox_caster["s"]
    assert default.preset_dates == config.PRESET_DATES


def test_registry_oslo_buffer_covers_midwinter_noon_shadows():
    spec = get_city_spec("oslo")
    dubai = get_city_spec("dubai_downtown")
    assert dubai.caster_buffer_m == config.CASTER_BUFFER_M and dubai.dates is None  # Dubai unchanged
    assert spec.timezone == OSLO_TZ
    assert spec.caster_buffer_m <= config.MAX_SHADOW_M  # rays can reach the ring's outer edge
    iso = spec.preset_dates["winter"]
    st = sun_times(date.fromisoformat(iso), spec.origin["lat"], spec.origin["lon"], spec.timezone)
    alt = sun_position(st["solar_noon"], spec.origin["lat"], spec.origin["lon"], spec.timezone).alt_deg
    # the ring holds every caster up to 150 m tall whose midwinter-noon shadow can reach the core
    assert spec.caster_buffer_m * math.tan(math.radians(alt)) >= 150.0

