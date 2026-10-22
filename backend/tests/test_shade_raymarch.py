"""Shadow geometry tests (PRD 7.3 a-d) + heightmap orientation (CONTRACTS 2).

Frame: x = east, z = south. Grid row 0 = north (min z), col 0 = west (min x).
"""

from __future__ import annotations

import numpy as np
import pytest

from zill import config
from zill.shade.heightmap import build_caster, building_mask
from zill.shade.raymarch import compute_sun_fraction
from zill.shade.synthetic import box, square_grid

SPEC = square_grid(400.0)  # 400 x 400 cells of 2 m, centred on the origin
SUNLIT = 128


def _scene(buildings, trees=None, spec=SPEC):
    caster = build_caster(spec, buildings, trees)
    mask = building_mask(spec, buildings)
    return caster, mask


def _shadow_run(sf, r, c, dr, dc):
    """Length (m) of the contiguous shaded run starting at (r, c) stepping (dr, dc)."""
    n = 0
    while 0 <= r < sf.shape[0] and 0 <= c < sf.shape[1] and sf[r, c] < SUNLIT:
        n += 1
        r += dr
        c += dc
    return n * SPEC.res


# --- heightmap orientation ------------------------------------------------------------------------
def test_heightmap_orientation_ne_quadrant():
    # building at x>0 (east) and z<0 (north) must land in the NE quadrant: low row, high col
    caster, mask = _scene([box(1, 100, -200, 140, -160, 30)])
    rows, cols = np.nonzero(caster.hmax > 0)
    assert rows.max() < SPEC.rows / 2 and cols.min() > SPEC.cols / 2
    # exact extents: x 100..140 -> cols 250..269 ; z -200..-160 -> rows 100..119
    assert (rows.min(), rows.max(), cols.min(), cols.max()) == (100, 119, 250, 269)
    assert (mask > 0).sum() == 20 * 20
    assert caster.bid[110, 260] == 1 and caster.bid[0, 0] == -1
    x, z = SPEC.cell_centre(110, 260)
    assert 100 < x < 140 and -200 < z < -160


def test_heightmap_holes_and_max_height():
    courtyard = box(1, -50, -50, 50, 50, 40)
    courtyard["holes"] = [[[-20, -20], [20, -20], [20, 20], [-20, 20]]]
    tower = box(2, 30, 30, 50, 50, 120)
    caster, mask = _scene([courtyard, tower])
    r, c = SPEC.cell_of(0.0, 0.0)
    assert caster.hmax[r, c] == 0 and mask[r, c] == 0  # the hole is open
    r, c = SPEC.cell_of(-35.0, 0.0)
    assert caster.hmax[r, c] == 40
    r, c = SPEC.cell_of(40.0, 40.0)
    assert caster.hmax[r, c] == 120 and caster.bid[r, c] == 2  # overlap keeps the max


def test_floating_part_not_in_mask_but_blocks():
    bridge = box(1, -40, -4, 40, 4, 12, min_h=8)  # elevated walkway 8-12 m
    caster, mask = _scene([bridge])
    assert mask.sum() == 0
    r, c = SPEC.cell_of(0.0, 0.0)
    assert caster.hmin[r, c] == 8 and caster.hmax[r, c] == 12
    sf = compute_sun_fraction(caster, SPEC, 85.0, 180.0, mask)
    assert sf[r, c] < SUNLIT  # the pedestrian under the bridge at near-noon is shaded
    r2, c2 = SPEC.cell_of(0.0, -20.0)  # 20 m north of it: sunlit
    assert sf[r2, c2] == 255


# --- (a) shadow length & direction ----------------------------------------------------------------
@pytest.mark.parametrize(
    "az, expect_dir",
    [
        (90.0, (0, -1)),  # sun in the east  -> shadow extends WEST (decreasing x / col)
        (180.0, (-1, 0)),  # sun in the south -> shadow extends NORTH (decreasing z / row)
        (270.0, (0, 1)),  # sun in the west  -> shadow extends EAST (increasing x / col)
        (0.0, (1, 0)),  # sun in the north -> shadow extends SOUTH (increasing z / row)
    ],
)
def test_box_shadow_length_and_direction(az, expect_dir):
    caster, mask = _scene([box(1, -10, -10, 10, 10, 100)])
    sf = compute_sun_fraction(caster, SPEC, 45.0, az, mask)
    rc, cc = SPEC.rows // 2, SPEC.cols // 2  # cell just SE of the centre, inside the box
    dr, dc = expect_dir
    # walk from the box centre to the first outside cell in the expected direction
    r, c = rc, cc
    while mask[r, c]:
        r += dr
        c += dc
    length = _shadow_run(sf, r, c, dr, dc)
    expected = 100.0 - config.H0  # pedestrian height: shadow tip is where the ray clears 1.5 m
    assert abs(length - 100.0) <= 3.0
    assert abs(length - expected) <= 2.0
    # opposite side is sunlit right next to the box
    r, c = rc, cc
    while mask[r, c]:
        r -= dr
        c -= dc
    assert sf[r, c] == 255 and sf[r - dr, c - dc] == 255
    # nothing shaded on the sun side anywhere
    if dc == -1:
        assert sf[:, cc + 6:].min() == 255
    if dc == 1:
        assert sf[:, : cc - 6].min() == 255
    if dr == -1:
        assert sf[rc + 6:, :].min() == 255
    if dr == 1:
        assert sf[: rc - 6, :].min() == 255


def test_shadow_length_scales_with_altitude():
    caster, mask = _scene([box(1, -10, -10, 10, 10, 60)])
    rc, cc = SPEC.rows // 2, SPEC.cols // 2
    for alt in (20.0, 30.0, 60.0):
        sf = compute_sun_fraction(caster, SPEC, alt, 90.0, mask)
        length = _shadow_run(sf, rc, cc - 6, 0, -1)
        expected = (60.0 - config.H0) / np.tan(np.radians(alt))
        assert abs(length - expected) <= 3.0, (alt, length, expected)


# --- (b) zenith sun -----------------------------------------------------------------------------
def test_zenith_sun_shadow_only_on_footprint():
    caster, mask = _scene([box(1, -10, -10, 10, 10, 100), box(2, 100, 50, 130, 90, 300)])
    sf = compute_sun_fraction(caster, SPEC, 90.0, 0.0, mask)
    assert (sf[mask > 0] == 0).all()
    assert (sf[mask == 0] == 255).all()


def test_night_is_all_dark():
    caster, mask = _scene([box(1, -10, -10, 10, 10, 100)])
    assert compute_sun_fraction(caster, SPEC, 1.5, 250.0, mask).max() == 0


# --- (c) two boxes with a gap --------------------------------------------------------------------
def test_gap_between_boxes():
    caster, mask = _scene([box(1, -30, -20, -10, 20, 50), box(2, 10, -20, 30, 20, 50)])
    rc = SPEC.rows // 2
    gap_cols = [SPEC.cell_of(x, 0.0)[1] for x in np.arange(-9.0, 10.0, 2.0)]
    # low eastern sun: B's 48.5 m shadow covers the whole 20 m gap
    sf = compute_sun_fraction(caster, SPEC, 45.0, 90.0, mask)
    assert all(sf[rc, c] == 0 for c in gap_cols)
    # high eastern sun: shadow (50-1.5)/tan(80) = 8.6 m -> only the eastern part of the gap is shaded
    sf = compute_sun_fraction(caster, SPEC, 80.0, 90.0, mask)
    row = np.array([sf[rc, c] for c in gap_cols])
    xs = np.arange(-9.0, 10.0, 2.0)
    assert (row[xs < 0] == 255).all()
    assert (row[xs > 3] < SUNLIT).all()
    # sun from the north along the gap: the gap is sunlit, shadows fall south of the boxes
    sf = compute_sun_fraction(caster, SPEC, 45.0, 0.0, mask)
    assert all(sf[rc, c] == 255 for c in gap_cols)
    r_south, c_a = SPEC.cell_of(-20.0, 40.0)
    assert sf[r_south, c_a] == 0


# --- (d) rotation symmetry -----------------------------------------------------------------------
def _rot_box(b):
    # rotate the scene 90 deg clockwise seen from above: north -> east, i.e. (x, z) -> (-z, x)
    (xa, za), _, (xb, zb), _ = b["footprint"]
    return box(b["id"], -zb, xa, -za, xb, b["height"])


def test_rotation_symmetry():
    rng = np.random.default_rng(3)
    blds = []
    for i in range(40):
        cx, cz = rng.integers(-150, 150, 2) * 2
        w, d = rng.integers(4, 20, 2) * 2
        blds.append(box(i, cx, cz, cx + w, cz + d, float(rng.integers(5, 120))))
    tree_xz = rng.integers(-150, 150, (30, 2)) * 2
    trees = [{"x": float(x), "z": float(z), "r": 3.0, "h": 7.0} for x, z in tree_xz]
    trees_r = [{"x": -t["z"], "z": t["x"], "r": 3.0, "h": 7.0} for t in trees]
    caster, mask = _scene(blds, trees)
    caster_r, mask_r = _scene([_rot_box(b) for b in blds], trees_r)
    assert np.array_equal(np.rot90(mask, k=-1), mask_r)
    for alt, az in ((35.0, 120.0), (60.0, 200.0), (25.0, 290.0), (50.0, 33.0)):
        sf = compute_sun_fraction(caster, SPEC, alt, az, mask)
        sf_r = compute_sun_fraction(caster_r, SPEC, alt, (az + 90.0) % 360.0, mask_r)
        expected = np.rot90(sf, k=-1)
        diff = np.abs(expected.astype(int) - sf_r.astype(int))
        assert (diff == 0).mean() > 0.999, (alt, az, (diff == 0).mean())
        assert diff.max() <= 64


# --- trees ---------------------------------------------------------------------------------------
def test_tree_canopy_partial_shade():
    trees = [{"x": 1.0, "z": 1.0, "r": 3.0, "h": 7.0, "src": "node"}]
    caster, mask = _scene([], trees)
    r, c = SPEC.cell_of(1.0, 1.0)
    sf = compute_sun_fraction(caster, SPEC, 85.0, 180.0, mask)
    expected = 255 * (1 - config.TREE_BLOCK)  # one tree crossed once: transmissivity 0.35
    assert abs(int(sf[r, c]) - expected) <= 26
    # the tree's shadow at 30 deg sun from the south falls to the north
    sf = compute_sun_fraction(caster, SPEC, 30.0, 180.0, mask)
    r_n, c_n = SPEC.cell_of(1.0, -6.0)
    r_s, c_s = SPEC.cell_of(1.0, 10.0)
    assert sf[r_n, c_n] < 200 and sf[r_s, c_s] == 255


def test_building_cells_are_zero_and_soft_edges_exist():
    caster, mask = _scene([box(1, -10, -10, 10, 10, 100)])
    sf = compute_sun_fraction(caster, SPEC, 30.0, 135.0, mask)
    assert (sf[mask > 0] == 0).all()
    vals = np.unique(sf)
    assert ((vals > 0) & (vals < 255)).any()  # penumbra from sun-disc sampling
