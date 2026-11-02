from __future__ import annotations
import ctypes
import json
import sys
from pathlib import Path
import traceback
from backend_runner import API_PREFIX, BASE_URL, wait_until_ready
from PyQt6.QtCore import (
    QEvent, QObject, QPoint, QRunnable, QSize, Qt, QThreadPool, QTimer, pyqtSignal,
)
from PyQt6.QtGui import QIcon, QImage, QKeySequence, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QButtonGroup, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPushButton,
    QMenu, QSplitter, QToolButton, QVBoxLayout, QWidget,
)
import httpx
import numpy as np

from click import group
from matplotlib.pyplot import box
from ui.panels.layer_statistics import MapBox
import Analysis
import file as file_tab
import Terrain_Editing
import Terrain_Mosaic
import Tools
import View
from ui.panels.icon_generator import icon, pixmap
from ui.panels.layer_statistics import (
    ContentsPane, InspectorPane, SampleWorkspace, SettingsForm,
)
from ui.panels.map_bar import MapSection

# order of the ribbon tabs
TAB_MODULES = [file_tab, View, Analysis, Tools, Terrain_Editing, Terrain_Mosaic]
DEFAULT_TAB = "Terrain Mosaic"
NOTE_TEXT = "AI-enabled Geospatial Terrain Analytics & Adaptive Modification"
PROJECT_TITLE = "Untitled"
APP_NAME ="GTAAM"


class _PixelSampleSignals(QObject):
    finished = pyqtSignal(object, object)


class _PixelSampleWorker(QRunnable):
    _http = httpx.Client(
        timeout=3.0,
        limits=httpx.Limits(max_connections=2, max_keepalive_connections=2),
    )

    def __init__(self, layer_id: str, row: int, col: int) -> None:
        super().__init__()
        self.layer_id = layer_id
        self.row = row
        self.col = col
        self.signals = _PixelSampleSignals()

    def run(self) -> None:
        try:
            with self._http.stream(
                "GET",
                f"{BASE_URL}{API_PREFIX}/file/add-data/layers/{self.layer_id}/pixel",
                params={"row": self.row, "col": self.col},
            ) as response:
                response.read()
                response.raise_for_status()
                result = response.json()
            self.signals.finished.emit(self, result)
        except Exception as exc:
            self.signals.finished.emit(self, exc)


def _wrap_label(text: str) -> str:
    """Two-line label for long ribbon captions."""
    if len(text) <= 12 or " " not in text:
        return text
    words = text.split(" ")
    best = min(range(1, len(words)),
               key=lambda i: abs(len(" ".join(words[:i])) - len(" ".join(words[i:]))))
    return " ".join(words[:best]) + "\n" + " ".join(words[best:])


# ----------------------------------------------------------------------------
# ribbon
# ----------------------------------------------------------------------------
class RibbonBar(QFrame):
    toolTriggered = pyqtSignal(dict)

    def __init__(self, is_on, is_available) -> None:
        super().__init__()
        self.setObjectName("ribbon")
        self.setFixedHeight(118)
        self._is_on = is_on
        self._is_available = is_available
        self._toggles: dict[str, QToolButton] = {}
        self._inner: QWidget | None = None
        self._outer = QVBoxLayout(self)
        self.backend_ids: dict[str,str]={}
        self._outer.setContentsMargins(0, 0, 0, 0)

    def show_tab(self, module) -> None:
        if self._inner is not None:
            self._inner.setParent(None)
            self._inner.deleteLater()
        self._toggles.clear()
        inner = QWidget()
        row = QHBoxLayout(inner)
        row.setContentsMargins(12, 6, 14, 6)
        row.setSpacing(0)
        for i, group in enumerate(module.GROUPS):
            if i:
                sep = QFrame()
                sep.setObjectName("ribbonSeparator")
                sep.setFixedWidth(1)
                row.addSpacing(8)
                row.addWidget(sep)
                row.addSpacing(8)
            row.addWidget(self._build_group(group))
        row.addStretch(1)


        self._outer.addWidget(inner)
        self._inner = inner
        self.refresh_checks()

    def _build_group(self, group: dict) -> QWidget:
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)
        tools_row = QHBoxLayout()
        tools_row.setSpacing(2)
        stack: QVBoxLayout | None = None
        for tool in group["tools"]:
            tool = dict(tool, group_label=group["label"])
            if tool.get("size") == "small":
                if stack is None or stack.count() >= 3:
                    stack = QVBoxLayout()
                    stack.setSpacing(2)
                    stack.setContentsMargins(0, 0, 0, 0)
                    tools_row.addLayout(stack)
                    tools_row.setAlignment(stack, Qt.AlignmentFlag.AlignVCenter)
                stack.addWidget(self._small_button(tool))
            else:
                stack = None
                tools_row.addWidget(self._large_button(tool))
        tools_row.addStretch(0)
        v.addLayout(tools_row, 1)
        label = QLabel(group["label"])
        label.setObjectName("ribbonLabel")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(label)
        return box

    def _wire(self, btn: QToolButton, tool: dict) -> None:
        btn.setToolTip(tool.get("tip") or tool["label"])
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda _=False, t=tool: self.toolTriggered.emit(t))
        if tool.get("kind") == "toggle":
            btn.setCheckable(True)
            self._toggles[tool["toggle"]] = btn

    def _large_button(self, tool: dict) -> QToolButton:
        b = QToolButton()
        b.setObjectName("ribbonButton")
        b.setText(_wrap_label(tool["label"]))
        b.setIcon(icon(tool["icon"], "#244557", 26))
        b.setIconSize(QSize(26,26))
        b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        b.setMinimumWidth(78)
        b.setFixedHeight(75)
        self._wire(b, tool)
        return b

    def _small_button(self, tool: dict) -> QToolButton:
        b = QToolButton()
        b.setObjectName("ribbonSmall")
        b.setText(tool["label"])
        b.setIcon(icon(tool["icon"], "#244557", 18))
        b.setIconSize(QSize(18, 18))
        b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        b.setMinimumWidth(138)
        b.setFixedHeight(23)
        self._wire(b, tool)
        return b

    def refresh_checks(self) -> None:
        for key, btn in self._toggles.items():
            btn.setEnabled(self._is_available(key))
            btn.blockSignals(True)
            btn.setChecked(bool(self._is_on(key)))
            btn.blockSignals(False)


# ----------------------------------------------------------------------------
# modal tool dialog (used for kind = "dialog")
# ----------------------------------------------------------------------------
class ToolDialog(QDialog):
    def __init__(self, parent, tool: dict, raster_names: list[str]) -> None:
        super().__init__(parent)
        self.setWindowTitle(tool["label"])
        self.setModal(True)
        self.setMinimumWidth(420)
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 18)
        v.setSpacing(14)
        head = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(pixmap(tool.get("icon", "grid"), "#1f6f9a", 26))
        title = QLabel(tool["label"])
        title.setObjectName("dialogTitle")
        head.addWidget(ic)
        head.addWidget(title, 1)
        v.addLayout(head)
        self.form = SettingsForm(tool.get("fields", []), raster_names)
        v.addWidget(self.form)
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.setObjectName("secondaryButton")
        cancel.clicked.connect(self.reject)
        ok = QPushButton(tool.get("run_label", "OK"))
        ok.setObjectName("primaryButton")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(ok)
        v.addLayout(row)


class ProjectNameDialog(QDialog):
    def __init__(self, project_name: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("projectNameDialog")
        self.setWindowTitle("Name the project")
        self.setModal(True)
        self.setMinimumWidth(440)
        self.project_name = ""
        self.setStyleSheet("""
            QDialog#projectNameDialog {
                background: #e4e7ea;
            }
            QFrame#projectNameCard {
                background: #f4f5f6;
                border: 1px solid #d0d4d8;
                border-radius: 12px;
            }
            QLabel#projectNameEyebrow {
                color: #6b737b;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 1px;
            }
            QLabel#projectNameHeading {
                color: #252a2f;
                font-size: 19px;
                font-weight: 700;
            }
            QLabel#projectNameDescription {
                color: #626a72;
                font-size: 12px;
            }
            QLineEdit#projectNameInput {
                background: #ffffff;
                color: #252a2f;
                border: 1px solid #c5cbd1;
                border-radius: 7px;
                padding: 9px 10px;
                selection-background-color: #68737d;
            }
            QLineEdit#projectNameInput:focus {
                border: 1px solid #68737d;
            }
            QLabel#projectNameError {
                color: #8b3f3f;
                font-size: 11px;
            }
            QPushButton#projectNameCancel {
                background: #e4e7ea;
                color: #343a40;
                border: 1px solid #cbd0d5;
                border-radius: 6px;
                padding: 7px 14px;
            }
            QPushButton#projectNameCancel:hover {
                background: #d9dde1;
            }
            QPushButton#projectNameSave {
                background: #495057;
                color: #f8f9fa;
                border: 1px solid #495057;
                border-radius: 6px;
                padding: 7px 16px;
                font-weight: 600;
            }
            QPushButton#projectNameSave:hover {
                background: #343a40;
                border-color: #343a40;
            }
        """)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)
        card = QFrame()
        card.setObjectName("projectNameCard")
        body = QVBoxLayout(card)
        body.setContentsMargins(22, 20, 22, 18)
        body.setSpacing(10)

        eyebrow = QLabel("PROJECT SETTINGS")
        eyebrow.setObjectName("projectNameEyebrow")
        heading = QLabel("Name your project")
        heading.setObjectName("projectNameHeading")
        description = QLabel("Choose a name that will be saved with this project.")
        description.setObjectName("projectNameDescription")
        description.setWordWrap(True)
        self.name_input = QLineEdit(project_name)
        self.name_input.setObjectName("projectNameInput")
        self.name_input.setPlaceholderText("Enter project name")
        self.name_input.selectAll()
        self.error_label = QLabel("Enter a project name to continue.")
        self.error_label.setObjectName("projectNameError")
        self.error_label.hide()

        body.addWidget(eyebrow)
        body.addWidget(heading)
        body.addWidget(description)
        body.addSpacing(4)
        body.addWidget(self.name_input)
        body.addWidget(self.error_label)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.setObjectName("projectNameCancel")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Save name")
        save.setObjectName("projectNameSave")
        save.setDefault(True)
        save.clicked.connect(self._accept_name)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        body.addSpacing(4)
        body.addLayout(buttons)
        outer.addWidget(card)
        self.name_input.returnPressed.connect(self._accept_name)

    def _accept_name(self) -> None:
        name = self.name_input.text().strip()
        if not name:
            self.error_label.show()
            self.name_input.setFocus()
            return
        self.project_name = name
        self.accept()


# ----------------------------------------------------------------------------
# main window
# ----------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{PROJECT_TITLE} - {APP_NAME}")  
        icon_path = Path(__file__).resolve().parent / "assets" / "gtaam_tool_icon.png"
        self.setWindowIcon(QIcon(str(icon_path)))
        self.resize(1480, 900)
        self.setMinimumSize(1040, 660)

        self.ws = SampleWorkspace()
        self.selected: str | None = None
        self.project_path: Path | None = None
        self.project_name = PROJECT_TITLE
        self.flags = {"contents": True, "statistics": True, "pixel_inspector": True,
                      "north_arrow": True, "scale_bar": True, "map_label": True,
                      "annotation": True}
        self._saved_sizes = [290, 900, 330]
        self._pixel_pool = QThreadPool(self)
        self._pixel_pool.setMaxThreadCount(1)
        self._pixel_request_in_flight = False
        self._pending_pixel_request: tuple[str, int, int] | None = None
        self._pixel_workers: set[_PixelSampleWorker] = set()

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_tabbar())
        self.ribbon = RibbonBar(self.is_on, self.is_available)
        self.ribbon.toolTriggered.connect(self.run_tool)
        root.addWidget(self.ribbon)
        root.addWidget(self._build_workspace(), 1)
        root.addWidget(self._build_statusbar())

        # overlays that float above everything
        self.toast = QLabel("", central)
        self.toast.setObjectName("toast")
        self.toast.hide()
        self._toast_timer = QTimer(self, singleShot=True)
        self._toast_timer.timeout.connect(self.toast.hide)

        QShortcut(QKeySequence("F11"), self, activated=self.act_fullscreen)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.act_save_project)
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self.act_open_project)
        QShortcut(QKeySequence("Esc"), self, activated=self._escape)

        self._connect_signals()
        self.select_tab(DEFAULT_TAB)
        self.on_layer_selected(None)
        QTimer.singleShot(0, self.map.canvas.fit)
        

    # ----- construction -----------------------------------------------------
    def _update_window_title(self) -> None:
        self.setWindowTitle(f"{self.project_name} - {APP_NAME}")

    def showEvent(self, e) -> None:
        super().showEvent(e)
        self._style_native_titlebar()

    def _style_native_titlebar(self) -> None:
        if sys.platform != "win32":
            return
        try:
            import ctypes
            from ctypes import wintypes
            hwnd = wintypes.HWND(int(self.winId()))

            def put(attr: int, value: int) -> None:
                v = ctypes.c_int(value)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attr, ctypes.byref(v), ctypes.sizeof(v))

            rgb = lambda r, g, b: r | (g << 8) | (b << 16)
            put(20, 0)                          # light mode: min/max/close icons dark ho jayenge
            put(35, rgb(0xF8, 0xF9, 0xFA))      # title bar colour (tab bar #e9ecef)
            put(36, rgb(0x21, 0x25, 0x29))      # title text colour
            put(34, rgb(0xCE, 0xD4, 0xDA))      # window border colour
        except Exception:
            pass

    def _build_tabbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("tabbar")
        h = QHBoxLayout(bar)
        h.setContentsMargins(10, 0, 14, 0)
        h.setSpacing(2)
        self.tab_group = QButtonGroup(self)
        self.tab_group.setExclusive(True)
        self.tab_buttons: dict[str, QPushButton] = {}
        for mod in TAB_MODULES:
            b = QPushButton(mod.TAB)
            b.setObjectName("tabButton")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, name=mod.TAB: self.select_tab(name))
            self.tab_group.addButton(b)
            self.tab_buttons[mod.TAB] = b
            h.addWidget(b)
        h.addStretch(1)

        bar.setFixedHeight(46)
        return bar

    def _build_workspace(self) -> QWidget:
        self.contents = ContentsPane(self.ws)
        self.map = MapSection(self.ws)
        self.inspector = InspectorPane(self.ws)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(5)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self.contents)
        self.splitter.addWidget(MapBox(self.map))
        self.splitter.addWidget(self.inspector)
        self.contents.setMinimumWidth(230)
        self.inspector.setMinimumWidth(270)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        self.splitter.setSizes(self._saved_sizes)
        return self.splitter

    def _build_statusbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("statusbar")
        bar.setFixedHeight(28)
        return bar 

    def _connect_signals(self) -> None:
        c, m, i = self.contents, self.map, self.inspector
        c.layerSelected.connect(self.on_layer_selected)
        c.visibilityChanged.connect(self.set_layer_visible)
        c.statisticsRequested.connect(lambda lid: self._show_stats_for(lid))
        c.zoomToLayerRequested.connect(self.map.canvas.zoom_to_layer)
      
        c.closeRequested.connect(lambda: self.set_flag("contents", False))
    
        i.closeRequested.connect(lambda: self.set_flag("statistics", False))
        i.showStatsRequested.connect(self.act_show_stats)
        i.opacityChanged.connect(self._opacity_changed)
        i.toolRun.connect(self.on_tool_run)
        i.toolCancelled.connect(self.act_show_stats)
        m.layersToggled.connect(lambda: self.toggle("contents"))
        m.statisticsToggled.connect(lambda: self.toggle("statistics"))
        m.discardPreview.connect(self.act_discard_preview)
        m.canvas.regionsChanged.connect(self._regions_changed)
        m.canvas.modeChanged.connect(self._mode_changed)
        m.canvas.statusMessage.connect(self.set_status)
        m.pixelSampleRequested.connect(self._request_pixel_sample)

    # ----- tabs / search ----------------------------------------------------
    def select_tab(self, name: str) -> None:
        for mod in TAB_MODULES:
            if mod.TAB == name:
                self.tab_buttons[name].setChecked(True)
                self.ribbon.show_tab(mod)
                self.current_tab = name
                return

    def _escape(self) -> None:
        self.map.canvas.cancel_draw()


    # ----- feedback ---------------------------------------------------------
    def show_toast(self, text: str, ms: int = 3000) -> None:
        self.toast.setText(text)
        self.toast.adjustSize()
        c = self.centralWidget()
        self.toast.move((c.width() - self.toast.width()) // 2, c.height() - self.toast.height() - 48)
        self.toast.show()
        self.toast.raise_()
        self._toast_timer.start(ms)

    def set_status(self, text: str) -> None:
        pass

    def api_post(self, path: str, payload: dict | None = None) -> dict:
        wait_until_ready()

        url = f"{BASE_URL}{API_PREFIX}{path}"

        try:
            response = httpx.post(
             url,
                json=payload or {},
                timeout=60
        )

            response.raise_for_status()

            if not response.content:
                raise RuntimeError(
                f"Backend returned an empty response for {url}"
            )

            try:
                data = response.json()
            except ValueError as e:
                raise RuntimeError(
                f"Backend returned invalid JSON: {response.text}"
            ) from e

            if not isinstance(data, dict):
                raise RuntimeError(
                f"Expected a JSON object, received: {data}"
            )

            return data

        except httpx.HTTPStatusError as e:
            raise RuntimeError(
            f"API error {e.response.status_code}: "
            f"{e.response.text}"
        ) from e

        except httpx.RequestError as e:
            raise RuntimeError(
            f"Backend connection failed: {e}"
        ) from e


    def api_get(self, path: str, params: dict | None = None) -> dict:
        wait_until_ready()
        url = f"{BASE_URL}{API_PREFIX}{path}"
        try:
            response = httpx.get(url, params=params, timeout=60)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"API error {e.response.status_code}: {e.response.text}") from e
        except httpx.RequestError as e:
            raise RuntimeError(f"Backend connection failed: {e}") from e

    def api_get_bytes(self, path: str) -> bytes:
        wait_until_ready()
        url = f"{BASE_URL}{API_PREFIX}{path}"
        try:
            response = httpx.get(url, timeout=60)
            response.raise_for_status()
            if not response.content:
                raise RuntimeError(f"Backend returned an empty response for {url}")
            return response.content
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"API error {e.response.status_code}: {e.response.text}") from e
        except httpx.RequestError as e:
            raise RuntimeError(f"Backend connection failed: {e}") from e

    def _request_pixel_sample(self, layer_id: str, row: int, col: int) -> None:
        request = (layer_id, row, col)
        if self._pixel_request_in_flight:
            self._pending_pixel_request = request
            return
        self._start_pixel_sample(request)

    def _start_pixel_sample(self, request: tuple[str, int, int]) -> None:
        layer_id, row, col = request
        worker = _PixelSampleWorker(layer_id, row, col)
        self._pixel_workers.add(worker)
        self._pixel_request_in_flight = True
        worker.signals.finished.connect(self._pixel_sample_finished)
        self._pixel_pool.start(worker)

    def _pixel_sample_finished(self, worker: _PixelSampleWorker, result: object) -> None:
        self._pixel_workers.discard(worker)
        self._pixel_request_in_flight = False
        is_current = (
            self.selected == worker.layer_id
            and self.map.is_pixel_sample_current(worker.layer_id, worker.row, worker.col)
        )
        if isinstance(result, Exception):
            if is_current:
                self.map.show_pixel_error(worker.layer_id, str(result))
        elif not isinstance(result, dict):
            if is_current:
                self.map.show_pixel_error(worker.layer_id, "Backend returned invalid pixel data.")
        else:
            self.map.cache_pixel_sample(worker.layer_id, worker.row, worker.col, result)
            if is_current:
                self.map.update_backend_pixel(worker.layer_id, result)

        pending = self._pending_pixel_request
        self._pending_pixel_request = None
        if pending is not None and self.map.is_pixel_sample_current(*pending):
            self._start_pixel_sample(pending)

    @staticmethod
    def _decode_raster_image(content: bytes) -> np.ndarray:
        image = QImage()
        if not image.loadFromData(content):
            raise RuntimeError("Backend returned an image that could not be decoded.")
        image = image.convertToFormat(QImage.Format.Format_RGBA8888)
        bits = image.bits()
        bits.setsize(image.sizeInBytes())
        return np.frombuffer(bits, dtype=np.uint8).reshape(
            image.height(), image.width(), 4
        ).copy()

    # ----- tool dispatch ----------------------------------------------------
    def raster_names(self) -> list[str]:
        return [l.name for l in self.ws.rasters()]

    def run_tool(self, tool: dict) -> None:
        kind = tool.get("kind", "toast")
        self.set_status(tool["label"])
        if kind == "action":
            fn = getattr(self, "act_" + tool["action"], None)
            if fn is None:
                self.show_toast(f"{tool['label']}: backend not connected in this interface preview")
            else:
                try:
                    fn()
                except Exception as e:
                    self.show_toast(f"{tool['label']}: error occurred while running the tool")
        elif kind == "toggle":
            self.toggle(tool["toggle"])
        elif kind == "panel":
            self.set_flag("statistics", True)
            self.inspector.show_tool(tool, self.raster_names())
        elif kind == "dialog":
            dlg = ToolDialog(self, tool, self.raster_names())
            if dlg.exec() == QDialog.DialogCode.Accepted:
                self.on_tool_run(tool, dlg.form.values())
        else:
            self.show_toast(tool["label"])

    def on_tool_run(self, tool: dict, values: dict) -> None:
        handler = tool.get("handler")
        fn = getattr(self, "run_" + handler, None) if handler else None
        if fn:
            try:
                fn(tool, values)
            except Exception as e:
                traceback.print_exc()
                self.show_toast(f"{tool['label']}: {e}")
                return
        else:
            self.show_toast(f"{tool['label']}: backend not connected in this interface preview")
        self.set_status(f"{tool['label']} (preview)")

    # handlers for tools that have a visible effect in the frontend
    def run_ramp(self, tool: dict, values: dict) -> None:
        self.ws.apply_ramp(values["ramp"])
        self.map.canvas.invalidate()
        self.contents.refresh_legend()
        if self.selected:
            self._show_stats_for(self.selected)
        self.show_toast(f"Colour ramp: {values['ramp']}")

    def run_preview_edit(self, tool: dict, values: dict) -> None:
        self.act_preview_edit()

    def run_select_dems(self, tool: dict, values: dict) -> None:
        chosen = values.get("dems", [])
        for lyr in self.ws.rasters():
            if lyr.id in ("dem", "east"):
                self.set_layer_visible(lyr.id, lyr.name in chosen)
                self.contents.set_visible(lyr.id, lyr.name in chosen)
        self.map.canvas.fit()
        self.show_toast(f"{len(chosen)} DEM{'s' if len(chosen) != 1 else ''} selected for the mosaic")

    def run_terrain_derivative(self, tool: dict, values: dict) -> None:
        source_name = values.get("input_dem")
        source = next(
            (layer for layer in self.ws.rasters() if layer.name == source_name),
            None,
        )
        if source is None:
            raise ValueError("Load a raster DEM before running this analysis.")

        payload = {"layer_id": source.id}
        tool_id = tool["id"]
        routes = {
            "an-hillshade": ("/analysis/surface-analysis/hillshade", "hillshade"),
            "an-slope": ("/analysis/surface-analysis/slope", "slope"),
            "an-aspect": ("/analysis/surface-analysis/aspect", "aspect"),
            "an-curvature": ("/analysis/surface-analysis/curvature", "curvature"),
            "an-contours": ("/analysis/terrain-derivatives/contours", "contours"),
        }
        try:
            route, operation = routes[tool_id]
        except KeyError as exc:
            raise ValueError(f"Unsupported terrain analysis: {tool_id}") from exc

        if operation == "hillshade":
            payload.update({
                "azimuth": values["azimuth"],
                "altitude": values["altitude"],
                "z_factor": values["z_factor"],
            })
        elif operation == "slope":
            units = values["output_units"]
            payload["units"] = "percent" if units == "Percent rise" else "degrees"
        elif operation == "aspect":
            payload["flat_as_minus_one"] = values["flat_areas_as_-1"]
        elif operation == "contours":
            payload.update({
                "interval": values["interval"],
                "base": values["base_elevation"],
            })

        result = self.api_post(route, payload)
        info = result.get("layer")
        if not isinstance(info, dict):
            raise RuntimeError("Backend did not return a derived layer.")
        layer_id = info.get("id")
        layer_name = info.get("name")
        if not isinstance(layer_id, str) or not layer_id:
            raise RuntimeError("Backend returned a derived layer without an id.")
        if not isinstance(layer_name, str) or not layer_name:
            raise RuntimeError("Backend returned a derived layer without a name.")

        if operation == "contours":
            geojson = self.api_get(f"/file/add-data/layers/{layer_id}/geojson")
            layer = self.ws.add_contour_layer(layer_id, layer_name, geojson, source)
        else:
            ramp = {
                "hillshade": "greys",
                "slope": "slope",
                "aspect": "viridis",
                "curvature": "diverging",
            }[operation]
            rgba = self._decode_raster_image(
                self.api_get_bytes(f"/file/export/map-image/{layer_id}?ramp={ramp}")
            )
            stats_result = self.api_get(f"/file/export/statistics/{layer_id}")
            histogram_result = self.api_get(
                f"/analysis/quality-statistics/histogram/{layer_id}",
                {"bins": 30},
            )
            stats = {
                "min": stats_result["min"],
                "max": stats_result["max"],
                "mean": stats_result["mean"],
                "std": stats_result["std_dev"],
                "median": stats_result["median"],
                "count": stats_result["count"],
                "nodata_count": stats_result["nodata_count"],
                "hist": np.asarray(histogram_result["counts"]),
                "edges": np.asarray(histogram_result["bin_edges"]),
            }
            layer = self.ws.add_raster_image(
                layer_id,
                layer_name,
                rgba,
                f"Derived from {source.name}",
                info,
                stats,
            )

        self.contents.rebuild()
        self.map.canvas.invalidate()
        self.on_layer_selected(layer.id)
        self.map.canvas.fit()
        feature_count = result.get("extra", {}).get("feature_count")
        if operation == "contours":
            self.show_toast(f"Contours created · {feature_count} levels")
        else:
            self.show_toast(f"{tool['label']} created · {layer.name}")

    # ----- toggles / panes --------------------------------------------------
    def is_on(self, key: str) -> bool:
        if key.startswith("layer:"):
            try:
                return self.ws.layer(key[6:]).visible
            except KeyError:
                return False
        return self.flags.get(key, False)

        #..............changed the functionality to make it clickable for all the layers rather than adding a backend......................
    def is_available(self, key: str) -> bool:
        return True

    def toggle(self, key: str) -> None:
        if key.startswith("layer:"):
            lid = key[6:]
            try:
                on = not self.ws.layer(lid).visible
            except KeyError:
                self.show_toast("No layer loaded yet · connect data to enable this")
                return
            self.set_layer_visible(lid, on)
            self.contents.set_visible(lid, on)
        else:
            self.set_flag(key, not self.flags[key])

    def set_flag(self, key: str, on: bool) -> None:
        self.flags[key] = on
        if key in ("contents", "statistics"):
            pane = self.contents if key == "contents" else self.inspector
            was_hidden = pane.isHidden()
            if not on and not was_hidden:
                sizes = self.splitter.sizes()
                if all(sizes):
                    self._saved_sizes = sizes
            pane.setVisible(on)
            if on and was_hidden:
                self.splitter.setSizes(self._saved_sizes if all(self._saved_sizes) else [290, 900, 330])
            if key == "statistics" and on and self.inspector.stack.currentWidget() is self.inspector.tool_scroll:
                if self.selected and self.ws.has_layer(self.selected):
                    self.inspector.show_layer(self.ws.layer(self.selected))
                else:
                    self.inspector.show_empty_state()
            self.map.set_pane_buttons(self.flags["contents"], self.flags["statistics"])
        else:
            self.map.set_element_visible(key, on)
        self.ribbon.refresh_checks()

    def set_layer_visible(self, lid: str, on: bool) -> None:
        self.ws.layer(lid).visible = on
        self.map.canvas.update()
        self.ribbon.refresh_checks()
        self.map.refresh_pixel()

    def _opacity_changed(self, lid: str, value: int) -> None:
        self.ws.layer(lid).opacity = value
        self.map.canvas.update()

    # ----- layers -----------------------------------------------------------
    def on_layer_selected(self, lid: str | None) -> None:
        if lid is None:
            self.selected = None
            self.contents.select("")
            self.map.set_selected_layer(None)
            self.inspector.show_empty_state()
            return

        self.selected = lid
        lyr = self.ws.layer(lid)
        if lyr.group == "raster" and lyr.user_added and not lyr.visible:
            self.set_layer_visible(lid, True)
            self.contents.set_visible(lid, True)
            self.map.canvas.zoom_to_layer(lid)
        self.contents.select(lid)
        self.map.set_selected_layer(lid)
        self.inspector.show_layer(lyr)

    def _show_stats_for(self, lid: str | None) -> None:
        if not lid or not any(l.id == lid for l in self.ws.layers):
            self.set_flag("statistics", True)
            self.inspector._show_empty_state()
            return
        self.set_flag("statistics", True)
        self.inspector.show_layer(self.ws.layer(lid))

    def _regions_changed(self) -> None:
        n = len(self.ws.regions)
        self.contents.set_sub("regions", f"{n} polygon{'s' if n != 1 else ''}")
        if self.selected == "regions":
            self.inspector.show_layer(self.ws.layer("regions"))

    def _mode_changed(self, mode: str) -> None:
        pass

    # ----- actions (referenced by tool["action"]) ---------------------------
    def act_mode_explore(self) -> None:
        self.map.canvas.set_mode("explore")

    def act_mode_select(self) -> None:
        self.map.canvas.set_mode("select")

    def act_draw_region(self) -> None:
        self.ws.layer("regions").visible = True
        self.contents.set_visible("regions", True)
        self.map.canvas.set_mode("draw")
        self.map.canvas.setFocus()

    def act_delete_region(self) -> None:
        if not self.map.canvas.delete_selected():
            self.show_toast("Select a region first (Select Region tool)")

    def act_clear_regions(self) -> None:
        self.map.canvas.clear_regions()
        self.show_toast("All editing regions removed")

    def act_zoom_in(self) -> None:
        self.map.canvas.zoom_by(1.5)

    def act_zoom_out(self) -> None:
        self.map.canvas.zoom_by(1 / 1.5)

    def act_full_extent(self) -> None:
        self.map.canvas.fit()

    def act_zoom_selected(self) -> None:
        if not self.selected:
            self.show_toast("Select a layer first")
            return
        self.map.canvas.zoom_to_layer(self.selected)

    def act_show_stats(self) -> None:
        self._show_stats_for(self.selected)

    def act_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def act_exit_app(self) -> None:
        self.close()

    def act_preview_edit(self) -> None:
        if not self.ws.regions:
            self.show_toast("Draw at least one editing region first")
            return
        self.map.canvas.set_preview("edit")
        self.map.show_preview("Modification preview")

    def act_preview_mosaic(self) -> None:
        for lid in ("dem", "east"):
            self.set_layer_visible(lid, True)
            self.contents.set_visible(lid, True)
        self.map.canvas.fit()
        self.map.canvas.set_preview("mosaic")
        self.map.show_preview("Mosaic preview")

    def act_discard_preview(self) -> None:
        self.map.canvas.set_preview(None)
        self.map.show_preview(None)
        self.show_toast("Preview discarded")

    def _refresh_everything(self) -> None:
        self.map.canvas.invalidate()
        self.contents.rebuild()
        self.map.update_annotation()
        self.map.canvas.set_preview(None)
        self.map.show_preview(None)
        self.map.canvas.set_mode("explore")
        self.on_layer_selected(self.ws.layers[0].id if self.ws.layers else None)
        self.ribbon.refresh_checks()
        self.map.canvas.fit()

    def act_reset_workspace(self) -> None:
        self.ws.reset()
        self._refresh_everything()
        self.show_toast("Sample workspace restored")

    def act_new_project(self) -> None:
        name = "Untitled project"

        try:
            info = self.api_post(
            "/file/project/new",
            {"name": name}
            )

            self.project_name = info.get("name", name)
            self.project_path = None
            self.ws.reset()

            self.setWindowTitle(
            f"{self.project_name} - GTAAM"
            )

            self._update_window_title()
            self._refresh_everything()

            self.show_toast("New project created")

        except Exception as e:
            traceback.print_exc()
            self.show_toast(f"New project failed: {e}")

    def act_name_project(self) -> None:
        dialog = ProjectNameDialog(self.project_name, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        name = dialog.project_name
        self.project_name = name
        self.project_label.setText(name)
        if self.project_path is not None:
            self._write_project(self.project_path)
        else:
            self.show_toast("Project renamed · save the project to keep this name")

    def _project_state(self) -> dict:
        c = self.map.canvas
        return {
            "app": "A-GTAAM", "version": 1, "name": self.project_name,
            "ramp": self.ws.ramp_name,
            "layers": {l.id: {"visible": l.visible, "opacity": l.opacity} for l in self.ws.layers},
            "regions": [[list(p) for p in poly] for poly in self.ws.regions],
            "view": {"scale": c.scale, "ox": c.ox, "oy": c.oy},
        }

    def act_save_project(self) -> None:
        if self.project_path is None:
            self.act_save_project_as()
            return
        self._write_project(self.project_path)

    def act_save_project_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save project", f"{self.project_name}.json",
                                              "A-GTAAM project (*.json)")
        if path:
            self.project_path = Path(path)
            self._write_project(self.project_path)

    def _write_project(self, path: Path) -> None:
        try:
            path.write_text(json.dumps(self._project_state(), indent=2), encoding="utf-8")
            self.project_label.setText(self.project_name)
            self.show_toast(f"Project saved · {path.name}")
        except OSError as exc:
            QMessageBox.warning(self, "Save project", str(exc))

    def act_open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open project", "", "A-GTAAM project (*.json)")
        if not path:
            return
        try:
            state = json.loads(Path(path).read_text(encoding="utf-8"))
            if state.get("app") != "A-GTAAM":
                raise ValueError("This file is not an A-GTAAM project.")
            self.ws.reset()
            self.ws.apply_ramp(state.get("ramp", "Hypsometric"))
            for lid, s in state.get("layers", {}).items():
                try:
                    lyr = self.ws.layer(lid)
                    lyr.visible, lyr.opacity = bool(s["visible"]), int(s["opacity"])
                except (KeyError, TypeError):
                    pass
            self.ws.regions = [[tuple(p) for p in poly] for poly in state.get("regions", [])]
            self.project_path = Path(path)
            self.project_name = state.get("name", Path(path).stem)
            self.project_label.setText(self.project_name)
            self._refresh_everything()
            self._regions_changed()
            v = state.get("view")
            if v:
                c = self.map.canvas
                c.scale, c.ox, c.oy = v["scale"], v["ox"], v["oy"]
                c.update()
                c.viewChanged.emit()
            self.show_toast(f"Project opened · {Path(path).name}")
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            QMessageBox.warning(self, "Open project", f"Could not open project:\n{exc}")

    # --- add data ------------------------------------------------------------
    def _add_data(
        self,
        title: str,
        file_filter: str,
        kind: str
    ) -> None:

    # 1. Open file selection dialog
        file_path, _ = QFileDialog.getOpenFileName(
        self,
        title,
        "",
        file_filter
    )

    # User cancelled file selection
        if not file_path:
            return

        try:
        # 2. Extract filename without extension
            file_name = Path(file_path).stem

        # 3. Prepare API payload
            payload = {
            "path": file_path,
            "name": file_name
        }

        # 4. Call FastAPI endpoint
            if kind == "raster":
                info = self.api_post(
                "/file/add-data/raster",
                payload
            )
            else:
                raise ValueError(
                f"Unsupported data type: {kind}"
            )

            if kind == "raster":
                layer_id = info.get("id")
                if not isinstance(layer_id, str) or not layer_id:
                    raise RuntimeError("Backend did not return a raster layer id.")
                png = self.api_get_bytes(f"/file/export/map-image/{layer_id}")
                rgba = self._decode_raster_image(png)
                stats_result = self.api_get(f"/file/export/statistics/{layer_id}")
                histogram_result = self.api_get(
                    f"/analysis/quality-statistics/histogram/{layer_id}",
                    {"bins": 30},
                )
                stats = {
                    "min": stats_result["min"],
                    "max": stats_result["max"],
                    "mean": stats_result["mean"],
                    "std": stats_result["std_dev"],
                    "median": stats_result["median"],
                    "count": stats_result["count"],
                    "nodata_count": stats_result["nodata_count"],
                    "hist": np.asarray(histogram_result["counts"]),
                    "edges": np.asarray(histogram_result["bin_edges"]),
                }
                layer = self.ws.add_raster_image(
                    layer_id,
                    info.get("name", file_name),
                    rgba,
                    file_path,
                    info,
                    stats,
                )
                self.contents.rebuild()
                self.map.canvas.invalidate()
                self.on_layer_selected(layer.id)
                self.map.canvas.fit()

            self.show_toast(f"Raster added successfully: {file_name}")

        except Exception as e:
            traceback.print_exc()
            self.show_toast(f"Add raster failed: {e}")

    def act_add_raster(self) -> None:
        self._add_data("Add raster", "Raster (*.tif *.tiff *.img *.asc);;All files (*)", "raster")

    def act_add_vector(self) -> None:
        self._add_data("Add vector", "Vector (*.shp *.geojson *.json *.gpkg);;All files (*)", "vector")

    def act_add_basemap(self) -> None:
        self._add_data("Add basemap", "Basemap (*.tif *.tiff *.png *.jpg);;All files (*)", "basemap")

    def act_export_image(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export map image", "terrain_map.png",
                                              "PNG image (*.png);;JPEG image (*.jpg *.jpeg)")
        if path:
            ok = self.map.surface.grab().save(path)
            self.show_toast(f"Map image saved · {Path(path).name}" if ok else "Could not save the image")
