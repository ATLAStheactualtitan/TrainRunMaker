from pathlib import Path
import sys

project_root = Path(SPECPATH)
is_macos = sys.platform == "darwin"
is_windows = sys.platform == "win32"

a = Analysis(
    [str(project_root / "foxhole_train_run_app.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        (str(project_root / "Hex Maps" / "global_hex_atlas.json"), "Hex Maps"),
        (str(project_root / "Hex Maps" / "cargo_items.txt"), "Hex Maps"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    icon=str(project_root / "assets" / "FoxholeTrainRunMaker.ico") if is_windows else None,
    name="FoxholeTrainRunMaker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name="FoxholeTrainRunMaker",
)

if is_macos:
    app = BUNDLE(
        coll,
        name="FoxholeTrainRunMaker.app",
        icon=str(project_root / "assets" / "FoxholeTrainRunMaker.icns"),
        bundle_identifier="com.cmrc.foxholetrainrunmaker",
    )
