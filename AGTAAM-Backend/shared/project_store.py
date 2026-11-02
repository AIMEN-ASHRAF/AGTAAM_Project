"""The current project: its name, workspace state, and save/open as a .json file."""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

from core.raster.reader import read_raster
from shared.errors import BadRequest
from shared.layer_store import Layer, layer_store

FORMAT = "A-GTAAM-project"
FORMAT_VERSION = 1


def default_workspace() -> dict:
    return copy.deepcopy({
        "mode": "explore",
        "fullscreen": False,
        "panes": {"contents": True, "statistics": True, "pixel_inspector": True},
        "viewport": {"center": None, "scale": None},
        "appearance": {"north_arrow": True, "scale_bar": True, "layer_label": False,
                       "colour_ramp": "terrain"},
        "display": {"regions": True, "reference_grid": False, "annotation": False},
        "annotations": [],
        "options": {"units": "metric", "decimals": 2, "default_ramp": "terrain"},
    })


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ProjectStore:
    def __init__(self) -> None:
        self.reset()

    def reset(self, name: str = "Untitled project") -> None:
        self.name = name
        self.path: str | None = None
        self.created = _now()
        self.workspace = default_workspace()
        self._saved_version = layer_store.version

    def is_dirty(self) -> bool:
        return layer_store.version != self._saved_version

    def info(self) -> dict:
        return {"name": self.name, "path": self.path, "dirty": self.is_dirty(),
                "layer_count": len(layer_store.list()), "created": self.created}

    def new(self, name: str) -> None:
        layer_store.clear()
        self.reset(name)

    def reset_workspace(self) -> None:
        self.workspace = default_workspace()

    # ---- save / open ----
    def save(self, path: str | None = None) -> dict:
        target = path or self.path
        if not target:
            raise BadRequest("No file path yet - use Save As.", code="no_path")
        target_p = Path(target)
        if target_p.suffix.lower() != ".json":
            target_p = target_p.with_suffix(".json")
        saved, skipped = [], []
        for layer in reversed(layer_store.list()):          # bottom first
            if layer.source is None:
                skipped.append(layer.name)                  # derived layers have no file yet
                continue
            saved.append({"id": layer.id, "name": layer.name, "kind": layer.kind,
                          "source": layer.source, "visible": layer.visible,
                          "opacity": layer.opacity, "meta": layer.meta})
        doc = {"format": FORMAT, "version": FORMAT_VERSION, "name": self.name,
               "created": self.created, "saved": _now(), "workspace": self.workspace,
               "layers": saved}
        target_p.parent.mkdir(parents=True, exist_ok=True)
        target_p.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        self.path = str(target_p)
        self._saved_version = layer_store.version
        return {**self.info(), "saved_layers": len(saved), "skipped_layers": skipped}

    def load(self, path: str) -> dict:
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(f"Project file not found: {path}")
        doc = json.loads(p.read_text(encoding="utf-8"))
        if doc.get("format") != FORMAT:
            raise BadRequest("This is not an A-GTAAM project file.", code="bad_project_file")
        layer_store.clear()
        missing = []
        for entry in doc.get("layers", []):                 # bottom first, so add() stacks right
            src = entry.get("source")
            kind = entry["kind"]
            try:
                layer = Layer(id=entry["id"], name=entry["name"], kind=kind, source=src,
                              visible=entry.get("visible", True),
                              opacity=entry.get("opacity", 1.0), meta=entry.get("meta", {}))
                if kind == "raster":
                    layer.raster = read_raster(src)
                elif kind == "vector":
                    layer.geojson = json.loads(Path(src).read_text(encoding="utf-8"))
                layer_store.add(layer)
            except (FileNotFoundError, OSError, ValueError):
                missing.append(entry.get("name", src))
        self.name = doc.get("name", p.stem)
        self.created = doc.get("created", _now())
        self.workspace = {**default_workspace(), **doc.get("workspace", {})}
        self.path = str(p)
        self._saved_version = layer_store.version
        return {**self.info(), "missing_layers": missing}


project = ProjectStore()
