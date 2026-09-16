import json
import math
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Optional

from build_global_atlas import build_atlas_file

PROJECT_ROOT = Path(__file__).resolve().parent
HEX_MAPS_DIR = PROJECT_ROOT / "Hex Maps"
ATLAS_PATH = HEX_MAPS_DIR / "global_hex_atlas.json"
OUTPUT_PATH = HEX_MAPS_DIR / "global_resource_overlay_map.png"
LOG_PATH = HEX_MAPS_DIR / "global_resource_positions.log"

SQRT3 = math.sqrt(3.0)
LOCAL_SCALE = 0.92
WAR_API_BASE_LIVE1 = "https://war-service-live.foxholeservices.com/api"
RENDER_ICON_TYPES = {45, 56, 57, 58}

# Structures requested for rendering.
ICON_SPECS: dict[int, dict[str, Any]] = {
    45: {"label": "Relic Base", "name": "Relic Base"},
    56: {"label": "Town Base", "name": "Town Base"},
    57: {"label": "Town Base", "name": "Town Base"},
    58: {"label": "Town Base", "name": "Town Base"},
}
BASE_LABEL_VERTICAL_OFFSET_PX = 14.0


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _fetch_json(url: str, timeout_s: float = 20.0) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "FoxholeTrainRunMaker/1.0",
            "Accept": "application/json",
        },
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        return json.loads(response.read().decode("utf-8"))


def _ping_warapi() -> tuple[bool, str]:
    try:
        war_data = _fetch_json(f"{WAR_API_BASE_LIVE1}/worldconquest/war")
    except urllib.error.URLError as exc:
        return False, f"WarAPI ping failed: {exc}"
    except TimeoutError:
        return False, "WarAPI ping timed out"
    except json.JSONDecodeError:
        return False, "WarAPI ping returned malformed JSON"

    war_number = war_data.get("warNumber") if isinstance(war_data, dict) else None
    winner = war_data.get("winner") if isinstance(war_data, dict) else None
    if war_number is None or winner is None:
        return False, "WarAPI ping succeeded but response was missing expected fields"

    return True, f"WarAPI Live-1 online | war={war_number} winner={winner}"


def ping_live1_api() -> tuple[bool, str]:
    return _ping_warapi()


def _load_warapi_map_names() -> set[str]:
    maps = _fetch_json(f"{WAR_API_BASE_LIVE1}/worldconquest/maps")
    if not isinstance(maps, list):
        return set()
    return {str(name) for name in maps if isinstance(name, str)}


def _tile_center_to_hex(center_x: float, center_y: float, tile_w: float, tile_h: float) -> list[tuple[float, float]]:
    radius = tile_w / 2.0
    points: list[tuple[float, float]] = []
    for i in range(6):
        angle = math.radians(60 * i)
        px = center_x + radius * math.cos(angle)
        py = center_y + radius * math.sin(angle)
        points.append((px, py))

    expected_half_h = tile_h / 2.0
    actual_half_h = (SQRT3 * radius) / 2.0
    scale_y = expected_half_h / actual_half_h if actual_half_h else 1.0
    return [(x, center_y + (y - center_y) * scale_y) for x, y in points]


def _project_local_to_global(tile_x: float, tile_y: float, tile_w: float, tile_h: float,
                             local_x: float, local_y: float) -> tuple[float, float]:
    gx = tile_x + (local_x * tile_w)
    gy = tile_y + (local_y * tile_h)
    cx = tile_x + tile_w / 2.0
    cy = tile_y + tile_h / 2.0
    gx = cx + (gx - cx) * LOCAL_SCALE
    gy = cy + (gy - cy) * LOCAL_SCALE
    return gx, gy


def _team_of(item: dict, override_team: str | None = None) -> str:
    if override_team:
        return override_team
    return str(item.get("teamId") or "NONE").upper()


def _nearest_base_name(local_x: float, local_y: float, map_text_items: list[dict[str, Any]]) -> str | None:
    best_name: str | None = None
    best_distance: float | None = None

    for marker in map_text_items:
        marker_x = marker.get("x")
        marker_y = marker.get("y")
        marker_text = marker.get("text")
        if not isinstance(marker_x, (float, int)) or not isinstance(marker_y, (float, int)):
            continue
        if not isinstance(marker_text, str) or not marker_text.strip():
            continue

        distance = math.hypot(float(local_x) - float(marker_x), float(local_y) - float(marker_y))
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_name = marker_text.strip()

    return best_name


def _load_live_base_items_for_region(region_name: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    static_payload = _fetch_json(f"{WAR_API_BASE_LIVE1}/worldconquest/maps/{region_name}/static")
    dynamic_payload = _fetch_json(f"{WAR_API_BASE_LIVE1}/worldconquest/maps/{region_name}/dynamic/public")

    static_text = []
    if isinstance(static_payload, dict):
        static_text = static_payload.get("mapTextItems", [])

    dynamic_items: list[dict[str, Any]] = []
    if isinstance(dynamic_payload, dict):
        for key in ("mapItems", "mapItemsC", "mapItemsW"):
            values = dynamic_payload.get(key)
            if isinstance(values, list):
                dynamic_items.extend(v for v in values if isinstance(v, dict))

    return dynamic_items, static_text if isinstance(static_text, list) else []


def _collect_positions(items: list[dict], tile_x: float, tile_y: float, tile_w: float, tile_h: float,
                       region_name: str, override_team: str | None, out: list[dict[str, Any]],
                       map_text_items: list[dict[str, Any]]) -> int:
    added = 0
    for item in items:
        icon_type = item.get("iconType")
        x = item.get("x")
        y = item.get("y")
        if icon_type not in RENDER_ICON_TYPES:
            continue
        if not isinstance(x, (float, int)) or not isinstance(y, (float, int)):
            continue

        gx, gy = _project_local_to_global(tile_x, tile_y, tile_w, tile_h, float(x), float(y))
        spec = ICON_SPECS[int(icon_type)]
        display_label = str(spec["label"])
        display_name = str(spec["name"])

        base_name = _nearest_base_name(float(x), float(y), map_text_items)
        if isinstance(base_name, str) and base_name:
            display_label = base_name
            display_name = base_name

        out.append(
            {
                "region": region_name,
                "iconType": int(icon_type),
                "name": display_name,
                "label": display_label,
                "team": _team_of(item, override_team),
                "global_x": gx,
                "global_y": gy,
                "hex_diameter": float(tile_w) * LOCAL_SCALE,
            }
        )
        added += 1
    return added


def _resolve_output_paths(output_dir: Optional[str] = None) -> tuple[Path, Path]:
    if output_dir is None or not str(output_dir).strip():
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        return OUTPUT_PATH, LOG_PATH

    target_dir = Path(str(output_dir)).expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    return (
        target_dir / OUTPUT_PATH.name,
        target_dir / LOG_PATH.name,
    )


def load_local_layout_data() -> dict[str, Any] | None:
    if not ATLAS_PATH.exists():
        try:
            build_atlas_file(PROJECT_ROOT)
        except Exception:
            return None

    atlas = _read_json(ATLAS_PATH)
    regions: dict[str, Any] = atlas.get("regions", {}) if isinstance(atlas, dict) else {}
    if not regions:
        return None

    min_left = float("inf")
    min_top = float("inf")
    max_right = 0.0
    max_bottom = 0.0
    region_polygons: list[dict[str, Any]] = []

    for region_name, region_data in regions.items():
        pixel = region_data.get("pixel", {})
        tx = float(pixel.get("tile_x", 0.0))
        ty = float(pixel.get("tile_y", 0.0))
        tw = float(pixel.get("tile_w", 1024.0))
        th = float(pixel.get("tile_h", 888.0))
        cx = float(pixel.get("center_x", tx + tw / 2.0))
        cy = float(pixel.get("center_y", ty + th / 2.0))

        min_left = min(min_left, tx)
        min_top = min(min_top, ty)
        max_right = max(max_right, tx + tw)
        max_bottom = max(max_bottom, ty + th)

        region_polygons.append(
            {
                "region": region_name,
                "display_name": str(region_data.get("display_name", region_name)),
                "center_x": cx,
                "center_y": cy,
                "points": _tile_center_to_hex(cx, cy, tw, th),
                "tile_x": tx,
                "tile_y": ty,
                "tile_w": tw,
                "tile_h": th,
            }
        )

    if min_left == float("inf"):
        return None

    return {
        "bounds": {
            "min_left": min_left,
            "min_top": min_top,
            "max_right": max_right,
            "max_bottom": max_bottom,
        },
        "regions": region_polygons,
        "hex_count": len(regions),
    }


def load_live_overlay_data() -> dict[str, Any] | None:
    layout = load_local_layout_data()
    if layout is None:
        return None

    available_maps = _load_warapi_map_names()
    regions = list(layout.get("regions", []))
    positions: list[dict[str, Any]] = []

    target_regions = [r for r in regions if str(r.get("region", "")) in available_maps]

    def _fetch_region_positions(region: dict[str, Any]) -> list[dict[str, Any]]:
        region_name = str(region.get("region", ""))
        tx = float(region.get("tile_x", 0.0))
        ty = float(region.get("tile_y", 0.0))
        tw = float(region.get("tile_w", 1024.0))
        th = float(region.get("tile_h", 888.0))

        dynamic_items, static_text_items = _load_live_base_items_for_region(region_name)
        region_positions: list[dict[str, Any]] = []
        _collect_positions(dynamic_items, tx, ty, tw, th, region_name, None, region_positions, static_text_items)
        return region_positions

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(_fetch_region_positions, region) for region in target_regions]
        for future in as_completed(futures):
            try:
                positions.extend(future.result())
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, ValueError):
                continue

    return {
        "bounds": layout["bounds"],
        "regions": regions,
        "bases": positions,
        "hex_count": int(layout.get("hex_count", 0)),
    }


def generate_resource_overlay_map(output_dir: Optional[str] = None) -> dict[str, Any] | None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Polygon

    if not ATLAS_PATH.exists():
        try:
            build_atlas_file(PROJECT_ROOT)
        except Exception:
            return None

    atlas = _read_json(ATLAS_PATH)
    regions: dict[str, Any] = atlas.get("regions", {}) if isinstance(atlas, dict) else {}

    if not regions:
        return None

    available_maps = _load_warapi_map_names()

    min_left = float("inf")
    min_top = float("inf")
    max_right = 0.0
    max_bottom = 0.0

    for region_data in regions.values():
        pixel = region_data.get("pixel", {})
        tx = float(pixel.get("tile_x", 0.0))
        ty = float(pixel.get("tile_y", 0.0))
        tw = float(pixel.get("tile_w", 1024.0))
        th = float(pixel.get("tile_h", 888.0))
        min_left = min(min_left, tx)
        min_top = min(min_top, ty)
        max_right = max(max_right, tx + tw)
        max_bottom = max(max_bottom, ty + th)

    width = max_right - min_left
    height = max_bottom - min_top
    fig_w = max(12.0, width / 500.0)
    fig_h = max(8.0, height / 500.0)

    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=220)
    ax.set_facecolor("#08111f")
    fig.patch.set_facecolor("#08111f")

    positions: list[dict[str, Any]] = []
    hex_centers: dict[str, tuple[float, float]] = {}

    for region_name, region_data in regions.items():
        pixel = region_data.get("pixel", {})
        tx = float(pixel.get("tile_x", 0.0))
        ty = float(pixel.get("tile_y", 0.0))
        tw = float(pixel.get("tile_w", 1024.0))
        th = float(pixel.get("tile_h", 888.0))
        cx = float(pixel.get("center_x", tx + tw / 2.0))
        cy = float(pixel.get("center_y", ty + th / 2.0))
        hex_centers[region_name] = (cx, cy)

        poly = Polygon(_tile_center_to_hex(cx, cy, tw, th), closed=True)
        poly.set_facecolor("#9ca3af")
        poly.set_alpha(0.07)
        poly.set_edgecolor("#d1d5db")
        poly.set_linewidth(0.7)
        ax.add_patch(poly)

        short_name = str(region_data.get("display_name", region_name))
        ax.text(cx, cy, short_name, ha="center", va="center", color="#cbd5e1", fontsize=4, alpha=0.72)

        if region_name not in available_maps:
            continue

        try:
            dynamic_items, static_text_items = _load_live_base_items_for_region(region_name)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            continue

        _collect_positions(dynamic_items, tx, ty, tw, th, region_name, None, positions, static_text_items)

    team_colors = {
        "COLONIALS": "#22c55e",
        "WARDENS": "#3b82f6",
        "NONE": "#e5e7eb",
    }

    for entry in positions:
        color = team_colors.get(entry["team"], "#e5e7eb")
        ax.text(
            float(entry["global_x"]),
            float(entry["global_y"]) + BASE_LABEL_VERTICAL_OFFSET_PX,
            str(entry["label"]),
            ha="center",
            va="top",
            fontsize=2.6,
            color="#0b1020",
            bbox={"boxstyle": "round,pad=0.03", "fc": color, "ec": "none", "alpha": 0.83},
            zorder=5,
        )

    ax.set_xlim(min_left - 120.0, max_right + 120.0)
    ax.set_ylim(max_bottom + 120.0, min_top - 120.0)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xticks([])
    ax.set_yticks([])

    ax.set_title(
        (
            "Foxhole Global Base Allegiance Overlay (WarAPI Live-1)\n"
            f"Hexes: {len(regions)} | Labels Plotted: {len(positions)}"
        ),
        color="#e2e8f0",
        fontsize=14,
        pad=12,
    )

    label_legend_rows = [
        "Rendered IDs: 45, 56, 57, 58",
        "Relic/Town Bases = full base names",
    ]

    label_legend_handles = [
        Line2D([], [], linestyle="none", marker="s", markersize=8, markerfacecolor="#e5e7eb", markeredgecolor="none", label=row)
        for row in label_legend_rows
    ]

    legend_handles = [*label_legend_handles]
    legend = ax.legend(
        handles=legend_handles,
        loc="lower right",
        fontsize=7,
        frameon=True,
        facecolor="#111827",
        edgecolor="#334155",
        title="Label Legend",
        title_fontsize=8,
    )
    for txt in legend.get_texts():
        txt.set_color("#e5e7eb")
    if legend.get_title() is not None:
        legend.get_title().set_color("#e5e7eb")

    output_image_path, output_log_path = _resolve_output_paths(output_dir)

    fig.tight_layout()
    fig.savefig(output_image_path, bbox_inches="tight")
    plt.close(fig)

    lines: list[str] = []
    lines.append("Live Base Allegiance Positions: Global Coordinates")
    lines.append("name,label,region,iconType,team,global_x,global_y")
    for item in sorted(
        positions,
        key=lambda d: (str(d["name"]), str(d["region"]), float(d["global_x"]), float(d["global_y"])),
    ):
        lines.append(
            f"{item['name']},{item['label']},{item['region']},{item['iconType']},{item['team']},{item['global_x']:.6f},{item['global_y']:.6f}"
        )

    lines.append("")
    lines.append("Hex Centers: Global Coordinates")
    lines.append("region,center_x,center_y")
    for region_name in sorted(hex_centers.keys()):
        center_x, center_y = hex_centers[region_name]
        lines.append(f"{region_name},{center_x:.6f},{center_y:.6f}")

    output_log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {
        "image_path": str(output_image_path),
        "log_path": str(output_log_path),
        "items_plotted": len(positions),
        "hex_count": len(regions),
    }


if __name__ == "__main__":
    is_online, status_text = ping_live1_api()
    print(status_text)
    if not is_online:
        raise SystemExit(1)

    summary = generate_resource_overlay_map()
    if summary is None:
        print("Overlay generation skipped: missing atlas or no regions available.")
    else:
        print(
            "Saved overlay image: "
            f"{summary['image_path']} | items={summary['items_plotted']} hexes={summary['hex_count']}"
        )
        print(f"Saved position log: {summary['log_path']}")
