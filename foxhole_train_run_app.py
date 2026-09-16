from __future__ import annotations

import base64
import html
import io
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import qrcode
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QFrame,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from FoxholeGlobalMapGenerationStandalone import load_live_overlay_data, load_local_layout_data, ping_live1_api

APP_TITLE = "Foxhole Train Run Maker"
WINDOW_SIZE = (1300, 720)
PROJECT_ROOT = Path(__file__).resolve().parent
HEX_MAPS_DIR = PROJECT_ROOT / "Hex Maps"
CARGO_ITEMS_PATH = HEX_MAPS_DIR / "cargo_items.txt"
CARGO_MANIFEST_SCHEMA = "cmrc.cargo_manifest.v1"

TEAM_COLORS = {
    "COLONIALS": QColor("#22c55e"),
    "WARDENS": QColor("#3b82f6"),
    "NONE": QColor("#e5e7eb"),
}

BASE_CIRCLE_RADIUS = 1.5


def clean_region_name(raw_name: str) -> str:
    """Format raw hex region names (e.g. 'BasinSionnachHex') into clean display names ('Basin Sionnach')."""
    if not raw_name:
        return "Unknown Region"
    name = str(raw_name).strip()
    if name.endswith("Hex"):
        name = name[:-3]
    import re
    formatted = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', name)
    formatted = re.sub(r'(?<=[A-Z])(?=[A-Z][a-z])', ' ', formatted)
    return formatted.strip()


def build_blocks_from_steps(steps: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Group consecutive steps by hex into blocks matching the reference HTML logic."""
    blocks: list[dict[str, Any]] = []
    for s in steps:
        if not blocks or blocks[-1]["hex"] != s["hex"]:
            blocks.append({"hex": s["hex"], "regions": []})
        blocks[-1]["regions"].append(s["region"])
    return blocks


def build_input_log(steps: list[dict[str, str]]) -> str:
    """Build input log text block."""
    lines = ["INPUT LOG (in order):\n"]
    for i, s in enumerate(steps):
        lines.append(f"{i + 1}. {s['hex']}; {s['region']}")
    return "\n".join(lines)


def build_diagram_text(blocks: list[dict[str, Any]]) -> str:
    """Build ASCII train diagram text block matching the reference HTML logic."""
    lines = ["TRAIN DIAGRAM\n"]
    for i, b in enumerate(blocks):
        lines.append(f"[{b['hex']}]")
        for r in b["regions"]:
            lines.append(f"  - {r}")
        if i < len(blocks) - 1:
            lines.append("   |\n   v\n  BORDER\n   |\n   v")
    return "\n".join(lines)


def load_cargo_items() -> list[str]:
    """Load the known cargo item names used to populate the manifest picker."""
    if not CARGO_ITEMS_PATH.exists():
        return []
    lines = CARGO_ITEMS_PATH.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip()]


def build_cargo_manifest_code_string(entries: list[dict[str, Any]]) -> str:
    """Build a single-line JSON string a Discord bot can parse and log to a file or Excel sheet."""
    payload = {
        "schema": CARGO_MANIFEST_SCHEMA,
        "manifest_id": str(uuid.uuid4()),
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "items": [{"name": e["name"], "quantity": e["quantity"]} for e in entries],
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def build_cargo_manifest_qr_png_base64(code_string: str) -> str:
    """Render the bot code string as a QR code and return it as a base64 PNG for embedding in HTML."""
    qr_image = qrcode.make(code_string)
    buffer = io.BytesIO()
    qr_image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def build_cargo_manifest_html(entries: list[dict[str, Any]], code_string: str) -> str:
    """Build a standalone HTML manifest report with an embedded scannable QR code."""
    qr_base64 = build_cargo_manifest_qr_png_base64(code_string)
    rows = "\n".join(
        f'<tr><td>{html.escape(e["name"])}</td><td class="qty">{e["quantity"]}</td></tr>'
        for e in entries
    )
    total_crates = sum(e["quantity"] for e in entries)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Cargo Manifest</title>
<style>
  body {{ background: #071523; color: #eef6ff; font-family: 'Segoe UI', sans-serif; padding: 32px; }}
  h1 {{ letter-spacing: 0.08em; }}
  .meta {{ color: #aebde0; font-size: 12px; margin-bottom: 24px; }}
  .layout {{ display: flex; gap: 32px; flex-wrap: wrap; align-items: flex-start; }}
  table {{ border-collapse: collapse; min-width: 360px; }}
  th, td {{ padding: 8px 14px; border-bottom: 1px solid #314b75; text-align: left; }}
  th {{ color: #d8e4ff; font-size: 11px; letter-spacing: 0.1em; text-transform: uppercase; }}
  td.qty {{ text-align: right; font-variant-numeric: tabular-nums; }}
  tr.total td {{ border-bottom: none; border-top: 2px solid #314b75; font-weight: 700; color: #8fffc1; }}
  .qr-box {{ background: #ffffff; padding: 16px; border-radius: 12px; text-align: center; }}
  .qr-box img {{ width: 220px; height: 220px; }}
  .qr-box p {{ color: #071523; font-size: 11px; margin-top: 10px; max-width: 220px; }}
</style>
</head>
<body>
  <h1>CARGO MANIFEST</h1>
  <div class="meta">Generated {generated_at}</div>
  <div class="layout">
    <table>
      <tr><th>Item</th><th>Quantity</th></tr>
      {rows}
      <tr class="total"><td>Total Crates</td><td class="qty">{total_crates}</td></tr>
    </table>
    <div class="qr-box">
      <img src="data:image/png;base64,{qr_base64}" alt="Manifest QR Code">
      <p>Scan to load this manifest into the CMRC Discord bot.</p>
    </div>
  </div>
</body>
</html>"""


def build_phrases_for_selected_bases(selected_bases: list[dict]) -> list[str]:
    """Return train route chat-like sentence lines with LOGI and REGION headers."""
    if not selected_bases:
        return []

    steps = [
        {"hex": clean_region_name(str(b.get("region", ""))), "region": str(b.get("name", "Unknown Stop"))}
        for b in selected_bases
    ]
    blocks = build_blocks_from_steps(steps)
    if not blocks:
        return []

    start_hex = blocks[0]["hex"]
    end_hex = blocks[-1]["hex"]
    prefix = "[+CMRC] "

    lines = []
    lines.append("LOGI CHAT MESSAGE")
    lines.append(f"{prefix}Train travelling from {start_hex} to {end_hex}")
    lines.append("")
    lines.append("REGION CHAT MESSAGES")

    for i in range(len(blocks) - 1):
        via = ", ".join(blocks[i]["regions"])
        lines.append(
            f"{prefix}Train travelling from {blocks[i]['hex']} to {blocks[i + 1]['hex']} via {via} -> Border"
        )

    final_regions = blocks[-1]["regions"]
    last_region = final_regions[-1]
    via_final = ", ".join(final_regions)
    lines.append(
        f"{prefix}Train travelling to {last_region} in {end_hex} via {via_final}"
    )

    return lines


class MapCanvasView(QGraphicsView):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.NoFrame)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.ScrollHandDrag)

        self.scene_ = QGraphicsScene(self)
        self.setScene(self.scene_)
        self.scene_.setBackgroundBrush(QColor("#071126"))

        self._press_pos = QPoint()

    def wheelEvent(self, event):
        zoom_in_factor = 1.18
        zoom_out_factor = 1.0 / zoom_in_factor
        zoom_factor = zoom_in_factor if event.angleDelta().y() > 0 else zoom_out_factor

        current_scale = self.transform().m11()
        if (current_scale * zoom_factor < 0.002 and zoom_factor < 1) or (current_scale * zoom_factor > 15.0 and zoom_factor > 1):
            return

        self.scale(zoom_factor, zoom_factor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press_pos = event.pos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            dist = (event.pos() - self._press_pos).manhattanLength()
            if dist < 6:
                scene_pt = self.mapToScene(event.pos())
                self.app._handle_map_click(scene_pt)
        super().mouseReleaseEvent(event)

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        painter.fillRect(rect, QColor("#071126"))

        grid_pen = QPen(QColor("#182942"), 2)
        grid_pen.setCosmetic(True)
        painter.setPen(grid_pen)

        step = 250
        left = int(rect.left()) - (int(rect.left()) % step)
        top = int(rect.top()) - (int(rect.top()) % step)

        x = left
        while x < rect.right():
            y = top
            while y < rect.bottom():
                painter.drawPoint(QPointF(x, y))
                y += step
            x += step


class CargoManifestDialog(QDialog):
    """Lets users search cargo items, add quantities, and export a finished manifest."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Cargo Manifest")
        self.resize(720, 560)
        self._all_items = load_cargo_items()
        self._entries: list[dict[str, Any]] = []
        self._setup_ui()
        self._filter_items("")

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        search_row = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search cargo items...")
        self.search_edit.textChanged.connect(self._filter_items)
        search_row.addWidget(self.search_edit, 1)
        layout.addLayout(search_row)

        self.item_list = QListWidget()
        self.item_list.itemDoubleClicked.connect(lambda _item: self._add_entry())
        layout.addWidget(self.item_list, 1)

        add_row = QHBoxLayout()
        self.quantity_spin = QSpinBox()
        self.quantity_spin.setRange(1, 999999)
        self.quantity_spin.setValue(1)
        add_row.addWidget(QLabel("Quantity:"))
        add_row.addWidget(self.quantity_spin)
        add_btn = QPushButton("Add to Manifest")
        add_btn.setObjectName("btnPrimary")
        add_btn.clicked.connect(self._add_entry)
        add_row.addWidget(add_btn)
        add_row.addStretch()
        layout.addLayout(add_row)

        layout.addWidget(QLabel("MANIFEST"))
        self.manifest_table = QTableWidget(0, 2)
        self.manifest_table.setHorizontalHeaderLabels(["Item", "Quantity"])
        self.manifest_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.manifest_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.manifest_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.manifest_table, 1)

        manifest_btn_row = QHBoxLayout()
        remove_btn = QPushButton("Remove Selected")
        remove_btn.clicked.connect(self._remove_selected_entry)
        manifest_btn_row.addWidget(remove_btn)
        clear_btn = QPushButton("Clear Manifest")
        clear_btn.clicked.connect(self._clear_manifest)
        manifest_btn_row.addWidget(clear_btn)
        manifest_btn_row.addStretch()
        layout.addLayout(manifest_btn_row)

        export_row = QHBoxLayout()
        export_btn = QPushButton("Export Manifest (.txt)")
        export_btn.clicked.connect(self._export_manifest)
        export_row.addWidget(export_btn)
        qr_btn = QPushButton("Export Manifest + QR Code (.html)")
        qr_btn.setObjectName("btnPrimary")
        qr_btn.clicked.connect(self._export_manifest_qr_html)
        export_row.addWidget(qr_btn)
        copy_btn = QPushButton("Copy Bot Code String")
        copy_btn.clicked.connect(self._copy_code_string)
        export_row.addWidget(copy_btn)
        export_row.addStretch()
        layout.addLayout(export_row)

        self.status_label = QLabel(f"{len(self._all_items)} known cargo items loaded.")
        self.status_label.setStyleSheet("color: #aebde0; font-size: 11px;")
        layout.addWidget(self.status_label)

    def _filter_items(self, text: str) -> None:
        query = text.strip().lower()
        self.item_list.clear()
        matches = [name for name in self._all_items if query in name.lower()] if query else self._all_items
        self.item_list.addItems(matches)

    def _add_entry(self) -> None:
        current = self.item_list.currentItem()
        if current is None:
            self.status_label.setText("Select an item from the list first.")
            return
        name = current.text()
        quantity = self.quantity_spin.value()

        for entry in self._entries:
            if entry["name"] == name:
                entry["quantity"] += quantity
                self._refresh_manifest_table()
                self.status_label.setText(f"Updated quantity for {name}.")
                return

        self._entries.append({"name": name, "quantity": quantity})
        self._refresh_manifest_table()
        self.status_label.setText(f"Added {name} x{quantity}.")

    def _remove_selected_entry(self) -> None:
        row = self.manifest_table.currentRow()
        if row < 0 or row >= len(self._entries):
            return
        removed = self._entries.pop(row)
        self._refresh_manifest_table()
        self.status_label.setText(f"Removed {removed['name']}.")

    def _clear_manifest(self) -> None:
        self._entries = []
        self._refresh_manifest_table()
        self.status_label.setText("Manifest cleared.")

    def _refresh_manifest_table(self) -> None:
        self.manifest_table.setRowCount(len(self._entries))
        for row, entry in enumerate(self._entries):
            self.manifest_table.setItem(row, 0, QTableWidgetItem(entry["name"]))
            self.manifest_table.setItem(row, 1, QTableWidgetItem(str(entry["quantity"])))

    def _export_manifest(self) -> None:
        if not self._entries:
            self.status_label.setText("Add items to the manifest before exporting.")
            return

        downloads_dir = Path.home() / "Downloads"
        downloads_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        lines = ["CARGO MANIFEST", ""]
        for entry in self._entries:
            lines.append(f"{entry['name']} x{entry['quantity']}")
        text_path = downloads_dir / f"CMRC_CARGO_MANIFEST_{timestamp}.txt"
        code_string = build_cargo_manifest_code_string(self._entries)
        text_path.write_text("\n".join(lines) + "\n\nBOT CODE STRING:\n" + code_string + "\n", encoding="utf-8")

        code_path = downloads_dir / f"CMRC_CARGO_MANIFEST_{timestamp}.bot.txt"
        code_path.write_text(code_string + "\n", encoding="utf-8")

        self.status_label.setText(f"Exported manifest and bot code string to Downloads ({text_path.name}).")

    def _copy_code_string(self) -> None:
        if not self._entries:
            self.status_label.setText("Add items to the manifest before copying a code string.")
            return
        code_string = build_cargo_manifest_code_string(self._entries)
        QGuiApplication.clipboard().setText(code_string)
        self.status_label.setText("Bot code string copied to clipboard.")

    def _export_manifest_qr_html(self) -> None:
        if not self._entries:
            self.status_label.setText("Add items to the manifest before exporting a QR code.")
            return

        downloads_dir = Path.home() / "Downloads"
        downloads_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        code_string = build_cargo_manifest_code_string(self._entries)
        html_path = downloads_dir / f"CMRC_CARGO_MANIFEST_{timestamp}.html"
        html_path.write_text(build_cargo_manifest_html(self._entries, code_string), encoding="utf-8")

        try:
            if sys.platform.startswith("darwin"):
                subprocess.run(["open", str(html_path)], check=False)
            elif sys.platform.startswith("win"):
                os.startfile(str(html_path))  # type: ignore[attr-defined]
            else:
                subprocess.run(["xdg-open", str(html_path)], check=False)
        except Exception:
            pass

        self.status_label.setText(f"Opened manifest with QR code: {html_path.name}")


class OverlayApp(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.resize(*WINDOW_SIZE)
        self.setMinimumSize(1200, 680)
        self.setWindowTitle(APP_TITLE)

        self.output_dir = str(Path.home() / "Downloads")
        self.status_text = "Live map loading..."

        self._is_running = False
        self._first_draw = True

        self._bases: list[dict] = []
        self._regions: list[dict] = []
        self._selected_indices: list[int] = []

        self._setup_ui()
        self._refresh_live_data()

    def _setup_ui(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow { background-color: #071523; }
            QWidget#shellWidget {
                background-color: rgba(10, 18, 30, 0.85);
                border: 1px solid #314b75;
                border-radius: 24px;
            }
            QWidget#mapPanel {
                background-color: #101a2c;
                border: 1px solid #314b75;
                border-radius: 20px;
            }
            QWidget#mapFrame {
                background-color: #071126;
                border: 1px solid #314b75;
                border-radius: 16px;
            }
            QWidget#sidePanel {
                background-color: #101a2c;
                border: 1px solid #314b75;
                border-radius: 20px;
            }
            QLabel { color: #eef6ff; font-family: 'Segoe UI', sans-serif; }
            QPushButton {
                background-color: #16223d;
                color: #eef6ff;
                border: 1px solid #314b75;
                border-radius: 10px;
                padding: 10px 12px;
                font-family: 'Segoe UI', sans-serif;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 0.08em;
                text-transform: uppercase;
            }
            QPushButton:hover {
                background-color: #203452;
                border-color: #8fffc1;
            }
            QPushButton:pressed {
                background-color: #121c33;
            }
            QPushButton#btnPrimary {
                background-color: #22c55e;
                color: #071523;
                border: 1px solid #8fffc1;
                font-weight: 800;
            }
            QPushButton#btnPrimary:hover {
                background-color: #4ade80;
            }
            QPlainTextEdit {
                background-color: #0d1320;
                color: #eef6ff;
                border: 1px solid #314b75;
                border-radius: 12px;
                padding: 10px;
                font-family: 'Consolas', monospace;
                font-size: 11px;
            }
            QFrame#statusBadge {
                background-color: rgba(76, 227, 176, 0.08);
                border: 1px solid #314b75;
                border-radius: 14px;
            }
            QFrame#statusBox {
                background-color: rgba(0, 0, 0, 0.25);
                border: 1px solid #314b75;
                border-radius: 12px;
            }
            """
        )

        root = QWidget(self)
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(16, 16, 16, 16)

        shell = QWidget(root)
        shell.setObjectName("shellWidget")
        shell_layout = QHBoxLayout(shell)
        shell_layout.setContentsMargins(14, 14, 14, 14)
        shell_layout.setSpacing(14)
        root_layout.addWidget(shell)

        # Left Panel (Map Column)
        map_panel = QWidget(shell)
        map_panel.setObjectName("mapPanel")
        map_layout = QVBoxLayout(map_panel)
        map_layout.setContentsMargins(16, 14, 16, 16)
        map_layout.setSpacing(12)
        shell_layout.addWidget(map_panel, 4)

        # Header bar inside map panel
        map_top = QWidget(map_panel)
        top_layout = QHBoxLayout(map_top)
        top_layout.setContentsMargins(0, 0, 0, 0)

        title_box = QWidget(map_top)
        title_layout = QVBoxLayout(title_box)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(2)

        app_title = QLabel(APP_TITLE)
        app_title.setStyleSheet("font-size: 26px; font-weight: 800; letter-spacing: 0.04em;")
        app_sub = QLabel("LIVE-1 ROUTE MAP")
        app_sub.setStyleSheet("font-size: 11px; color: #aebde0; font-weight: 600; letter-spacing: 0.12em;")
        title_layout.addWidget(app_title)
        title_layout.addWidget(app_sub)
        top_layout.addWidget(title_box)

        top_layout.addStretch()

        self.status_badge = QFrame(map_top)
        self.status_badge.setObjectName("statusBadge")
        badge_layout = QHBoxLayout(self.status_badge)
        badge_layout.setContentsMargins(12, 6, 12, 6)
        badge_layout.setSpacing(8)

        dot = QLabel("●")
        dot.setStyleSheet("color: #8fffc1; font-size: 10px;")
        self.badge_label = QLabel("MAP ONLINE")
        self.badge_label.setStyleSheet("color: #8fffc1; font-size: 10px; font-weight: 700; letter-spacing: 0.12em;")
        badge_layout.addWidget(dot)
        badge_layout.addWidget(self.badge_label)
        top_layout.addWidget(self.status_badge)

        map_layout.addWidget(map_top)

        # Map View Frame
        map_frame = QWidget(map_panel)
        map_frame.setObjectName("mapFrame")
        frame_layout = QVBoxLayout(map_frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)

        self.map_view = MapCanvasView(self)
        frame_layout.addWidget(self.map_view)
        map_layout.addWidget(map_frame, 1)

        # Right Panel (Sidebar Controls)
        side_panel = QWidget(shell)
        side_panel.setObjectName("sidePanel")
        side_panel.setFixedWidth(340)
        side_layout = QVBoxLayout(side_panel)
        side_layout.setContentsMargins(18, 18, 18, 18)
        side_layout.setSpacing(12)
        shell_layout.addWidget(side_panel)

        controls_title = QLabel("CONTROLS")
        controls_title.setStyleSheet("font-size: 13px; font-weight: 800; letter-spacing: 0.12em; color: #d8e4ff;")
        side_layout.addWidget(controls_title)

        button_defs = [
            ("Refresh Live Map", self._refresh_live_data, True),
            ("Generate Phrases", self._generate_phrases, False),
            ("Flip Direction", self._flip_direction, False),
            ("Export Phrases (.txt)", self._export_phrases, False),
            ("Show Train Plan", self._show_train_plan, False),
            ("Cargo Manifest", self._open_cargo_manifest, False),
            ("Zoom In", self._zoom_in, False),
            ("Zoom Out", self._zoom_out, False),
            ("Clear Selection", self._clear_selection, False),
            ("Reset Zoom", self._reset_zoom, False),
        ]

        for text, callback, is_primary in button_defs:
            btn = QPushButton(text)
            if is_primary:
                btn.setObjectName("btnPrimary")
            btn.clicked.connect(callback)
            btn.setMinimumHeight(34)
            side_layout.addWidget(btn)

        # Status box
        self.status_box = QFrame(side_panel)
        self.status_box.setObjectName("statusBox")
        status_box_layout = QVBoxLayout(self.status_box)
        status_box_layout.setContentsMargins(12, 10, 12, 10)
        self.status_text_label = QLabel(self.status_text)
        self.status_text_label.setStyleSheet("color: #aebde0; font-size: 11px; line-height: 1.4;")
        self.status_text_label.setWordWrap(True)
        status_box_layout.addWidget(self.status_text_label)
        side_layout.addWidget(self.status_box)

        # Route output
        output_title = QLabel("ROUTE OUTPUT")
        output_title.setStyleSheet("font-size: 13px; font-weight: 800; letter-spacing: 0.12em; color: #d8e4ff;")
        side_layout.addWidget(output_title)

        self.phrase_output = QPlainTextEdit()
        self.phrase_output.setPlainText(
            "LOGI CHAT MESSAGE: [+CMRC] Train travelling from Alpha to Bravo\n"
            "REGION CHAT MESSAGES: [+CMRC] Train travelling from Alpha to Bravo via Region A, Region B -> Border"
        )
        self.phrase_output.setMinimumHeight(120)
        side_layout.addWidget(self.phrase_output)

        footer = QLabel("ROUTE PLANNER / CMRC")
        footer.setStyleSheet("color: #aebde0; font-size: 10px; font-weight: 600; letter-spacing: 0.12em; margin-top: 4px;")
        side_layout.addWidget(footer)

    def _set_status(self, text: str) -> None:
        self.status_text = text
        if hasattr(self, "status_text_label"):
            self.status_text_label.setText(text)

    def _toggle_base_selection(self, idx: int) -> None:
        if idx in self._selected_indices:
            self._selected_indices.remove(idx)
        else:
            self._selected_indices.append(idx)
        self._redraw_scene()

    def _selected_bases(self) -> list[dict]:
        return [self._bases[idx] for idx in self._selected_indices if 0 <= idx < len(self._bases)]

    def _handle_map_click(self, scene_pt: QPointF) -> None:
        if not self._bases:
            return

        best_idx = -1
        min_dist = float("inf")
        view_scale = self.map_view.transform().m11()
        threshold = max(25.0, 15.0 / max(0.0001, view_scale))

        for idx, base in enumerate(self._bases):
            gx = float(base.get("global_x", 0.0))
            gy = float(base.get("global_y", 0.0))
            dist = ((gx - scene_pt.x()) ** 2 + (gy - scene_pt.y()) ** 2) ** 0.5
            if dist < min_dist:
                min_dist = dist
                best_idx = idx

        if min_dist <= threshold and best_idx != -1:
            self._toggle_base_selection(best_idx)

    def _refresh_live_data(self) -> None:
        if self._is_running:
            return
        self._is_running = True
        self._set_status("Checking WarAPI Live-1...")

        self._regions = list(load_local_layout_data().get("regions", [])) if load_local_layout_data() else []
        self._bases = []
        self._selected_indices = []
        self._redraw_scene()

        try:
            success, status = ping_live1_api()
            if not success:
                self._is_running = False
                self._set_status(status)
                if hasattr(self, "badge_label"):
                    self.badge_label.setText("MAP OFFLINE")
                return
            payload = load_live_overlay_data()
            if payload is None:
                self._is_running = False
                self._set_status("No data available from atlas/live endpoints.")
                return
            self._is_running = False
            self._regions = list(payload.get("regions", []))
            self._bases = list(payload.get("bases", []))
            self._selected_indices = []
            self._first_draw = True
            hex_count = payload.get("hex_count", 0)
            self._set_status(f"Live-1 active | Regions: {hex_count}, Bases: {len(self._bases)}")
            if hasattr(self, "badge_label"):
                self.badge_label.setText("MAP ONLINE")
            self._redraw_scene()
        except Exception as exc:
            self._is_running = False
            self._set_status(f"Load failed: {exc}")

    def _redraw_scene(self) -> None:
        scene = self.map_view.scene_
        scene.clear()

        if not self._regions:
            item = scene.addText("Loading map data...")
            item.setDefaultTextColor(QColor("#aebde0"))
            return

        # 1. Hex Regions (Dark sleek tiles with centered Hex Region Name)
        hex_brush = QColor(18, 32, 56, 180)
        hex_pen = QPen(QColor("#22385a"), 1.5)
        hex_pen.setCosmetic(True)

        for region in self._regions:
            points = region.get("points", [])
            if not isinstance(points, list) or len(points) < 3:
                continue
            polygon = QPolygonF()
            for p in points:
                if isinstance(p, (list, tuple)) and len(p) == 2:
                    polygon.append(QPointF(float(p[0]), float(p[1])))
            if polygon.count() >= 3:
                scene.addPolygon(polygon, hex_pen, hex_brush)

                # Draw Hex Region Name in center of hex
                display_name = clean_region_name(str(region.get("display_name") or region.get("region", "")))
                cx = float(region.get("center_x", 0.0))
                cy = float(region.get("center_y", 0.0))
                if cx == 0.0 and cy == 0.0:
                    rect = polygon.boundingRect()
                    cx, cy = rect.center().x(), rect.center().y()

                hex_label = scene.addSimpleText(display_name)
                font = QFont("Segoe UI", 36, QFont.Bold)
                hex_label.setFont(font)
                hex_label.setBrush(QColor("#4a6b82"))
                br = hex_label.boundingRect()
                hex_label.setPos(cx - br.width() / 2.0, cy - br.height() / 2.0)

        # 2. Connecting Route Lines
        glow_pen = QPen(QColor(143, 255, 193, 140), 7)
        glow_pen.setCosmetic(True)
        core_pen = QPen(QColor("#ffffff"), 3.5)
        core_pen.setCosmetic(True)

        for i in range(len(self._selected_indices) - 1):
            idx_a = self._selected_indices[i]
            idx_b = self._selected_indices[i + 1]
            if 0 <= idx_a < len(self._bases) and 0 <= idx_b < len(self._bases):
                a = self._bases[idx_a]
                b = self._bases[idx_b]
                ax, ay = float(a.get("global_x", 0.0)), float(a.get("global_y", 0.0))
                bx, by = float(b.get("global_x", 0.0)), float(b.get("global_y", 0.0))
                scene.addLine(ax, ay, bx, by, glow_pen)
                scene.addLine(ax, ay, bx, by, core_pen)

        # 3. Location Bubbles & Name Labels (Larger font, centered directly below bubbles)
        WORLD_BASE_RADIUS = 8.0

        for idx, base in enumerate(self._bases):
            gx = float(base.get("global_x", 0.0))
            gy = float(base.get("global_y", 0.0))
            team = str(base.get("team", "NONE"))
            team_color = TEAM_COLORS.get(team, QColor("#e5e7eb"))

            is_selected = idx in self._selected_indices

            if is_selected:
                brush = QColor("#ffffff")
                pen = QPen(team_color, 2.5)
                pen.setCosmetic(True)
            else:
                brush = QColor(10, 18, 30, 220)
                pen = QPen(team_color, 1.8)
                pen.setCosmetic(True)

            scene.addEllipse(
                gx - WORLD_BASE_RADIUS,
                gy - WORLD_BASE_RADIUS,
                WORLD_BASE_RADIUS * 2,
                WORLD_BASE_RADIUS * 2,
                pen,
                brush,
            )

            base_name = str(base.get("name", ""))
            if base_name:
                region_name = clean_region_name(str(base.get("region", "")))
                full_label = f"{base_name} ({region_name})" if is_selected else base_name
                label_item = scene.addSimpleText(full_label)
                font = QFont("Segoe UI", 13, QFont.Bold if is_selected else QFont.Normal)
                label_item.setFont(font)
                label_item.setBrush(QColor("#ffffff") if is_selected else QColor("#d8e4ff"))
                br = label_item.boundingRect()
                label_item.setPos(gx - (br.width() / 2.0), gy + WORLD_BASE_RADIUS + 3.0)

        if self._first_draw:
            self._first_draw = False
            rect = scene.itemsBoundingRect()
            if not rect.isEmpty():
                self.map_view.fitInView(rect.adjusted(-200, -200, 200, 200), Qt.KeepAspectRatio)

    def _generate_phrases(self) -> None:
        bases = self._selected_bases()
        if not bases:
            self._set_status("Select route bases on map to generate phrases.")
            self.phrase_output.setPlainText("")
            return

        phrases = build_phrases_for_selected_bases(bases)
        report = "\n".join(phrases)
        self.phrase_output.setPlainText(report)
        self._set_status(f"Generated route phrases ({len(bases)} stops).")

    def _export_phrases(self) -> None:
        phrase_text = self.phrase_output.toPlainText().strip()
        if not phrase_text:
            self._set_status("No phrases available to export.")
            return

        bases = self._selected_bases()
        if bases:
            start_hex = clean_region_name(str(bases[0].get("region", ""))).replace(" ", "_")
            end_hex = clean_region_name(str(bases[-1].get("region", ""))).replace(" ", "_")
            filename = f"CMRC_TRAINR_{start_hex}_{end_hex}.txt"
        else:
            filename = "CMRC_TRAINR_Unknown.txt"

        downloads_dir = Path.home() / "Downloads"
        downloads_dir.mkdir(parents=True, exist_ok=True)
        output_path = downloads_dir / filename

        try:
            output_path.write_text(phrase_text + "\n", encoding="utf-8")
            self._set_status(f"Exported to Downloads: {filename}")
        except Exception as exc:
            self._set_status(f"Export failed: {exc}")

    def _flip_direction(self) -> None:
        if not self._selected_indices:
            self._set_status("No route selected to flip.")
            return
        self._selected_indices.reverse()
        self._redraw_scene()
        if self.phrase_output.toPlainText().strip():
            self._generate_phrases()
        self._set_status("Flipped route direction.")

    def _show_train_plan(self) -> None:
        bases = self._selected_bases()
        if not bases:
            self._set_status("Select route bases to show a train plan.")
            return
        downloads_dir = Path.home() / "Downloads"
        downloads_dir.mkdir(parents=True, exist_ok=True)
        start_hex = clean_region_name(str(bases[0].get("region", ""))).replace(" ", "_")
        end_hex = clean_region_name(str(bases[-1].get("region", ""))).replace(" ", "_")
        html_path = downloads_dir / f"CMRC_TRAINR_{start_hex}_{end_hex}.html"
        html_path.write_text(self._render_train_plan_html(bases), encoding="utf-8")
        self._set_status(f"Opened train plan for {len(bases)} stops in browser.")
        try:
            if sys.platform.startswith("darwin"):
                subprocess.run(["open", str(html_path)], check=False)
            elif sys.platform.startswith("win"):
                os.startfile(str(html_path))  # type: ignore[attr-defined]
            else:
                subprocess.run(["xdg-open", str(html_path)], check=False)
        except Exception:
            pass

    def _open_cargo_manifest(self) -> None:
        dialog = CargoManifestDialog(self)
        dialog.exec()

    def _render_train_plan_html(self, bases: list[dict]) -> str:
        hex_blocks: list[dict[str, Any]] = []
        for idx, base in enumerate(bases):
            hex_name = clean_region_name(str(base.get("region", "")))
            name = html.escape(str(base.get("name", "Stop")))
            team = html.escape(str(base.get("team", "NONE")).upper())

            team_class = "team-neutral"
            if team == "COLONIALS":
                team_class = "team-colonial"
            elif team == "WARDENS":
                team_class = "team-warden"

            stop_item = {
                "step": idx + 1,
                "name": name,
                "team": team,
                "team_class": team_class,
                "is_first": (idx == 0),
                "is_last": (idx == len(bases) - 1),
            }

            if not hex_blocks or hex_blocks[-1]["hex_name"] != hex_name:
                hex_blocks.append({"hex_name": hex_name, "stops": []})
            hex_blocks[-1]["stops"].append(stop_item)

        hex_cards_html = []
        for b_idx, block in enumerate(hex_blocks):
            hex_title = html.escape(block["hex_name"])
            stops_html = []
            for s in block["stops"]:
                badge = ""
                if s["is_first"]:
                    badge = '<span class="role-badge">START</span>'
                elif s["is_last"]:
                    badge = '<span class="role-badge">DESTINATION</span>'

                stops_html.append(f"""
                <div class="stop-row {s['team_class']}">
                  <div class="stop-left">
                    <span class="step-badge">{s['step']}</span>
                    <span class="stop-name">{s['name']}</span>
                  </div>
                  <div class="stop-right">
                    {badge}
                    <span class="team-tag">{s['team']}</span>
                  </div>
                </div>
                """)

            all_stops = "".join(stops_html)
            card = f"""
            <div class="hex-card">
              <div class="hex-header">
                <span class="hex-icon">⬡</span>
                <span class="hex-title">{hex_title}</span>
                <span class="stop-count">{len(block['stops'])} STOP{"S" if len(block['stops']) != 1 else ""}</span>
              </div>
              <div class="hex-body">
                {all_stops}
              </div>
            </div>
            """
            hex_cards_html.append(card)

            if b_idx < len(hex_blocks) - 1:
                hex_cards_html.append("""
                <div class="border-connector">
                  <div class="border-pill">BORDER</div>
                  <div class="connector-arrow">➔</div>
                </div>
                """)

        combined_flow = "".join(hex_cards_html)
        start_stop = html.escape(str(bases[0].get("name", "Start")))
        start_hex = html.escape(clean_region_name(str(bases[0].get("region", ""))))
        end_stop = html.escape(str(bases[-1].get("name", "End")))
        end_hex = html.escape(clean_region_name(str(bases[-1].get("region", ""))))

        unique_regions = len(hex_blocks)

        return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>CMRC Train Route Plan</title>
  <style>
    body {{
      margin: 0;
      background: #071523;
      font-family: 'Segoe UI', Inter, sans-serif;
      color: #eef6ff;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      padding: 24px;
      box-sizing: border-box;
    }}
    .shell {{
      width: 100%;
      max-width: 1200px;
      background: #0d1a2d;
      border: 1px solid #314b75;
      border-radius: 24px;
      padding: 28px;
      box-shadow: 0 30px 100px rgba(0,0,0,0.6);
    }}
    .header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 24px;
      border-bottom: 1px solid #22385a;
      padding-bottom: 16px;
    }}
    .title-area h1 {{
      margin: 0;
      font-size: 28px;
      font-weight: 800;
      letter-spacing: 0.04em;
      color: #eef6ff;
    }}
    .title-area p {{
      margin: 4px 0 0 0;
      color: #8fffc1;
      font-size: 13px;
      font-weight: 600;
    }}
    .stats-bar {{
      display: flex;
      gap: 12px;
    }}
    .stat-pill {{
      background: #16273e;
      border: 1px solid #314b75;
      border-radius: 999px;
      padding: 6px 14px;
      font-size: 11px;
      font-weight: 700;
      color: #d8e4ff;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .route-flow {{
      display: flex;
      flex-wrap: wrap;
      align-items: stretch;
      gap: 16px;
      background: #071126;
      border: 1px solid #22385a;
      border-radius: 20px;
      padding: 24px;
    }}
    .hex-card {{
      flex: 1 1 260px;
      min-width: 250px;
      background: #122036;
      border: 1px solid #314b75;
      border-radius: 16px;
      padding: 16px;
      box-shadow: 0 8px 24px rgba(0,0,0,0.35);
      display: flex;
      flex-direction: column;
    }}
    .hex-header {{
      display: flex;
      align-items: center;
      gap: 8px;
      border-bottom: 1px solid #22385a;
      padding-bottom: 10px;
      margin-bottom: 12px;
    }}
    .hex-icon {{
      color: #8fffc1;
      font-size: 18px;
    }}
    .hex-title {{
      font-size: 16px;
      font-weight: 800;
      color: #ffffff;
      flex: 1;
      letter-spacing: 0.02em;
    }}
    .stop-count {{
      font-size: 10px;
      font-weight: 700;
      color: #8fffc1;
      background: rgba(143,255,193,0.08);
      border: 1px solid #314b75;
      border-radius: 999px;
      padding: 3px 8px;
      letter-spacing: 0.06em;
    }}
    .hex-body {{
      display: flex;
      flex-direction: column;
      gap: 8px;
      flex: 1;
    }}
    .stop-row {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: rgba(7, 17, 38, 0.7);
      border: 1px solid #22385a;
      border-radius: 10px;
      padding: 10px 12px;
    }}
    .stop-row.team-colonial {{ border-left: 4px solid #22c55e; }}
    .stop-row.team-warden {{ border-left: 4px solid #3b82f6; }}
    .stop-row.team-neutral {{ border-left: 4px solid #9ca3af; }}

    .stop-left {{
      display: flex;
      align-items: center;
      gap: 10px;
    }}
    .step-badge {{
      width: 22px;
      height: 22px;
      background: #22c55e;
      color: #071523;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 800;
      font-size: 11px;
    }}
    .stop-name {{
      font-size: 13px;
      font-weight: 700;
      color: #ffffff;
    }}
    .stop-right {{
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .role-badge {{
      font-size: 9px;
      font-weight: 800;
      letter-spacing: 0.08em;
      color: #8fffc1;
      background: rgba(143, 255, 193, 0.12);
      border: 1px solid rgba(143, 255, 193, 0.3);
      border-radius: 4px;
      padding: 2px 6px;
      text-transform: uppercase;
    }}
    .team-tag {{
      font-size: 9px;
      font-weight: 700;
      color: #88a0ca;
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }}
    .border-connector {{
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 4px;
      padding: 0 4px;
    }}
    .border-pill {{
      font-size: 9px;
      font-weight: 800;
      letter-spacing: 0.12em;
      color: #8fffc1;
      background: rgba(143, 255, 193, 0.08);
      border: 1px solid #314b75;
      border-radius: 999px;
      padding: 4px 8px;
      text-transform: uppercase;
    }}
    .connector-arrow {{
      color: #8fffc1;
      font-size: 22px;
      font-weight: 800;
    }}
  </style>
</head>
<body>
  <div class="shell">
    <header class="header">
      <div class="title-area">
        <h1>CMRC Train Route Plan</h1>
        <p>Route: {start_stop} ({start_hex}) ➔ {end_stop} ({end_hex})</p>
      </div>
      <div class="stats-bar">
        <div class="stat-pill">{len(bases)} STOPS</div>
        <div class="stat-pill">{unique_regions} HEXES</div>
      </div>
    </header>
    <main class="route-flow">
      {combined_flow}
    </main>
  </div>
</body>
</html>"""

    def _clear_selection(self) -> None:
        self._selected_indices = []
        self._redraw_scene()

    def _zoom_in(self) -> None:
        self.map_view.scale(1.25, 1.25)

    def _zoom_out(self) -> None:
        self.map_view.scale(0.8, 0.8)

    def _reset_zoom(self) -> None:
        rect = self.map_view.scene_.itemsBoundingRect()
        if not rect.isEmpty():
            self.map_view.fitInView(rect.adjusted(-200, -200, 200, 200), Qt.KeepAspectRatio)

    def _open_output_dir(self) -> None:
        out_dir = Path(self.output_dir).expanduser()
        out_dir.mkdir(parents=True, exist_ok=True)
        if sys.platform.startswith("darwin"):
            subprocess.run(["open", str(out_dir)], check=False)
        elif sys.platform.startswith("win"):
            os.startfile(str(out_dir))  # type: ignore[attr-defined]
        else:
            subprocess.run(["xdg-open", str(out_dir)], check=False)


def main() -> None:
    app = QApplication(sys.argv)
    window = OverlayApp()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
