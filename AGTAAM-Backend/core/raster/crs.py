"""Just enough coordinate-system knowledge to get real-world (metre) cell sizes.

Slope, aspect, hillshade and curvature need cell size in metres. AW3D30 tiles are in
degrees (EPSG:4326), so a pixel is ~30 m tall but narrower than 30 m east-west.
"""
from __future__ import annotations

import math

from .model import Raster

_GEOGRAPHIC_EPSG = {4326, 4269, 4258, 4283, 4167, 4612, 4979, 4617, 4019, 4030}
M_PER_DEG_LAT = 110_574.0
M_PER_DEG_LON_EQ = 111_320.0


def is_geographic(raster: Raster) -> bool:
    crs = (raster.crs or "").strip()
    up = crs.upper()
    if up.startswith("EPSG:"):
        try:
            return int(up.split(":")[1]) in _GEOGRAPHIC_EPSG
        except ValueError:
            pass
    if "PROJCS" in up or "PROJCRS" in up:
        return False
    if "GEOGCS" in up or "GEOGCRS" in up:
        return True
    # unknown: guess from the extent
    minx, miny, maxx, maxy = raster.bounds
    return max(abs(minx), abs(maxx)) <= 180 and max(abs(miny), abs(maxy)) <= 90


def epsg_code(raster: Raster) -> int | None:
    up = (raster.crs or "").upper()
    if up.startswith("EPSG:"):
        try:
            return int(up.split(":")[1])
        except ValueError:
            return None
    return None


def cell_size_meters(raster: Raster) -> tuple[float, float]:
    """(dx, dy) of one pixel in metres."""
    if is_geographic(raster):
        lat = (raster.bounds[1] + raster.bounds[3]) / 2
        return (raster.pixel_w * M_PER_DEG_LON_EQ * math.cos(math.radians(lat)),
                raster.pixel_h * M_PER_DEG_LAT)
    return raster.pixel_w, raster.pixel_h
