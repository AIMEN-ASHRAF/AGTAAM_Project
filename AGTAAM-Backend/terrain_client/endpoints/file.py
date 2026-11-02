from __future__ import annotations

from ..http import clean
from .base import Endpoints


class FileApi(Endpoints):
    """File tab: Project, Add Data, Export, Workspace."""

    # ---- Project ----
    def project_info(self) -> dict:
        return self._h.get("/file/project")

    def new_project(self, name: str = "Untitled project") -> dict:
        return self._h.post("/file/project/new", json={"name": name})

    def open_project(self, path: str) -> dict:
        """Returns the project info plus `missing_layers` (files that could not be found)."""
        return self._h.post("/file/project/open", json={"path": path})

    def save_project(self, path: str | None = None) -> dict:
        """Save over the current file (or to `path`). Reply has `skipped_layers`."""
        return self._h.post("/file/project/save", json={"path": path})

    def save_project_as(self, path: str) -> dict:
        return self._h.post("/file/project/save-as", json={"path": path})

    # ---- Add Data ----
    def add_raster(self, path: str, name: str | None = None) -> dict:
        """Load a DEM. Returns the layer info (use its "id" for every other call)."""
        return self._h.post("/file/add-data/raster", json=clean({"path": path, "name": name}))

    def add_vector(self, path: str, name: str | None = None) -> dict:
        return self._h.post("/file/add-data/vector", json=clean({"path": path, "name": name}))

    def add_basemap(self, name: str, url_template: str, attribution: str | None = None) -> dict:
        return self._h.post("/file/add-data/basemap",
                            json=clean({"name": name, "url_template": url_template,
                                        "attribution": attribution}))

    def layers(self) -> list[dict]:
        """All layers, top of the drawing order first (feeds the Layers panel)."""
        return self._h.get("/file/add-data/layers")

    def reorder_layers(self, layer_ids: list[str]) -> list[dict]:
        return self._h.put("/file/add-data/layers/order", json={"layer_ids": layer_ids})

    def update_layer(self, layer_id: str, *, name: str | None = None, visible: bool | None = None,
                     opacity: float | None = None) -> dict:
        return self._h.patch(f"/file/add-data/layers/{layer_id}",
                             json=clean({"name": name, "visible": visible, "opacity": opacity}))

    def remove_layer(self, layer_id: str) -> dict:
        return self._h.delete(f"/file/add-data/layers/{layer_id}")

    def layer_geojson(self, layer_id: str) -> dict:
        """The lines/features of a vector layer (e.g. contours, seamline)."""
        return self._h.get(f"/file/add-data/layers/{layer_id}/geojson")

    # ---- Export ----
    def map_image(self, layer_id: str, ramp: str = "terrain", vmin: float | None = None,
                  vmax: float | None = None, max_pixels: int | None = None) -> bytes:
        """PNG bytes. In Qt: QPixmap.loadFromData(png)."""
        return self._h.get(f"/file/export/map-image/{layer_id}", expect="bytes",
                           params={"ramp": ramp, "vmin": vmin, "vmax": vmax, "max_pixels": max_pixels})

    def export_elevations(self, layer_id: str, path: str) -> dict:
        return self._h.post("/file/export/elevations", json={"layer_id": layer_id, "path": path})

    def statistics(self, layer_id: str, fmt: str = "json"):
        """fmt="json" -> dict, fmt="csv" -> str."""
        return self._h.get(f"/file/export/statistics/{layer_id}", params={"format": fmt},
                           expect="text" if fmt == "csv" else "json")

    # ---- Workspace ----
    def reset_workspace(self) -> dict:
        return self._h.post("/file/workspace/reset")

    def set_fullscreen(self, enabled: bool) -> dict:
        return self._h.put("/file/workspace/fullscreen", json={"enabled": enabled})

    def exit_app(self) -> dict:
        """Ask whether there are unsaved changes: {"unsaved_changes": bool, ...}."""
        return self._h.post("/file/workspace/exit")
