# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path


project_dir = Path.cwd()

a = Analysis(
    [str(project_dir / "installer" / "setup_installer.py")],
    pathex=[],
    binaries=[],
    datas=[
        (str(project_dir / "installer" / "payload" / "Resumator10-app.zip"), "."),
        (str(project_dir / "installer" / "payload" / "prompts.json"), "."),
        (str(project_dir / "installer" / "payload" / "README.txt"), "."),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name="Resumator 10 Setup",
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
    icon=str(project_dir / "assets" / "robot.ico"),
)
