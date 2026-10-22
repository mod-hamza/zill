"""Heat model helpers (PRD 8.1 / 8.3)."""

from __future__ import annotations

import numpy as np

from zill import config

UV_MIN, UV_MAX, UV_EXP = 0.15, 1.0, 0.6


def uv_factor(alt_deg):
    """uv(alt) = clip(sin(alt)^0.6, 0.15, 1.0). Heuristic: low sun hurts less. Works on arrays."""
    s = np.sin(np.radians(np.asarray(alt_deg, dtype=float)))
    s = np.clip(s, 0.0, None)
    out = np.clip(np.power(s, UV_EXP), UV_MIN, UV_MAX)
    return float(out) if np.ndim(out) == 0 else out


def rhl_edge(t_s: float, sun: float, cls: str) -> float:
    """Relative Heat Load contribution of one traversal (PRD 8.3).

    indoor / ac_link: t * 0.1.  everything else (open and covered): t * (sun*1.0 + (1-sun)*0.35);
    covered edges have sun = 0, so they contribute t * 0.35.
    """
    if cls in ("indoor", "ac_link"):
        return t_s * config.RHL_INDOOR
    return t_s * (sun * config.RHL_SUN + (1.0 - sun) * config.RHL_SHADE)
