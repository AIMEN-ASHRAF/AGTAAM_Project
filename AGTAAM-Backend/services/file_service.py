"""File tab logic: projects, adding data, exporting, workspace."""
from __future__ import annotations

import csv
import io
import json
import math
from pathlib import Path

from core.raster._deps import require_rasterio
from core.raster.reader import read_raster
from core.raster.writer import write_geotiff
from core.render.map_image import render_png
from core.stats import layer_stats
from config import get_settings
from shared.errors import BadRequest
from shared.layer_store import (Layer, add_raster_layer, add_vector_layer, get_raster_layer,
                                    layer_store)
from shared.project_store import project


# ---- project ----
def project_info() -> dict:
    return project.info()


def new_project(name: str) -> dict:
    project.new(name)
    return project.info()


def open_project(path: str) -> dict:
    return project.load(path)


def save_project(path: str | None) -> dict:
    return project.save(path)


# ---- add data ----
def add_raster(path: str, name: str | None) -> dict:
    raster = read_raster(path)
    return add_raster_layer(raster, name or Path(path).stem, source=str(Path(path))).info()


def add_vector(path: str, name: str | None) -> dict:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Vector file not found: {path}")
    if p.suffix.lower() not in (".geojson", ".json"):
        raise BadRequest("Only GeoJSON (.geojson / .json) vectors are supported for now.",
                         code="unsupported_format")
    data = json.loads(p.read_text(encoding="utf-8"))
    if data.get("type") not in ("FeatureCollection", "Feature", "GeometryCollection"):
        raise BadRequest("That file is not valid GeoJSON.", code="bad_geojson")
    return add_vector_layer(data, name or p.stem, source=str(p)).info()


def add_basemap(name: str, url_template: str, attribution: str | None) -> dict:
    layer = Layer(name=name, kind="basemap", source=url_template,
                  meta={"attribution": attribution} if attribution else {})
    return layer_store.add(layer).info()


def list_layers() -> list[dict]:
    return [l.info() for l in layer_store.list()]


def update_layer(layer_id: str, fields: dict) -> dict:
    return layer_store.update(layer_id, **fields).info()


def reorder_layers(ids: list[str]) -> list[dict]:
    layer_store.reorder(ids)
    return list_layers()


def remove_layer(layer_id: str) -> None:
    layer_store.remove(layer_id)


def layer_geojson(layer_id: str) -> dict:
    layer = layer_store.get(layer_id)
    if layer.geojson is None:
        raise BadRequest("This layer has no vector data.", code="not_a_vector")
    return layer.geojson


# ---- export ----
def map_image(layer_id: str, ramp: str, vmin: float | None, vmax: float | None,
              max_pixels: int | None) -> bytes:
    raster = get_raster_layer(layer_id).raster
    limit = min(max_pixels or get_settings().max_png_pixels, get_settings().max_png_pixels)
    return render_png(raster, ramp, vmin, vmax, limit)


def export_elevations(layer_id: str, path: str) -> dict:
    raster = get_raster_layer(layer_id).raster
    return {"path": write_geotiff(raster, path)}


def statistics(layer_id: str, fmt: str):
    layer = get_raster_layer(layer_id)
    stats = {"layer": layer.name, **layer_stats.compute(layer.raster.data)}
    if fmt == "json":
        return stats
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(stats.keys())
    w.writerow(stats.values())
    return buf.getvalue()


def pixel_value(layer_id: str, row: int, col: int) -> dict:
    raster = get_raster_layer(layer_id).raster
    if row < 0 or col < 0 or row >= raster.height or col >= raster.width:
        raise BadRequest("Pixel row or column is outside the raster.", code="pixel_out_of_bounds")
    value = float(raster.data[row, col])
    x, y = raster.rowcol_to_xy(row, col)
    coordinate_unit = "map units"
    x_label, y_label = "Easting", "Northing"
    if raster.crs:
        rasterio = require_rasterio()
        crs = rasterio.crs.CRS.from_string(raster.crs)
        if crs.is_geographic:
            coordinate_unit = "°"
            x_label, y_label = "Longitude", "Latitude"
        elif crs.axis_info:
            coordinate_unit = crs.axis_info[0].unit_name
    return {
        "row": row,
        "col": col,
        "value": value if math.isfinite(value) else None,
        "x": float(x),
        "y": float(y),
        "crs": raster.crs,
        "coordinate_unit": coordinate_unit,
        "x_label": x_label,
        "y_label": y_label,
    }


# ---- workspace ----
def reset_workspace() -> dict:
    project.reset_workspace()
    return project.workspace


def set_fullscreen(enabled: bool) -> dict:
    project.workspace["fullscreen"] = enabled
    return {"fullscreen": enabled}


def exit_info() -> dict:
    return {"ok": True, "unsaved_changes": project.is_dirty(), "project": project.name}
