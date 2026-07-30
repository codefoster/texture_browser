# -*- mode: python ; coding: utf-8 -*-
# Single spec for all platforms: `pyinstaller TextureBrowser.spec`.
# On macOS PyInstaller converts the PNG icon to .icns via Pillow
# (already a hard dependency) and wraps the exe in a .app bundle.

import sys

APP_ICON = 'assets/app_icon.ico' if sys.platform == 'win32' else 'assets/app_icon.png'

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets/app_icon.ico', 'assets'),
        ('assets/app_icon.png', 'assets'),
        ('assets/stollnation_cool_logo_for_a_program_called_Texture_Browser_ju_6450916f-8510-416e-ab27-ceb00f104fbc_0.png', 'assets'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='TextureBrowser',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=APP_ICON,
)

if sys.platform == 'darwin':
    app = BUNDLE(
        exe,
        name='TextureBrowser.app',
        icon='assets/app_icon.png',
        bundle_identifier='com.stollnation.texturebrowser',
    )
