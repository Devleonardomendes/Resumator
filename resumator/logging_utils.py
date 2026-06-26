from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
import traceback


APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
LOG_PATH = APP_DIR / "resumator-11.0.log"


def write_log(message: str) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with LOG_PATH.open("a", encoding="utf-8") as log_file:
            log_file.write(f"[{timestamp}] {message}\n")
    except Exception:
        pass


def write_exception(context: str, exc: BaseException) -> None:
    details = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    write_log(f"{context}: {details}")


def collect_logs(extra_paths: list[Path] | None = None) -> str:
    lines = [
        "LOGS DO RESUMATOR 10",
        f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
        f"Pasta do aplicativo: {APP_DIR}",
        "",
    ]

    paths = [LOG_PATH, APP_DIR / "resumator-automation.log"]
    if extra_paths:
        paths.extend(extra_paths)

    seen: set[Path] = set()
    found = False
    for path in paths:
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        if resolved in seen:
            continue
        seen.add(resolved)
        if not path.exists():
            continue
        found = True
        lines.extend([f"===== {path} =====", ""])
        try:
            lines.append(path.read_text(encoding="utf-8", errors="replace"))
        except OSError as exc:
            lines.append(f"Não foi possível ler este log: {exc}")
        lines.append("")

    if not found:
        lines.append("Nenhum arquivo de log foi encontrado.")

    return "\n".join(lines).strip() + "\n"
