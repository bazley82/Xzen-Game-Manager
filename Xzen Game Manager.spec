# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path


def source_datas():
    excluded_parts = {
        '__pycache__',
        'backups',
        'user_settings',
    }
    datas = []
    for path in Path('source').rglob('*'):
        if not path.is_file():
            continue
        if any(part.lower() in excluded_parts for part in path.parts):
            continue
        rel_parent = str(path.parent)
        datas.append((str(path), rel_parent))
    return datas


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=source_datas(),
    hiddenimports=[
        'source.xzen_engine',
        'source.xzen_engine.auto_monitor',
        'source.xzen_engine.compressibility',
        'source.xzen_engine.workers',
        'source.xzen_engine.background_controller',
        'source.xzen_engine.background_jobs',
        'source.xzen_engine.storage',
        'source.xzen_engine.system',
        'source.xzen_engine.stores',
        'source.xzen_engine.steam',
        'source.xzen_engine.posters',
        'source.xzen_engine.formatting',
        'source.xzen_engine.theme',
        'source.xzen_engine.constants',
        'source.xzen_engine.app_state',
        'source.tabs.game_library',
        'source.tabs.settings',
        'source.tabs.xgcr_fsr_mods',
        'source.logs',
        'source.logs.action_logger',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

icon_path = 'source/assets/xzen.ico' if os.path.exists('source/assets/xzen.ico') else 'source\\assets\\xzen.ico'

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    a.zipfiles,
    [],
    name='Xzen Game Manager',
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
    icon=[icon_path] if os.path.exists(icon_path) else None,
)
