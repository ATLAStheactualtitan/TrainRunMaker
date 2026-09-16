from pathlib import Path
import sys

project_root = Path(SPECPATH)

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

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="FoxholeTrainRunMaker.app",
        icon=None,
        bundle_identifier="com.cmrc.foxholetrainrunmaker",
    )
