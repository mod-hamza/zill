"""Typed places: full name index, search, one-line parsing and an optional online fallback."""

from __future__ import annotations

from zill.places.fold import fold
from zill.places.index import PlaceIndex, get_index, get_place
from zill.places.parse import parse_text

__all__ = ["PlaceIndex", "fold", "get_index", "get_place", "parse_text"]
