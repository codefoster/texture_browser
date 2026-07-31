# -*- mode: python ; coding: utf-8 -*-
# Single spec for all platforms: `pyinstaller TextureBrowser.spec`.
# On macOS PyInstaller converts the PNG icon to .icns via Pillow
# (already a hard dependency) and wraps the exe in a .app bundle.

import sys
from pathlib import Path

APP_ICON = 'assets/app_icon.ico' if sys.platform == 'win32' else 'assets/app_icon.png'


renderer_datas = [
    ('VERSION', '.'),
    ('godot_material_renderer/project.godot', 'godot_material_renderer'),
    ('godot_material_renderer/scenes', 'godot_material_renderer/scenes'),
    ('godot_material_renderer/scripts', 'godot_material_renderer/scripts'),
    ('godot_material_renderer/assets', 'godot_material_renderer/assets'),
]
renderer_build = Path('godot_material_renderer/build')
if renderer_build.is_dir():
    for renderer_file in renderer_build.iterdir():
        if renderer_file.is_file():
            renderer_datas.append((str(renderer_file), 'godot_material_renderer'))

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets/app_icon.ico', 'assets'),
        ('assets/app_icon.png', 'assets'),
        ('assets/stollnation_cool_logo_for_a_program_called_Texture_Browser_ju_6450916f-8510-416e-ab27-ceb00f104fbc_0.png', 'assets'),
        *renderer_datas,
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
