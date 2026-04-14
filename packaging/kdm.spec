# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Kalupura Download Manager (KDM)
# Run from repo root:  pyinstaller packaging/kdm.spec
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

# SPECPATH is injected by PyInstaller (directory that contains this .spec file)
ROOT = Path(SPECPATH).parent

datas = [(str(ROOT / "translations.json"), ".")]
cfg = ROOT / "kdm_config.json"
if cfg.is_file():
    datas.append((str(cfg), "."))

datas_pyqt, binaries_pyqt, hidden_pyqt = collect_all("PyQt6")

a = Analysis(
    [str(ROOT / "kdm.py")],
    pathex=[str(ROOT)],
    binaries=binaries_pyqt,
    datas=datas + datas_pyqt,
    hiddenimports=list(
        {
            *hidden_pyqt,
            "yt_dlp",
            "certifi",
            "requests",
            "urllib3",
            "charset_normalizer",
            "idna",
            "playwright",
            "playwright.sync_api",
            "kdm.licensing",
        }
    ),
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
    name="KDM",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="KDM",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="KDM.app",
        icon=None,
        bundle_identifier="com.kalupura.kdm",
        info_plist={
            "NSHighResolutionCapable": True,
            "CFBundleName": "KDM",
            "CFBundleDisplayName": "Kalupura Download Manager",
        },
    )
