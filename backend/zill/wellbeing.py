"""Well-being context for a route (overnight Stream A): UV band, heat stress, daylight window, breaks.

Pure functions, no I/O. Inputs come from the weather module (Open-Meteo, recorded or live, labelled)
and the solar position. Everything here is well-being guidance, never medical advice: no function
claims to treat or prevent anything.

Sources
* UV bands and advice: WHO, "Global Solar UV Index: A Practical Guide" (WHO/WMO/UNEP/ICNIRP, 2002):
  0-2 low, 3-5 moderate, 6-7 high, 8-10 very high, 11+ extreme. Advice texts paraphrase its
  "no protection / protection required / extra protection" messages.
* Heat-stress bands: US National Weather Service heat-index categories (Caution 80-90 F, Extreme
  caution 90-103 F, Danger 103-124 F, Extreme danger >= 125 F), converted to C. We apply them to the
  BoM apparent temperature, which is a different index, so the band is labelled "indicative".
* Overcast / sky state: clear-sky index = measured global horizontal irradiance (Open-Meteo
  `shortwave_radiation`) / clear-sky GHI from the Haurwitz model,
  GHI_cs = 1098 * cos(z) * exp(-0.057 / cos(z)) W/m2 (z = solar zenith; Haurwitz 1945, as evaluated in
  Reno, Hansen & Stein, "Global Horizontal Irradiance Clear Sky Models", Sandia SAND2012-2389).
  Overcast when the index < CLEAR_SKY_INDEX_OVERCAST (0.4). Total cloud cover counts thin high cloud
  (cirrus) as cloud, so it is only the fallback (>= 70 %) when radiation is missing.
* Daylight / vitamin D window: shadow-rule heuristic (sun altitude >= 45 deg, i.e. your shadow is no
  longer than you are) plus UV >= 3 and cloud cover < 70 %. A rule of thumb, not a measurement.
"""

from __future__ import annotations

import math
from typing import Any

from zill import config

NOT_MEDICAL = "Well-being guidance, not medical advice."
DAYLIGHT_TEXT = "Daylight / vitamin D window. Well-being guidance, not medical advice."

EXTRA_PROTECTION = (
    "Extra protection: avoid being outside around midday; seek shade; shirt, sunscreen and hat are a must."
)

# (lower bound inclusive, band, advice) -- WHO Global Solar UV Index practical guide (2002)
UV_BANDS: tuple[tuple[float, str, str], ...] = (
    (0.0, "low", "No protection needed; you can safely stay outside."),
    (3.0, "moderate", "Protection needed: seek shade around midday, cover up, wear a hat and sunscreen."),
    (6.0, "high", "Protection needed: seek shade around midday, cover up, wear a hat and sunscreen."),
    (
        8.0,
        "very high",
        EXTRA_PROTECTION,
    ),
    (
        11.0,
        "extreme",
        EXTRA_PROTECTION,
    ),
)

# (lower bound C inclusive, band) -- US NWS heat-index categories (F -> C), applied indicatively
HEAT_BANDS: tuple[tuple[float, str], ...] = (
    (-math.inf, "none"),
    (26.7, "caution"),
    (32.2, "extreme caution"),
    (39.4, "danger"),
    (51.7, "extreme danger"),
)
HEAT_ADVICE = {
    "none": "No heat stress expected.",
    "caution": "Warm: fatigue is possible with long exposure; carry water.",
    "extreme caution": "Hot: drink water regularly and take shade breaks.",
    "danger": "Very hot: limit time in direct sun, drink water often, rest in shade or indoors.",
    "extreme danger": "Extreme heat: avoid walking in direct sun; use indoor or air-conditioned options.",
}


def _r(x: float | None, nd: int = 1) -> float | None:
    return None if x is None else round(float(x), nd)


def uv_band(uv_index: float | None, basis: str | None = None) -> dict[str, Any]:
    """WHO UV-index band and advice. `basis` says where the number came from (forecast or estimate)."""
    if uv_index is None:
        return {"index": None, "band": "unknown", "advice": "UV index unavailable.", "basis": basis}
    v = max(0.0, float(uv_index))
    band, advice = UV_BANDS[0][1], UV_BANDS[0][2]
    for lo, b, a in UV_BANDS:
        # WHO bands are on the rounded index (2.6 reads as 3)
        if round(v) >= lo:
            band, advice = b, a
    return {
        "index": round(v, 1),
        "band": band,
        "advice": advice,
        "basis": basis,
        "source": "WHO Global Solar UV Index bands",
    }


def heat_stress(apparent_c: float | None, rhl: float | None = None) -> dict[str, Any]:
    """Indicative heat-stress band from the apparent temperature (NWS heat-index thresholds)."""
    if apparent_c is None:
        return {"apparent_c": None, "band": "unknown", "advice": "Apparent temperature unavailable."}
    band = HEAT_BANDS[0][1]
    for lo, b in HEAT_BANDS:
        if apparent_c >= lo:
            band = b
    out: dict[str, Any] = {
        "apparent_c": _r(apparent_c),
        "band": band,
        "advice": HEAT_ADVICE[band],
        "indicative": True,
        "source": "US NWS heat-index categories applied to apparent temperature (indicative)",
    }
    if rhl is not None:
        out["route_rhl"] = _r(rhl)
    return out


def clear_sky_ghi(alt_deg: float | None) -> float:
    """Haurwitz clear-sky global horizontal irradiance (W/m2) for a solar altitude. 0 when the sun is down."""
    if alt_deg is None or alt_deg <= 0.0:
        return 0.0
    cz = math.sin(math.radians(alt_deg))  # cos(zenith)
    return 1098.0 * cz * math.exp(-0.057 / cz)


def clear_sky_index(shortwave_wm2: float | None, alt_deg: float | None) -> float | None:
    """Measured / Haurwitz clear-sky GHI. None when unmeasured or the clear-sky GHI is too small to judge."""
    if shortwave_wm2 is None:
        return None
    cs = clear_sky_ghi(alt_deg)
    if cs < config.CLEAR_SKY_MIN_GHI_WM2:
        return None
    return float(shortwave_wm2) / cs


def sky_state(clear_index: float | None, cloud_cover_pct: float | None) -> dict[str, Any]:
    """Is the sky overcast? Radiation first (clear-sky index < 0.4), cloud cover >= 70 % only as fallback."""
    thr = config.CLEAR_SKY_INDEX_OVERCAST
    if clear_index is not None:
        return {
            "overcast": clear_index < thr,
            "basis": "radiation",
            "clear_sky_index": round(clear_index, 2),
            "cloud_cover_pct": _r(cloud_cover_pct, 0),
            "rule": f"overcast when measured / Haurwitz clear-sky radiation < {thr}",
        }
    if cloud_cover_pct is not None:
        return {
            "overcast": cloud_cover_pct >= config.OVERCAST_CLOUD_PCT,
            "basis": "cloud_cover",
            "clear_sky_index": None,
            "cloud_cover_pct": _r(cloud_cover_pct, 0),
            "rule": f"radiation missing: overcast when cloud cover >= {config.OVERCAST_CLOUD_PCT:.0f} %",
        }
    return {
        "overcast": None,
        "basis": "unknown",
        "clear_sky_index": None,
        "cloud_cover_pct": None,
        "rule": "",
    }


def _sky_reason(sky: dict[str, Any]) -> str:
    if sky["basis"] == "radiation":
        return (
            f"sunlight is {100 * sky['clear_sky_index']:.0f}% of the clear-sky level "
            f"(below {100 * config.CLEAR_SKY_INDEX_OVERCAST:.0f}%: overcast)"
        )
    return f"cloud cover {sky['cloud_cover_pct']:.0f}% is {config.OVERCAST_CLOUD_PCT:.0f}% or more"


def shadow_ratio(alt_deg: float | None) -> float | None:
    """Length of your shadow in multiples of your height: 1 / tan(altitude). None when the sun is down."""
    if alt_deg is None or alt_deg <= 0.0:
        return None
    return 1.0 / math.tan(math.radians(alt_deg))


def daylight_window(
    alt_deg: float | None,
    uv_index: float | None,
    cloud_cover_pct: float | None,
    clear_index: float | None = None,
) -> dict[str, Any]:
    """Daylight / vitamin D window: altitude >= 45 deg AND UV >= 3 AND not overcast.

    Overcast = clear-sky index < 0.4 (radiation), or cloud cover >= 70 % when radiation is missing.
    An unknown sky never opens the window (conservative); the reason is listed.
    """
    sky = sky_state(clear_index, cloud_cover_pct)
    ratio = shadow_ratio(alt_deg)
    reasons: list[str] = []
    if alt_deg is None or alt_deg <= 0.0:
        reasons.append("the sun is below the horizon")
    elif alt_deg < config.DAYLIGHT_MIN_ALT_DEG:
        reasons.append(
            f"the sun is {alt_deg:.1f} deg high, below {config.DAYLIGHT_MIN_ALT_DEG:.0f} deg "
            "(your shadow is longer than you are)"
        )
    if uv_index is None:
        reasons.append("UV index unavailable")
    elif round(uv_index) < config.DAYLIGHT_MIN_UV:  # WHO reports the index rounded, as uv_band does
        reasons.append(f"UV index {uv_index:.1f} is below {config.DAYLIGHT_MIN_UV:.0f}")
    if sky["overcast"] is None:
        reasons.append("sky state unknown (no radiation or cloud data)")
    elif sky["overcast"]:
        reasons.append(_sky_reason(sky))
    active = not reasons
    if ratio is None:
        shadow_text = "The sun is below the horizon."
    else:
        shadow_text = f"Your shadow is {ratio:.1f}× your height."
    return {
        "active": active,
        "text": DAYLIGHT_TEXT if active else f"No daylight / vitamin D window now: {'; '.join(reasons)}.",
        "sun_alt_deg": _r(alt_deg),
        "shadow_ratio": _r(ratio, 2),
        "shadow_text": shadow_text,
        "uv_index": _r(uv_index),
        "cloud_cover_pct": _r(cloud_cover_pct, 0),
        "sky": sky,
        "reasons": reasons,
        "rule": "sun altitude >= 45 deg, UV index >= 3, not overcast (rule of thumb)",
        "disclaimer": NOT_MEDICAL,
    }


def break_prompts(
    segments: list[dict[str, Any]] | None,
    sun_exposure_s: float,
    apparent_c: float | None,
    every_min: float | None = None,
) -> dict[str, Any]:
    """Hydration / shade-break prompts every `every_min` minutes of DIRECT sun, only in hot conditions.

    Hot = apparent temperature >= WELLBEING_HOT_APPARENT_C (NWS "extreme caution", indicative).
    With segments, each prompt carries the elapsed seconds at which the threshold is crossed; without
    them only the count is known (`at_s` = None).
    """
    every = float(every_min or config.WELLBEING_BREAK_SUN_MIN)
    hot = apparent_c is not None and apparent_c >= config.WELLBEING_HOT_APPARENT_C
    out: dict[str, Any] = {
        "hot": hot,
        "every_sun_min": every,
        "prompts": [],
        "rule": (
            f"a prompt every {every:.0f} min of direct sun when the apparent temperature is "
            f">= {config.WELLBEING_HOT_APPARENT_C:.1f} C"
        ),
    }
    if not hot:
        return out
    step = every * 60.0
    prompts: list[dict[str, Any]] = []
    if segments:
        acc, nxt = 0.0, step
        for sg in segments:
            t = float(sg.get("t_s", 0.0))
            s = float(sg.get("sun", 0.0)) if sg.get("cls", "open") == "open" else 0.0
            add = s * t
            while add > 0 and acc + add >= nxt:
                frac = (nxt - acc) / add
                prompts.append({"at_s": round(float(sg.get("arrival_s", 0.0)) + frac * t, 1)})
                nxt += step
            acc += add
    else:
        prompts = [{"at_s": None} for _ in range(int(sun_exposure_s // step))]
    for i, p in enumerate(prompts, 1):
        p["sun_min"] = round(i * every, 1)
        p["text"] = (
            f"About {i * every:.0f} min in direct sun so far: drink some water and take a short break "
            f"in the shade. {NOT_MEDICAL}"
        )
    out["prompts"] = prompts
    return out


def overcast_note(
    preference: str, cloud_cover_pct: float | None, clear_index: float | None = None
) -> dict[str, Any] | None:
    """Sun mode under an overcast sky (see `sky_state`): the sunny route has little direct sun today."""
    sky = sky_state(clear_index, cloud_cover_pct)
    if preference != "sun" or not sky["overcast"]:
        return None
    if sky["basis"] == "radiation":
        pct = 100 * sky["clear_sky_index"]
        what = f"Sunlight is only about {pct:.0f}% of the clear-sky level at this time"
    else:
        what = f"Cloud cover is about {cloud_cover_pct:.0f}% at this time"
    return {
        "cloud_cover_pct": None if cloud_cover_pct is None else round(float(cloud_cover_pct)),
        "clear_sky_index": sky["clear_sky_index"],
        "basis": sky["basis"],
        "text": f"{what}, so the sunny route has little direct sun today. "
        "The sun figures assume a clear sky.",
    }


def assess(
    preference: str,
    alt_deg: float | None,
    weather: dict[str, Any] | None,
    route_stats: dict[str, Any] | None = None,
    segments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Full `wellbeing` block for a route response.

    weather: the dict from `zill.weather.get` (keys uv_index, uv_basis, apparent_c, cloud_cover_pct,
    source, label). route_stats / segments: the recommended (best) route.
    """
    w = weather or {}
    uv = w.get("uv_index")
    cloud = w.get("cloud_cover_pct")
    kt = w.get("clear_sky_index")
    app = w.get("apparent_c")
    st = route_stats or {}
    return {
        "preference": preference,
        "uv": uv_band(uv, w.get("uv_basis")),
        "heat_stress": heat_stress(app, st.get("rhl")),
        "daylight_window": daylight_window(alt_deg, uv, cloud, kt),
        "breaks": break_prompts(segments, float(st.get("sun_exposure_s", 0.0)), app),
        "overcast": overcast_note(preference, cloud, kt),
        "weather": {
            "source": w.get("source"),
            "label": w.get("label"),
            "at": w.get("at"),
            "apparent_c": app,
            "uv_index": uv,
            "cloud_cover_pct": cloud,
            "shortwave_wm2": w.get("shortwave_wm2"),
            "clear_sky_index": kt,
        },
        "disclaimer": NOT_MEDICAL,
    }
