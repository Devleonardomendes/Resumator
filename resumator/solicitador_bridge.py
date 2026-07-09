from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable
import json
import os
import subprocess
import sys
import tempfile


APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
SOLICITADOR_TARGETS = (
    ("QUIMERA ULTIMATE 2.0", "QUIMERA ULTIMATE 2.0.exe"),
    ("QUIMERA", "QUIMERA.exe"),
    ("Quimera", "QUIMERA.exe"),
)


@dataclass
class SolicitadorExportResult:
    ok: bool
    message: str
    payload_path: Path | None = None
    target: str | None = None
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SolicitadorTarget:
    command: tuple[str, ...]
    cwd: Path
    label: str


def export_summary_to_solicitador(
    summary_text: str,
    prompt_name: str | None = None,
    source_pdf: Path | Iterable[Path] | None = None,
) -> SolicitadorExportResult:
    summary = summary_text.strip()
    if not summary:
        return SolicitadorExportResult(False, "Cole ou capture a resposta antes de acionar o QUIMERA.")

    payload_path = _write_payload(summary, prompt_name, source_pdf)
    targets = _candidate_targets(payload_path)
    if not targets:
        return SolicitadorExportResult(
            False,
            "Quimera não operacional",
            payload_path=payload_path,
        )

    errors: list[str] = []
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    for target in targets:
        try:
            subprocess.Popen(list(target.command), cwd=str(target.cwd), creationflags=creationflags)
            return SolicitadorExportResult(
                True,
                "Resumo enviado ao QUIMERA.",
                payload_path=payload_path,
                target=target.label,
            )
        except Exception as exc:  # noqa: BLE001 - try the next known target
            errors.append(f"{target.label}: {exc}")

    return SolicitadorExportResult(
        False,
        "Quimera não operacional",
        payload_path=payload_path,
        notes=errors,
    )


def _write_payload(
    summary: str,
    prompt_name: str | None,
    source_pdf: Path | Iterable[Path] | None,
) -> Path:
    output_dir = Path(tempfile.gettempdir()) / "resumator-11.2-quimera"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"resumo-quimera-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    source_pdfs = _normalize_source_pdfs(source_pdf)
    payload = {
        "version": 1,
        "source": "Resumator 11.2",
        "target": "QUIMERA",
        "type": "resumo_peticao_inicial",
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "prompt": prompt_name,
        "arquivos_analisados": [path.name for path in source_pdfs],
        "caminhos_arquivos": [str(path) for path in source_pdfs],
        "resumo": summary,
        "resumo_peticao": summary,
        "resumo_da_peticao": summary,
        "content": summary,
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def _candidate_targets(payload_path: Path) -> list[SolicitadorTarget]:
    targets: list[SolicitadorTarget] = []
    seen: set[tuple[str, ...]] = set()

    if not getattr(sys, "frozen", False):
        for app_path in _candidate_source_app_paths():
            for python_exe in _candidate_python_executables():
                command = (str(python_exe), str(app_path), "--summary-file", str(payload_path))
                if command in seen:
                    continue
                seen.add(command)
                targets.append(SolicitadorTarget(command=command, cwd=app_path.parent, label=str(app_path)))

    for exe_path in _candidate_exe_paths():
        command = (str(exe_path), "--summary-file", str(payload_path))
        if command in seen:
            continue
        seen.add(command)
        targets.append(SolicitadorTarget(command=command, cwd=exe_path.parent, label=str(exe_path)))

    return targets


def _candidate_exe_paths() -> list[Path]:
    candidates: list[Path] = []

    for base_dir in _candidate_base_dirs():
        for dir_name, exe_name in SOLICITADOR_TARGETS:
            candidates.extend(
                [
                    base_dir / dir_name / "dist-py314" / dir_name / exe_name,
                    base_dir / dir_name / exe_name,
                ]
            )

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        for dir_name, exe_name in SOLICITADOR_TARGETS:
            candidates.append(Path(local_app_data) / "Programs" / dir_name / exe_name)

    return _existing_unique_paths(candidates)


def _candidate_source_app_paths() -> list[Path]:
    candidates: list[Path] = []
    for base_dir in _candidate_base_dirs():
        for dir_name, _ in SOLICITADOR_TARGETS:
            candidates.append(base_dir / dir_name / "app.py")
    return _existing_unique_paths(candidates)


def _candidate_base_dirs() -> list[Path]:
    candidates = [APP_DIR, Path.cwd()]
    candidates.extend(APP_DIR.parents)
    candidates.extend(Path.cwd().parents)
    candidates.append(Path(r"S:\Backup da Pasta Trabalho"))
    return _unique_paths(candidates)


def _candidate_python_executables() -> list[Path]:
    candidates = [
        Path(r"C:\Users\Leonardo\AppData\Local\Programs\Python\Python314\python.exe"),
        Path(sys.executable),
    ]
    py_launcher = _which("py")
    if py_launcher:
        candidates.append(py_launcher)
    python = _which("python")
    if python:
        candidates.append(python)
    return _existing_unique_paths(candidates)


def _which(name: str) -> Path | None:
    for raw_dir in os.environ.get("PATH", "").split(os.pathsep):
        if not raw_dir:
            continue
        candidate = Path(raw_dir) / name
        if candidate.exists():
            return candidate
        if os.name == "nt":
            candidate_exe = candidate.with_suffix(".exe")
            if candidate_exe.exists():
                return candidate_exe
    return None


def _normalize_source_pdfs(source_pdf: Path | Iterable[Path] | None) -> list[Path]:
    if source_pdf is None:
        return []
    if isinstance(source_pdf, Path):
        return [source_pdf]
    return [Path(path) for path in source_pdf]


def _existing_unique_paths(paths: Iterable[Path]) -> list[Path]:
    return [path for path in _unique_paths(paths) if path.exists()]


def _unique_paths(paths: Iterable[Path]) -> list[Path]:
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        try:
            key = str(path.resolve()).casefold()
        except OSError:
            key = str(path).casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique

