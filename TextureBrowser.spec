# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


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
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/app_icon.ico',
)
