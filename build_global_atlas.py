import json
import math
from pathlib import Path




X_STEP = 0.75  # flat-topped hex: 3/4 width horizontally
Y_STEP = 0.5   # flat-topped hex: 1/2 height vertically
TILE_W = 1024
TILE_H = 888
SCALE_X = TILE_W
SCALE_Y = TILE_H

POSITIONS: dict[str, tuple[int, int]] = {
    # R0
    "BasinSionnachHex": (7, 0),
    # R1
    "SpeakingWoodsHex": (6, 1),
    "HowlCountyHex": (8, 1),
    # R2
    "KuuraStrandHex": (3, 2),
    "CallumsCapeHex": (5, 2),
    "ReachingTrailHex": (7, 2),
    "ClansheadValleyHex": (9, 2),
    # R3
    "PariPeakHex": (2, 3),
    "NevishLineHex": (4, 3),
    "MooringCountyHex": (6, 3),
    "ViperPitHex": (8, 3),
    "MorgensCrossingHex": (10, 3),
    # R4
    "OlavisWakeHex": (1, 4),
    "GutterHex": (3, 4),
    "StonecradleHex": (5, 4),
    "CallahansPassageHex": (7, 4),
    "WeatheredExpanseHex": (9, 4),
    "GodcroftsHex": (11, 4),
    # R5
    "PalantineBermHex": (2, 5),
    "FarranacCoastHex": (4, 5),
    "LinnMercyHex": (6, 5),
    "MarbanHollow": (8, 5),
    "StlicanShelfHex": (10, 5),
    "LykosIsleHex": (12, 5),
    # R6
    "FishermansRowHex": (3, 6),
    "KingsCageHex": (5, 6),
    "DeadLandsHex": (7, 6),
    "ClahstraHex": (9, 6),
    "TempestIslandHex": (11, 6),
    # R7
    "OarbreakerHex": (2, 7),
    "WestgateHex": (4, 7),
    # R8
    "LochMorHex": (6, 8),
    "DrownedValeHex": (8, 8),
    "EndlessShoreHex": (10, 8),
    "TheFingersHex": (12, 8),
    # R9
    "StemaLandingHex": (3, 9),
    "SableportHex": (5, 9),
    "UmbralWildwoodHex": (7, 9),
    "AllodsBightHex": (9, 9),
    "WrestaHex": (11, 9),
    "PipersEnclaveHex": (13, 9),
    # R10
    "OriginHex": (4, 10),
    "HeartlandsHex": (6, 10),
    "ShackledChasmHex": (8, 10),
    "ReaversPassHex": (10, 10),
    "TyrantFoothillsHex": (12, 10),
    # R11
    "AshFieldsHex": (5, 11),
    "GreatMarchHex": (7, 11),
    "TerminusHex": (9, 11),
    "OnyxHex": (11, 11),
    # R12
    "RedRiverHex": (6, 12),
    "AcrithiaHex": (8, 12),
    # R13
    "KalokaiHex": (7, 13),
}


def paste_xy(col: int, row: int) -> tuple[int, int]:
    # Move every hex from row 8 onwards up by 1 grid unit
    adj_row = row - 1 if row >= 8 else row
    x = int(col * SCALE_X * X_STEP)
    y = int(adj_row * SCALE_Y * Y_STEP)
    return x, y


def display_name(region: str) -> str:
    text = region
    if text.endswith("Hex"):
        text = text[:-3]
    text = text.replace("Oarbreaker", "Oarbreaker Isles")
    text = text.replace("MooringCounty", "Mooring County")
    text = text.replace("LinnMercy", "The Linn of Mercy")
    text = text.replace("Clahstra", "The Clahstra")
    text = text.replace("StlicanShelf", "Stlican Shelf")
    return text


def build_neighbors(entries: dict[str, dict]) -> None:
    # Neighboring centers are one hex-edge apart, approximately TILE_H pixels.
    nominal = float(TILE_H)
    tolerance = 24.0
    regions = list(entries.keys())

    for region in regions:
        entries[region]["neighbors"] = []

    for i, a in enumerate(regions):
        ax = entries[a]["pixel"]["center_x"]
        ay = entries[a]["pixel"]["center_y"]
        for b in regions[i + 1:]:
            bx = entries[b]["pixel"]["center_x"]
            by = entries[b]["pixel"]["center_y"]
            dist = math.hypot(bx - ax, by - ay)
            if abs(dist - nominal) <= tolerance:
                entries[a]["neighbors"].append(b)
                entries[b]["neighbors"].append(a)

    for region in regions:
        entries[region]["neighbors"] = sorted(entries[region]["neighbors"])


def build_atlas(project_root: Path) -> dict:
    manifest_path = project_root / "Hex Maps" / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        regions = set(manifest.get("regions", []))
    else:
        manifest = {"regions": []}
        regions = set(POSITIONS.keys())

    entries: dict[str, dict] = {}
    for region, (col, row) in POSITIONS.items():
        px, py = paste_xy(col, row)
        entries[region] = {
            "region": region,
            "display_name": display_name(region),
            "stitch": {
                "column": col,
                "row": row,
            },
            "pixel": {
                "tile_x": px,
                "tile_y": py,
                "tile_w": TILE_W,
                "tile_h": TILE_H,
                "center_x": px + (TILE_W / 2.0),
                "center_y": py + (TILE_H / 2.0),
            },
        }

    build_neighbors(entries)

    layout_set = set(entries.keys())
    missing_from_layout = sorted(regions - layout_set)
    not_in_manifest = sorted(layout_set - regions)

    if not manifest_path.exists():
        # In fallback mode we use the built-in layout as the full atlas.
        missing_from_layout = []
        not_in_manifest = []

    atlas = {
        "schema_version": 2,
        "source": {
            "manifest": "Hex Maps/manifest.json" if manifest_path.exists() else "missing (fallback to built-in layout)",
            "layout_basis": "User-defined explicit grid (vertical 1, horizontal 0.5 units)",
        },
        "tile": {
            "width": TILE_W,
            "height": TILE_H,
            "x_step": X_STEP,
            "y_step": Y_STEP,
            "scale_x": SCALE_X,
            "scale_y": SCALE_Y,
        },
        "summary": {
            "manifest_region_count": len(regions),
            "atlas_region_count": len(entries),
            "missing_from_layout": missing_from_layout,
            "not_in_manifest": not_in_manifest,
        },
        "regions": entries,
    }
    return atlas


def build_atlas_file(project_root: Path) -> Path:
    atlas = build_atlas(project_root)
    out_path = project_root / "Hex Maps" / "global_hex_atlas.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(atlas, indent=2), encoding="utf-8")
    return out_path


def main() -> None:
    project_root = Path(__file__).resolve().parent
    atlas = build_atlas(project_root)
    out_path = build_atlas_file(project_root)

    summary = atlas["summary"]
    print(
        f"wrote {out_path} | atlas={summary['atlas_region_count']} "
        f"manifest={summary['manifest_region_count']} "
        f"missing={len(summary['missing_from_layout'])} extra={len(summary['not_in_manifest'])}"
    )


if __name__ == "__main__":
    main()
