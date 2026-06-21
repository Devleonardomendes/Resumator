from __future__ import annotations

import ctypes
import os
from pathlib import Path
import sys


_TCL_DLL = None


def _initialize_tcl_runtime() -> None:
    global _TCL_DLL

    if os.name != "nt" or _TCL_DLL is not None:
        return

    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
        tcl_data = meipass / "_tcl_data"
        tk_data = meipass / "_tk_data"
        if tcl_data.exists():
            os.environ["TCL_LIBRARY"] = str(tcl_data)
        if tk_data.exists():
            os.environ["TK_LIBRARY"] = str(tk_data)
        if os.environ.get("TCL_LIBRARY") and os.environ.get("TK_LIBRARY"):
            return

    base_dirs = [Path(sys.base_prefix), Path(sys.prefix), Path(sys.executable).resolve().parent]
    if getattr(sys, "frozen", False):
        base_dirs.insert(0, Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent)))

    for base_dir in base_dirs:
        dll_candidates = [base_dir / "DLLs" / "tcl86t.dll", base_dir / "tcl86t.dll"]
        dll_path = next((candidate for candidate in dll_candidates if candidate.exists()), None)
        if dll_path is None:
            continue
        try:
            tcl = ctypes.CDLL(str(dll_path))
            tcl.Tcl_FindExecutable.argtypes = [ctypes.c_char_p]
            executable_for_tcl = base_dir / "python.exe" if getattr(sys, "frozen", False) else Path(sys.executable)
            tcl.Tcl_FindExecutable(str(executable_for_tcl).encode("utf-8"))
            _TCL_DLL = tcl
        except Exception:
            pass
        return


_initialize_tcl_runtime()
