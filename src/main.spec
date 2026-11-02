# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for macOS, Windows and Linux - build with `python build.py`
# (each OS can only build its own app). BUNDLE (the .app) is skipped off macOS.
import os
from PyInstaller.utils.hooks import collect_all

APP_NAME = 'Eirekes-Manager'

datas = [(os.path.join(SPECPATH, 'artists.json'), '.')]  # bundled artist list
binaries = []
hiddenimports = []
tmp_ret = collect_all('PyQt6')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    [os.path.join(SPECPATH, 'main.py')],
    pathex=[SPECPATH],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pytest'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_NAME,
)
app = BUNDLE(
    coll,
    name='Eirekes-manager.app',
    icon=None,
    bundle_identifier=None,
)
