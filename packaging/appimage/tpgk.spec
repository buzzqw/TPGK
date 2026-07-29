# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

datas, binaries, hiddenimports = collect_all('gi', include_py_files=True)

# Collect gobject-introspection typelib data (Debian/Ubuntu multiarch + fallback)
datas += [('/usr/lib/girepository-1.0', './girepository-1.0')]
import glob as _glob
for _d in _glob.glob('/usr/lib/*/girepository-1.0'):
    datas.append((_d, './girepository-1.0'))

a = Analysis(
    [os.path.join(SPECPATH, '..', '..', 'tpgk', '__main__.py')],
    pathex=[os.path.join(SPECPATH, '..', '..')],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + [
        'gi.repository.Gtk',
        'gi.repository.Gdk',
        'gi.repository.Vte',
        'gi.repository.GLib',
        'gi.repository.Gio',
        'gi.repository.Pango',
        'gi.repository.cairo',
        'cairo',
        'requests',
        'psutil',
        'sqlite3',
        'json',
        'os',
        'sys',
        'threading',
        'tempfile',
        'subprocess',
        'datetime',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='tpgk',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
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
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='tpgk',
)
