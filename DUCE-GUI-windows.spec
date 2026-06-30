# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files

a = Analysis(
    ['gui.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('default-duce-gui-settings.json', '.'),
        ('README.md', '.'),
        ('LICENSE', '.')
    ] + collect_data_files('customtkinter'),
    hiddenimports=[
        'duce',
        'duce.core',
        'duce.core.client',
        'duce.core.config',
        'duce.core.cookies',
        'duce.core.db',
        'duce.core.exceptions',
        'duce.core.images',
        'duce.core.models',
        'duce.scrapers',
        'duce.scrapers.base_scraper',
        'duce.scrapers.cj',
        'duce.scrapers.cs',
        'duce.scrapers.cv',
        'duce.scrapers.cxyz',
        'duce.scrapers.du',
        'duce.scrapers.en',
        'duce.scrapers.idc',
        'duce.scrapers.rd',
        'duce.scrapers.tb',
        'duce.scrapers.uf',
        'duce.utils',
        'duce.utils.html',
        'duce.utils.network',
        'duce.utils.url'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['rich', 'unittest', 'pydoc'],
    noarchive=False,
    optimize=2,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='DUCE-GUI-windows',
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
    icon=['extra/DUCE-LOGO.ico'],
)
