# -*- mode: python ; coding: utf-8 -*-
import importlib.util
from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import collect_submodules


project_dir = Path.cwd()
vendor_dir = project_dir / "vendor"
if vendor_dir.exists():
    sys.path.insert(0, str(vendor_dir))


def require_package(package_name):
    if importlib.util.find_spec(package_name) is None:
        raise RuntimeError(
            f"Dependencia obrigatoria ausente para gerar o Resumator 11.4: {package_name}. "
            f"Instale o pacote antes de executar o PyInstaller."
        )


datas = [
    ("data/prompts.json", "data"),
    ("README.txt", "."),
    ("assets/robot.ico", "assets"),
    ("assets/robot-logo.png", "assets"),
    ("assets/robot-banner.png", "assets"),
    ("assets/export-success.webp", "assets"),
    ("assets/export-success.wav", "assets"),
]
hiddenimports = [
    "pythoncom",
    "win32clipboard",
    "win32con",
    "win32gui",
    "win32com",
    "win32com.client",
    "win32com.propsys",
    "win32com.propsys.propsys",
    "win32com.propsys.pscon",
]
for package_name in ("docx", "reportlab", "PIL"):
    require_package(package_name)
    datas += collect_data_files(package_name)
    hiddenimports += collect_submodules(package_name)

if importlib.util.find_spec("tkinterdnd2") is not None:
    datas += collect_data_files("tkinterdnd2")
    hiddenimports += collect_submodules("tkinterdnd2")


a = Analysis(
    ["app.py"],
    pathex=[str(vendor_dir)] if vendor_dir.exists() else [],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
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
    [],
    exclude_binaries=True,
    name="Resumator 11.4",
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
    icon="assets/robot.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Resumator 11.4",
)
