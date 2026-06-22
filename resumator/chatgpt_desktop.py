from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import ctypes
from ctypes import wintypes
import json
import os
import platform
import struct
import subprocess
import sys
import time
from typing import Iterable


IS_WINDOWS = platform.system().lower() == "windows"
APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
LOG_PATH = APP_DIR / "resumator-automation.log"

try:
    import win32clipboard  # type: ignore
    import win32con  # type: ignore
    import win32gui  # type: ignore
except ImportError:  # pragma: no cover - depends on Windows packages
    win32clipboard = None
    win32con = None
    win32gui = None


@dataclass
class AutomationResult:
    ok: bool
    message: str
    window_title: str | None = None
    notes: list[str] = field(default_factory=list)
    text: str = ""


class AutomationError(RuntimeError):
    pass


@dataclass
class AttachmentResult:
    attached: bool
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AssistantTarget:
    hwnd: int | None
    title: str
    pid: int | None = None
    candidate_pids: tuple[int, ...] = ()
    note: str | None = None


@dataclass(frozen=True)
class DesktopAssistant:
    key: str
    display_name: str
    window_keywords: tuple[str, ...]
    process_keywords: tuple[str, ...] = ()
    launch_paths: tuple[str, ...] = ()
    launch_commands: tuple[tuple[str, ...], ...] = ()
    launch_urls: tuple[str, ...] = ()
    attachment_wait_seconds: float = 2.2
    require_visible_window: bool = False
    supports_clipboard_file_paste: bool = True
    supports_file_dialog_attachment: bool = False
    trust_clipboard_attachment_fallback: bool = False
    attachment_button_terms: tuple[str, ...] = (
        "anexar",
        "anexo",
        "attach",
        "attachment",
        "adicionar arquivo",
        "adicionar conteudo",
        "adicionar conteúdo",
        "adicionar e gerenciar fontes",
        "gerenciar fontes",
        "fontes",
        "add content",
        "add file",
        "add sources",
        "manage sources",
        "sources",
        "upload",
        "paperclip",
        "clip",
        "plus",
        "+",
    )
    attachment_menu_terms: tuple[str, ...] = (
        "carregar arquivo",
        "carregar arquivos",
        "upload file",
        "upload files",
        "upload from this device",
        "attach file",
        "attach files",
        "adicionar arquivo",
        "adicionar arquivos",
        "adicionar fontes",
        "add sources",
        "sources",
        "do computador",
        "do dispositivo",
        "from computer",
        "from this device",
        "arquivo",
        "arquivos",
        "procurar",
        "browse",
    )
    response_copy_terms: tuple[str, ...] = (
        "copiar",
        "copiar resposta",
        "copiar texto",
        "copy",
        "copy response",
        "copy text",
        "copy to clipboard",
        "copied",
        "clipboard",
    )
    launch_urls_first: bool = False


ASSISTANTS: dict[str, DesktopAssistant] = {
    "chatgpt": DesktopAssistant(
        key="chatgpt",
        display_name="ChatGPT Desktop",
        window_keywords=("chatgpt",),
        process_keywords=("chatgpt",),
        launch_paths=(
            r"%LOCALAPPDATA%\Programs\ChatGPT\ChatGPT.exe",
            r"%LOCALAPPDATA%\Microsoft\WindowsApps\ChatGPT.exe",
            r"C:\Program Files\ChatGPT\ChatGPT.exe",
        ),
        launch_urls=("chatgpt://",),
    ),
    "copilot": DesktopAssistant(
        key="copilot",
        display_name="Microsoft 365 Copilot",
        window_keywords=("microsoft 365 copilot", "microsoft 365", "m365", "copilot"),
        process_keywords=("copilot", "officehub", "microsoft365", "m365"),
        launch_commands=(
            (
                "explorer.exe",
                r"shell:AppsFolder\Microsoft.MicrosoftOfficeHub_8wekyb3d8bbwe!Microsoft.MicrosoftOfficeHub",
            ),
            ("explorer.exe", r"shell:AppsFolder\Microsoft.Copilot_8wekyb3d8bbwe!App"),
        ),
        launch_urls=("https://m365.cloud.microsoft/chat", "https://copilot.microsoft.com/"),
        attachment_wait_seconds=3.0,
        require_visible_window=True,
        supports_clipboard_file_paste=False,
        supports_file_dialog_attachment=True,
        trust_clipboard_attachment_fallback=True,
        launch_urls_first=True,
    ),
    "claude": DesktopAssistant(
        key="claude",
        display_name="Claude Desktop",
        window_keywords=("claude", "anthropic"),
        process_keywords=("claude", "anthropicclaude"),
        launch_paths=(
            r"%LOCALAPPDATA%\Programs\Claude\Claude.exe",
            r"%LOCALAPPDATA%\AnthropicClaude\Claude.exe",
            r"%LOCALAPPDATA%\AnthropicClaude\app-*\Claude.exe",
            r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Claude.lnk",
            r"%USERPROFILE%\Desktop\Claude.lnk",
            r"%PUBLIC%\Desktop\Claude.lnk",
        ),
        launch_commands=(
            (r"%LOCALAPPDATA%\AnthropicClaude\Update.exe", "--processStart", "Claude.exe"),
        ),
        attachment_wait_seconds=3.0,
        supports_clipboard_file_paste=False,
        supports_file_dialog_attachment=True,
    ),
    "gemini": DesktopAssistant(
        key="gemini",
        display_name="Google Gemini",
        window_keywords=("google gemini", "gemini"),
        launch_paths=(
            r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Chrome Apps\Google Gemini.lnk",
            r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Google Gemini.lnk",
            r"%USERPROFILE%\Desktop\Google Gemini.lnk",
            r"%PUBLIC%\Desktop\Google Gemini.lnk",
        ),
        launch_urls=("https://gemini.google.com/app", "https://gemini.google.com/"),
        attachment_wait_seconds=3.0,
        require_visible_window=True,
        supports_clipboard_file_paste=False,
        supports_file_dialog_attachment=True,
    ),
    "lmstudio": DesktopAssistant(
        key="lmstudio",
        display_name="LM Studio Desktop",
        window_keywords=("lm studio", "lmstudio", "lm-studio"),
        process_keywords=("lm studio", "lmstudio", "lm-studio"),
        launch_paths=(
            r"%LOCALAPPDATA%\Programs\LM Studio\LM Studio.exe",
            r"C:\Program Files\LM Studio\LM Studio.exe",
        ),
        attachment_wait_seconds=4.0,
    ),
    "jusia": DesktopAssistant(
        key="jusia",
        display_name="Jus IA",
        window_keywords=("jus ia", "ia jusbrasil", "jusbrasil", "ia.jusbrasil.com.br"),
        launch_commands=(
            (
                r"%ProgramFiles%\Google\Chrome\Application\chrome_proxy.exe",
                "--profile-directory=Default",
                "--app-id=abdohjhbhkncbpojnjfhagolpokkcpll",
            ),
            (
                r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome_proxy.exe",
                "--profile-directory=Default",
                "--app-id=abdohjhbhkncbpojnjfhagolpokkcpll",
            ),
            (
                r"%LOCALAPPDATA%\Google\Chrome\Application\chrome_proxy.exe",
                "--profile-directory=Default",
                "--app-id=abdohjhbhkncbpojnjfhagolpokkcpll",
            ),
        ),
        launch_urls=("https://ia.jusbrasil.com.br/",),
        attachment_wait_seconds=3.5,
    ),
}


def assistant_display_name(assistant_key: str) -> str:
    assistant = ASSISTANTS.get(assistant_key)
    return assistant.display_name if assistant else assistant_key


def open_desktop_assistant(assistant_key: str) -> AutomationResult:
    assistant = ASSISTANTS.get(assistant_key)
    if assistant is None:
        return AutomationResult(False, f"Assistente nao configurado: {assistant_key}.")

    if not IS_WINDOWS:
        return AutomationResult(False, f"A automacao do {assistant.display_name} so esta disponivel no Windows.")

    target = _resolve_assistant_target(assistant)
    if target is None:
        return AutomationResult(
            False,
            _missing_target_message(assistant, opening=True),
        )

    notes: list[str] = []
    if target.note:
        notes.append(target.note)

    try:
        _activate_assistant_target(target)
    except Exception as exc:  # noqa: BLE001 - opening is best-effort on selection
        notes.append(f"Nao foi possivel trazer a janela para frente: {exc}")

    return AutomationResult(True, f"{assistant.display_name} pronto.", target.title, notes)


def find_chatgpt_windows() -> list[tuple[int, str]]:
    return find_assistant_windows("chatgpt")


def find_lmstudio_windows() -> list[tuple[int, str]]:
    return find_assistant_windows("lmstudio")


def find_assistant_windows(assistant_key: str) -> list[tuple[int, str]]:
    if not IS_WINDOWS:
        return []

    assistant = ASSISTANTS.get(assistant_key)
    if assistant is None:
        return []

    if win32gui is None:
        return _find_assistant_windows_ctypes(assistant)

    windows: list[tuple[int, str]] = []

    def collect(hwnd: int, _: object) -> bool:
        if not win32gui.IsWindowVisible(hwnd):
            return True
        title = win32gui.GetWindowText(hwnd).strip()
        process_text = _process_text_for_window(hwnd)
        if _matches_assistant_window(title, process_text, assistant):
            windows.append((hwnd, title or _window_fallback_title(process_text, assistant)))
        return True

    try:
        win32gui.EnumWindows(collect, None)
    except Exception as exc:  # noqa: BLE001 - pywin32 may fail when no desktop windows are visible
        _log_automation(f"{assistant.display_name}: falha no EnumWindows via pywin32: {exc!r}")
        return _find_assistant_windows_ctypes(assistant)
    return windows


def _find_assistant_windows_ctypes(assistant: DesktopAssistant) -> list[tuple[int, str]]:
    user32 = ctypes.windll.user32
    user32.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM), wintypes.LPARAM]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int

    windows: list[tuple[int, str]] = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def collect(hwnd: int, _: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            title = ""
        else:
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            title = buffer.value.strip()
        process_text = _process_text_for_window(int(hwnd))
        if _matches_assistant_window(title, process_text, assistant):
            windows.append((int(hwnd), title or _window_fallback_title(process_text, assistant)))
        return True

    user32.EnumWindows(callback_type(collect), 0)
    return windows


def _matches_assistant_window(title: str, process_text: str, assistant: DesktopAssistant) -> bool:
    title_folded = title.casefold()
    if title and any(keyword.casefold() in title_folded for keyword in assistant.window_keywords):
        return True

    process_folded = process_text.casefold()
    return bool(
        process_text
        and any(keyword.casefold() in process_folded for keyword in assistant.process_keywords)
    )


def _window_fallback_title(process_text: str, assistant: DesktopAssistant) -> str:
    if process_text:
        return Path(process_text).name or process_text
    return assistant.display_name


def _process_text_for_window(hwnd: int) -> str:
    if not IS_WINDOWS:
        return ""

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    process_id = wintypes.DWORD()

    try:
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(process_id))
        if not process_id.value:
            return ""

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, process_id.value)
        if not handle:
            return ""
        try:
            buffer = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(buffer))
            kernel32.QueryFullProcessImageNameW.argtypes = [
                wintypes.HANDLE,
                wintypes.DWORD,
                wintypes.LPWSTR,
                ctypes.POINTER(wintypes.DWORD),
            ]
            kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
            if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                return buffer.value.strip()
        finally:
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle(handle)
    except Exception:
        return ""
    return ""


def _resolve_assistant_target(assistant: DesktopAssistant) -> AssistantTarget | None:
    windows = find_assistant_windows(assistant.key)
    if windows:
        hwnd, title = windows[0]
        return AssistantTarget(hwnd=hwnd, title=title)

    if assistant.require_visible_window:
        launched, _ = _launch_assistant(assistant)
        if launched:
            windows = _wait_for_assistant_window(assistant, timeout_seconds=10.0)
            if windows:
                hwnd, title = windows[0]
                return AssistantTarget(hwnd=hwnd, title=title, note="Chat aberto automaticamente.")
        return None

    processes = _find_assistant_processes(assistant)
    if processes:
        launched, _ = _launch_assistant(assistant)
        if launched:
            time.sleep(2.0)
            windows = find_assistant_windows(assistant.key)
            if windows:
                hwnd, title = windows[0]
                return AssistantTarget(hwnd=hwnd, title=title, note="Aplicativo aberto automaticamente.")
            processes = _find_assistant_processes(assistant) or processes

        pid, name, path = processes[0]
        title = Path(path).name if path else name
        return AssistantTarget(
            hwnd=None,
            title=title or assistant.display_name,
            pid=pid,
            candidate_pids=tuple(process_pid for process_pid, _, _ in processes),
            note=f"{assistant.display_name} localizado pelo processo do Windows.",
        )

    launched, launched_pid = _launch_assistant(assistant)
    if not launched:
        return None

    time.sleep(2.0)
    windows = find_assistant_windows(assistant.key)
    if windows:
        hwnd, title = windows[0]
        return AssistantTarget(hwnd=hwnd, title=title, note="Aplicativo aberto automaticamente.")

    processes = _find_assistant_processes(assistant)
    if processes:
        pid, name, path = processes[0]
        title = Path(path).name if path else name
        return AssistantTarget(
            hwnd=None,
            title=title or assistant.display_name,
            pid=pid,
            candidate_pids=tuple(process_pid for process_pid, _, _ in processes),
            note="Aplicativo aberto e localizado pelo processo do Windows.",
        )

    if launched_pid is None:
        return None

    return AssistantTarget(
        hwnd=None,
        title=assistant.display_name,
        pid=launched_pid,
        candidate_pids=(launched_pid,),
        note="Aplicativo aberto automaticamente.",
    )


def _find_assistant_processes(assistant: DesktopAssistant) -> list[tuple[int, str, str]]:
    if not IS_WINDOWS:
        return []

    kernel32 = ctypes.windll.kernel32
    TH32CS_SNAPPROCESS = 0x00000002
    INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == INVALID_HANDLE_VALUE:
        return []

    results: list[tuple[int, str, str]] = []
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
        kernel32.Process32FirstW.restype = wintypes.BOOL
        kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
        kernel32.Process32NextW.restype = wintypes.BOOL

        has_entry = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while has_entry:
            pid = int(entry.th32ProcessID)
            name = entry.szExeFile
            path = _process_image_path(pid)
            folded = f"{name} {path}".casefold()
            if any(keyword.casefold() in folded for keyword in assistant.process_keywords):
                results.append((pid, name, path))
            has_entry = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle(snapshot)

    return results


def _process_image_path(pid: int) -> str:
    if not IS_WINDOWS:
        return ""

    kernel32 = ctypes.windll.kernel32
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""

    try:
        buffer = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(buffer))
        kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return buffer.value.strip()
    finally:
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle(handle)
    return ""


def _launch_assistant(assistant: DesktopAssistant) -> tuple[bool, int | None]:
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    if assistant.launch_urls_first:
        launched, launched_pid = _launch_assistant_urls(assistant)
        if launched:
            return launched, launched_pid

    for path in _candidate_launch_paths(assistant.launch_paths):
        if not path.exists():
            continue
        try:
            if path.suffix.casefold() in {".lnk", ".url"}:
                os.startfile(str(path))  # type: ignore[attr-defined]
                _log_automation(f"{assistant.display_name}: atalho aberto: {path}")
                return True, None
            process = subprocess.Popen([str(path)], cwd=str(path.parent), creationflags=creationflags)
            _log_automation(f"{assistant.display_name}: executavel aberto: {path}")
            return True, int(process.pid)
        except Exception as exc:  # noqa: BLE001 - best-effort fallback
            _log_automation(f"{assistant.display_name}: falha ao abrir {path}: {exc!r}")

    for raw_command in assistant.launch_commands:
        command = tuple(os.path.expandvars(part) for part in raw_command)
        try:
            process = subprocess.Popen(list(command), creationflags=creationflags)
            _log_automation(f"{assistant.display_name}: comando de abertura executado: {command}")
            return True, int(process.pid)
        except Exception as exc:  # noqa: BLE001 - best-effort fallback
            _log_automation(f"{assistant.display_name}: falha ao executar {command}: {exc!r}")

    if not assistant.launch_urls_first:
        launched, launched_pid = _launch_assistant_urls(assistant)
        if launched:
            return launched, launched_pid

    return False, None


def _candidate_launch_paths(raw_paths: tuple[str, ...]) -> list[Path]:
    candidates: list[Path] = []
    for raw_path in raw_paths:
        expanded = os.path.expandvars(raw_path)
        if "*" not in expanded and "?" not in expanded:
            candidates.append(Path(expanded))
            continue

        pattern_path = Path(expanded)
        parent = pattern_path.parent
        if not parent.exists():
            continue
        candidates.extend(sorted(parent.glob(pattern_path.name), reverse=True))
    return candidates


def _launch_assistant_urls(assistant: DesktopAssistant) -> tuple[bool, int | None]:
    for url in assistant.launch_urls:
        try:
            if os.name == "nt":
                os.startfile(url)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", url])
            _log_automation(f"{assistant.display_name}: URL de abertura acionada: {url}")
            return True, None
        except Exception as exc:  # noqa: BLE001 - best-effort fallback
            _log_automation(f"{assistant.display_name}: falha ao abrir URL {url}: {exc!r}")

    return False, None


def _wait_for_assistant_window(
    assistant: DesktopAssistant,
    timeout_seconds: float,
    interval_seconds: float = 0.7,
) -> list[tuple[int, str]]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        windows = find_assistant_windows(assistant.key)
        if windows:
            return windows
        time.sleep(interval_seconds)
    return []


def _missing_target_message(assistant: DesktopAssistant, opening: bool = False) -> str:
    if assistant.require_visible_window:
        url = assistant.launch_urls[0] if assistant.launch_urls else f"o chat do {assistant.display_name}"
        return (
            f"Nao encontrei uma janela visivel do {assistant.display_name}. "
            f"Abra {url}, clique no campo de mensagem e tente novamente."
        )
    if opening:
        return f"Nao consegui abrir ou localizar o {assistant.display_name}."
    return f"Não encontrei uma janela aberta do {assistant.display_name}. Abra o aplicativo e tente novamente."


def send_to_chatgpt_desktop(
    prompt_text: str,
    pdf_path: Path | Iterable[Path] | None,
    attach_pdf: bool = True,
    submit: bool = True,
    prompt_document_path: Path | Iterable[Path] | None = None,
    paste_prompt_text: bool = True,
) -> AutomationResult:
    return send_to_desktop_assistant(
        "chatgpt",
        prompt_text,
        pdf_path,
        attach_pdf=attach_pdf,
        submit=submit,
        prompt_document_path=prompt_document_path,
        paste_prompt_text=paste_prompt_text,
    )


def send_to_desktop_assistant(
    assistant_key: str,
    prompt_text: str,
    pdf_path: Path | Iterable[Path] | None,
    attach_pdf: bool = True,
    submit: bool = True,
    prompt_document_path: Path | Iterable[Path] | None = None,
    paste_prompt_text: bool = True,
) -> AutomationResult:
    assistant = ASSISTANTS.get(assistant_key)
    if assistant is None:
        return AutomationResult(False, f"Assistente não configurado: {assistant_key}.")

    if not IS_WINDOWS:
        return AutomationResult(False, f"A automação do {assistant.display_name} só está disponível no Windows.")

    target = _resolve_assistant_target(assistant)
    if target is None:
        _log_automation(f"{assistant.display_name}: nenhuma janela ou processo acionavel encontrado.")
        return AutomationResult(
            False,
            _missing_target_message(assistant),
        )

    title = target.title
    notes: list[str] = []
    if target.note:
        notes.append(target.note)

    try:
        _activate_assistant_target(target)
        time.sleep(0.6)

        pdf_paths = _normalize_pdf_paths(pdf_path)
        prompt_document_paths = _normalize_paths(prompt_document_path)
        attachment_paths = [*prompt_document_paths]
        if attach_pdf:
            attachment_paths.extend(pdf_paths)

        attached = False
        if attachment_paths:
            attachment_result = _attach_files_to_assistant(assistant, target, attachment_paths)
            attached = attachment_result.attached
            notes.extend(attachment_result.notes)

        if paste_prompt_text:
            message = _build_message(
                prompt_text,
                pdf_paths,
                attached=bool(attach_pdf and attached),
                assistant_key=assistant.key,
            )
        else:
            message = ""

        if message:
            _set_clipboard_text(message)
            time.sleep(0.1)
            _hotkey("ctrl", "v")
            time.sleep(0.2)

        if submit and not _must_pause_for_attachment(attachment_paths, attached):
            _press("enter")
        elif submit:
            notes.append(
                f"Envio automatico pausado porque o anexo no {assistant.display_name} "
                "nao foi confirmado."
            )

        _log_automation(f"{assistant.display_name}: envio concluido. alvo={target}")
        return AutomationResult(True, f"Prompt enviado ao {assistant.display_name}.", title, notes)
    except Exception as exc:  # noqa: BLE001 - surfaced to UI
        _log_automation(f"{assistant.display_name}: falha na automacao. alvo={target}. erro={exc!r}")
        return AutomationResult(False, f"Falha na automação: {exc}", title, notes)


def capture_latest_response_from_assistant(assistant_key: str) -> AutomationResult:
    assistant = ASSISTANTS.get(assistant_key)
    if assistant is None:
        return AutomationResult(False, f"Assistente não configurado: {assistant_key}.")

    if not IS_WINDOWS:
        return AutomationResult(False, f"A automação do {assistant.display_name} só está disponível no Windows.")

    target = _resolve_assistant_target(assistant)
    if target is None:
        _log_automation(f"{assistant.display_name}: nenhuma janela ou processo acionavel encontrado para captura.")
        return AutomationResult(False, _missing_target_message(assistant))

    notes: list[str] = []
    if target.note:
        notes.append(target.note)

    previous_clipboard = ""
    clipboard_was_read = False
    sentinel = f"__RESUMATOR_COPY_SENTINEL_{time.time_ns()}__"

    try:
        try:
            previous_clipboard = get_clipboard_text()
            clipboard_was_read = True
        except Exception as exc:  # noqa: BLE001 - clipboard read is best-effort here
            notes.append(f"Nao foi possivel preservar o texto anterior da area de transferencia: {exc}")

        _set_clipboard_text(sentinel)
        _activate_assistant_target(target)
        time.sleep(0.5)

        invoked, detail = _invoke_copy_response_action(assistant, target)
        notes.append(detail)
        if not invoked:
            if clipboard_was_read:
                _set_clipboard_text(previous_clipboard)
            return AutomationResult(
                False,
                f"Nao consegui acionar o botao de copiar resposta no {assistant.display_name}.",
                target.title,
                notes,
            )

        copied_text = _wait_for_clipboard_text_change(sentinel, timeout_seconds=5.0)
        if not copied_text:
            if clipboard_was_read:
                _set_clipboard_text(previous_clipboard)
            return AutomationResult(
                False,
                f"O botao de copiar foi acionado, mas nenhuma resposta em texto foi detectada.",
                target.title,
                notes,
            )

        _log_automation(f"{assistant.display_name}: resposta capturada. alvo={target}")
        return AutomationResult(
            True,
            f"Resposta capturada do {assistant.display_name}.",
            target.title,
            notes,
            copied_text,
        )
    except Exception as exc:  # noqa: BLE001 - surfaced to UI
        if clipboard_was_read:
            try:
                _set_clipboard_text(previous_clipboard)
            except Exception:
                pass
        _log_automation(f"{assistant.display_name}: falha na captura de resposta. alvo={target}. erro={exc!r}")
        return AutomationResult(False, f"Falha na captura automática: {exc}", target.title, notes)


def _invoke_copy_response_action(assistant: DesktopAssistant, target: AssistantTarget) -> tuple[bool, str]:
    hwnd = target.hwnd or _foreground_window_handle()
    if not hwnd:
        return False, "Nao ha janela ativa para procurar o botao de copiar."

    invoked, detail = _invoke_uia_action(hwnd, assistant.response_copy_terms, "botao de copiar resposta")
    _log_automation(f"{assistant.display_name}: tentativa UIA de copiar resposta: {detail}")
    if invoked:
        return True, "Botao de copiar resposta acionado por UI Automation."

    visual_invoked, visual_detail = _invoke_visual_copy_button(hwnd)
    _log_automation(f"{assistant.display_name}: tentativa visual de copiar resposta: {visual_detail}")
    if visual_invoked:
        return True, "Botao de copiar resposta acionado pelo icone."

    return False, f"Nao encontrei o botao de copiar resposta. UIA: {detail}; visual: {visual_detail}"


def _wait_for_clipboard_text_change(sentinel: str, timeout_seconds: float) -> str:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() <= deadline:
        time.sleep(0.15)
        try:
            text = get_clipboard_text()
        except Exception:
            continue
        if text and text != sentinel:
            return text.strip()
    return ""


def _invoke_visual_copy_button(hwnd: int) -> tuple[bool, str]:
    script = r"""
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
Add-Type -Namespace Resumator -Name NativeMouse -MemberDefinition @"
[System.Runtime.InteropServices.DllImport("user32.dll")]
public static extern void mouse_event(int dwFlags, int dx, int dy, int dwData, UIntPtr dwExtraInfo);
"@

function Get-Luminance($color) {
    return (0.299 * $color.R) + (0.587 * $color.G) + (0.114 * $color.B)
}

function Count-Groups($flags) {
    $groups = 0
    $inside = $false
    foreach ($flag in $flags) {
        if ($flag -and -not $inside) {
            $groups += 1
            $inside = $true
        } elseif (-not $flag) {
            $inside = $false
        }
    }
    return $groups
}

function Get-CopyIconScore($bitmap) {
    $width = [int]$bitmap.Width
    $height = [int]$bitmap.Height
    if ($width -lt 12 -or $height -lt 12 -or $width -gt 90 -or $height -gt 90) {
        return 0
    }

    $corners = @(
        (Get-Luminance $bitmap.GetPixel(0, 0)),
        (Get-Luminance $bitmap.GetPixel($width - 1, 0)),
        (Get-Luminance $bitmap.GetPixel(0, $height - 1)),
        (Get-Luminance $bitmap.GetPixel($width - 1, $height - 1))
    )
    $background = ($corners | Measure-Object -Average).Average
    $mask = New-Object 'bool[,]' $width, $height
    $minX = $width
    $minY = $height
    $maxX = -1
    $maxY = -1
    $foregroundCount = 0

    for ($y = 0; $y -lt $height; $y++) {
        for ($x = 0; $x -lt $width; $x++) {
            $lum = Get-Luminance $bitmap.GetPixel($x, $y)
            $diff = [Math]::Abs($lum - $background)
            $isForeground = $false
            if ($background -gt 128) {
                $isForeground = ($lum -lt ($background - 35)) -and ($diff -gt 30)
            } else {
                $isForeground = ($lum -gt ($background + 35)) -and ($diff -gt 30)
            }
            if ($isForeground) {
                $mask[$x, $y] = $true
                $foregroundCount += 1
                if ($x -lt $minX) { $minX = $x }
                if ($y -lt $minY) { $minY = $y }
                if ($x -gt $maxX) { $maxX = $x }
                if ($y -gt $maxY) { $maxY = $y }
            }
        }
    }

    if ($foregroundCount -lt 10 -or $maxX -lt 0) {
        return 0
    }

    $boxWidth = $maxX - $minX + 1
    $boxHeight = $maxY - $minY + 1
    if ($boxWidth -lt 8 -or $boxHeight -lt 8) {
        return 0
    }

    $density = $foregroundCount / [double]($boxWidth * $boxHeight)
    $verticalFlags = @()
    for ($x = $minX; $x -le $maxX; $x++) {
        $count = 0
        for ($y = $minY; $y -le $maxY; $y++) {
            if ($mask[$x, $y]) { $count += 1 }
        }
        $verticalFlags += ($count -ge [Math]::Max(3, [int]($boxHeight * 0.34)))
    }

    $horizontalFlags = @()
    for ($y = $minY; $y -le $maxY; $y++) {
        $count = 0
        for ($x = $minX; $x -le $maxX; $x++) {
            if ($mask[$x, $y]) { $count += 1 }
        }
        $horizontalFlags += ($count -ge [Math]::Max(3, [int]($boxWidth * 0.34)))
    }

    $verticalGroups = Count-Groups $verticalFlags
    $horizontalGroups = Count-Groups $horizontalFlags
    $aspect = $boxWidth / [double]$boxHeight
    $score = 0

    if ($verticalGroups -ge 3 -and $verticalGroups -le 6) { $score += 35 }
    if ($horizontalGroups -ge 3 -and $horizontalGroups -le 6) { $score += 35 }
    if ($density -ge 0.08 -and $density -le 0.55) { $score += 15 }
    if ($aspect -ge 0.45 -and $aspect -le 1.15) { $score += 15 }
    if ($foregroundCount -gt 220) { $score -= 10 }
    if ($verticalGroups -lt 2 -or $horizontalGroups -lt 2) { $score -= 30 }

    return $score
}

try {
    $root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]__HWND__)
} catch {
    Write-Output ("NOT_FOUND|janela nao exposta ao UI Automation: " + $_.Exception.Message)
    exit 2
}
if ($null -eq $root) {
    Write-Output "NOT_FOUND|janela nao exposta ao UI Automation"
    exit 2
}

$buttonCondition = [System.Windows.Automation.PropertyCondition]::new(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::Button
)
$rootRect = $root.Current.BoundingRectangle
$buttons = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $buttonCondition)
$best = $null
$bestScore = 0
$bestName = ""
$bestType = ""
$bestRect = $null

foreach ($button in $buttons) {
    try {
        if (-not $button.Current.IsEnabled) { continue }
        if ($button.Current.IsOffscreen) { continue }
        $rect = $button.Current.BoundingRectangle
        if ($rect.IsEmpty) { continue }
        $width = [int][Math]::Round($rect.Width)
        $height = [int][Math]::Round($rect.Height)
        if ($width -lt 12 -or $height -lt 12 -or $width -gt 90 -or $height -gt 90) { continue }

        $bitmap = New-Object System.Drawing.Bitmap($width, $height)
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
        try {
            $graphics.CopyFromScreen(
                [int][Math]::Round($rect.Left),
                [int][Math]::Round($rect.Top),
                0,
                0,
                ([System.Drawing.Size]::new($width, $height))
            )
            $score = Get-CopyIconScore $bitmap
            $name = [string]$button.Current.Name
            $automationId = [string]$button.Current.AutomationId
            $helpText = [string]$button.Current.HelpText
            $haystack = ("$name $automationId $helpText").ToLowerInvariant()
            if ($haystack.Contains("copy") -or $haystack.Contains("copiar")) {
                $score += 80
            } elseif (-not [string]::IsNullOrWhiteSpace($name)) {
                $score -= 45
            }
            if (
                $haystack.Contains("inicializador") -or
                $haystack.Contains("launcher") -or
                $haystack.Contains("configura") -or
                $haystack.Contains("settings") -or
                $haystack.Contains("more") -or
                $haystack.Contains("mais") -or
                $haystack.Contains("novo chat") -or
                $haystack.Contains("new chat") -or
                $haystack.Contains("modelo") -or
                $haystack.Contains("model") -or
                $haystack.Contains("fonte") -or
                $haystack.Contains("source") -or
                $haystack.Contains("adicionar") -or
                $haystack.Contains("add") -or
                $haystack.Contains("anex") -or
                $haystack.Contains("attach") -or
                $haystack.Contains("upload") -or
                $haystack.Contains("ditado") -or
                $haystack.Contains("dictation") -or
                $haystack.Contains("rolar") -or
                $haystack.Contains("scroll") -or
                $haystack.Contains("minimize") -or
                $haystack.Contains("maximize") -or
                $haystack.Contains("fechar") -or
                $haystack.Contains("close")
            ) {
                $score -= 120
            }
            if (-not $rootRect.IsEmpty -and $rootRect.Height -gt 0 -and $rootRect.Width -gt 0) {
                $relativeX = (($rect.Left + ($rect.Width / 2.0)) - $rootRect.Left) / [double]$rootRect.Width
                $relativeY = (($rect.Top + ($rect.Height / 2.0)) - $rootRect.Top) / [double]$rootRect.Height
                if ($relativeY -lt 0.22) { $score -= 100 }
                if ($relativeX -lt 0.12) { $score -= 40 }
                if ($relativeY -gt 0.28 -and $relativeY -lt 0.92) { $score += 12 }
            }
            if ($score -gt $bestScore) {
                $bestScore = $score
                $best = $button
                $bestName = $name
                $bestType = [string]$button.Current.ControlType.ProgrammaticName
                $bestRect = $rect
            }
        } finally {
            $graphics.Dispose()
            $bitmap.Dispose()
        }
    } catch {
        continue
    }
}

if ($null -eq $best -or $bestScore -lt 55) {
    Write-Output ("NOT_FOUND|icone de copiar nao localizado; score=" + $bestScore)
    exit 2
}

try {
    try {
        $point = $best.GetClickablePoint()
        $clickX = [int]$point.X
        $clickY = [int]$point.Y
    } catch {
        if ($null -eq $bestRect -or $bestRect.IsEmpty) {
            throw
        }
        $clickX = [int][Math]::Round($bestRect.Left + ($bestRect.Width / 2.0))
        $clickY = [int][Math]::Round($bestRect.Top + ($bestRect.Height / 2.0))
    }
    [System.Windows.Forms.Cursor]::Position = [System.Drawing.Point]::new($clickX, $clickY)
    [Resumator.NativeMouse]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 80
    [Resumator.NativeMouse]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
    Write-Output ("CLICKED|score=" + $bestScore + "|name=" + $bestName + "|type=" + $bestType)
    exit 0
} catch {
    Write-Output ("FAILED|" + $_.Exception.Message)
    exit 3
}
""".replace("__HWND__", str(int(hwnd)))

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            check=False,
            capture_output=True,
            text=True,
            creationflags=creationflags,
            timeout=10,
        )
    except Exception as exc:  # noqa: BLE001 - best-effort visual UI automation
        return False, f"erro ao procurar icone de copiar: {exc}"

    output = (completed.stdout or completed.stderr or "").strip()
    return completed.returncode == 0, output or f"retorno={completed.returncode}"


def _invoke_visual_attachment_button(hwnd: int) -> tuple[bool, str]:
    script = r"""
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
Add-Type -Namespace Resumator -Name NativeMouse -MemberDefinition @"
[System.Runtime.InteropServices.DllImport("user32.dll")]
public static extern void mouse_event(int dwFlags, int dx, int dy, int dwData, UIntPtr dwExtraInfo);
"@

function Get-Luminance($color) {
    return (0.299 * $color.R) + (0.587 * $color.G) + (0.114 * $color.B)
}

function Count-Groups($flags) {
    $groups = 0
    $inside = $false
    foreach ($flag in $flags) {
        if ($flag -and -not $inside) {
            $groups += 1
            $inside = $true
        } elseif (-not $flag) {
            $inside = $false
        }
    }
    return $groups
}

function Get-PlusIconScore($bitmap) {
    $width = [int]$bitmap.Width
    $height = [int]$bitmap.Height
    if ($width -lt 10 -or $height -lt 10 -or $width -gt 96 -or $height -gt 96) {
        return 0
    }

    $corners = @(
        (Get-Luminance $bitmap.GetPixel(0, 0)),
        (Get-Luminance $bitmap.GetPixel($width - 1, 0)),
        (Get-Luminance $bitmap.GetPixel(0, $height - 1)),
        (Get-Luminance $bitmap.GetPixel($width - 1, $height - 1))
    )
    $background = ($corners | Measure-Object -Average).Average
    $mask = New-Object 'bool[,]' $width, $height
    $minX = $width
    $minY = $height
    $maxX = -1
    $maxY = -1
    $foregroundCount = 0

    for ($y = 0; $y -lt $height; $y++) {
        for ($x = 0; $x -lt $width; $x++) {
            $lum = Get-Luminance $bitmap.GetPixel($x, $y)
            $diff = [Math]::Abs($lum - $background)
            $isForeground = $false
            if ($background -gt 128) {
                $isForeground = ($lum -lt ($background - 34)) -and ($diff -gt 26)
            } else {
                $isForeground = ($lum -gt ($background + 34)) -and ($diff -gt 26)
            }
            if ($isForeground) {
                $mask[$x, $y] = $true
                $foregroundCount += 1
                if ($x -lt $minX) { $minX = $x }
                if ($y -lt $minY) { $minY = $y }
                if ($x -gt $maxX) { $maxX = $x }
                if ($y -gt $maxY) { $maxY = $y }
            }
        }
    }

    if ($foregroundCount -lt 8 -or $maxX -lt 0) {
        return 0
    }

    $boxWidth = $maxX - $minX + 1
    $boxHeight = $maxY - $minY + 1
    if ($boxWidth -lt 7 -or $boxHeight -lt 7) {
        return 0
    }

    $density = $foregroundCount / [double]($boxWidth * $boxHeight)
    $cx1 = [Math]::Max($minX, [int]($minX + ($boxWidth * 0.42)))
    $cx2 = [Math]::Min($maxX, [int]($minX + ($boxWidth * 0.58)))
    $cy1 = [Math]::Max($minY, [int]($minY + ($boxHeight * 0.42)))
    $cy2 = [Math]::Min($maxY, [int]($minY + ($boxHeight * 0.58)))

    $verticalRowsHit = 0
    for ($y = $minY; $y -le $maxY; $y++) {
        $hit = $false
        for ($x = $cx1; $x -le $cx2; $x++) {
            if ($mask[$x, $y]) {
                $hit = $true
                break
            }
        }
        if ($hit) { $verticalRowsHit += 1 }
    }

    $horizontalColsHit = 0
    for ($x = $minX; $x -le $maxX; $x++) {
        $hit = $false
        for ($y = $cy1; $y -le $cy2; $y++) {
            if ($mask[$x, $y]) {
                $hit = $true
                break
            }
        }
        if ($hit) { $horizontalColsHit += 1 }
    }

    $verticalSpan = $verticalRowsHit / [double]$boxHeight
    $horizontalSpan = $horizontalColsHit / [double]$boxWidth

    $verticalFlags = @()
    for ($x = $minX; $x -le $maxX; $x++) {
        $count = 0
        for ($y = $minY; $y -le $maxY; $y++) {
            if ($mask[$x, $y]) { $count += 1 }
        }
        $verticalFlags += ($count -ge [Math]::Max(3, [int]($boxHeight * 0.35)))
    }

    $horizontalFlags = @()
    for ($y = $minY; $y -le $maxY; $y++) {
        $count = 0
        for ($x = $minX; $x -le $maxX; $x++) {
            if ($mask[$x, $y]) { $count += 1 }
        }
        $horizontalFlags += ($count -ge [Math]::Max(3, [int]($boxWidth * 0.35)))
    }

    $verticalGroups = Count-Groups $verticalFlags
    $horizontalGroups = Count-Groups $horizontalFlags
    $aspect = $boxWidth / [double]$boxHeight
    $score = 0

    if ($verticalSpan -ge 0.45) { $score += 30 }
    if ($horizontalSpan -ge 0.45) { $score += 30 }
    if ($verticalGroups -ge 1 -and $verticalGroups -le 3) { $score += 15 }
    if ($horizontalGroups -ge 1 -and $horizontalGroups -le 3) { $score += 15 }
    if ($density -ge 0.05 -and $density -le 0.50) { $score += 10 }
    if ($aspect -ge 0.62 -and $aspect -le 1.45) { $score += 10 }
    if ($verticalSpan -lt 0.35 -or $horizontalSpan -lt 0.35) { $score -= 35 }
    if ($foregroundCount -gt 260 -and $density -gt 0.45) { $score -= 10 }

    return $score
}

try {
    $root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]__HWND__)
} catch {
    Write-Output ("NOT_FOUND|janela nao exposta ao UI Automation: " + $_.Exception.Message)
    exit 2
}
if ($null -eq $root) {
    Write-Output "NOT_FOUND|janela nao exposta ao UI Automation"
    exit 2
}

$rootRect = $root.Current.BoundingRectangle
$elements = $root.FindAll(
    [System.Windows.Automation.TreeScope]::Descendants,
    [System.Windows.Automation.Condition]::TrueCondition
)
$best = $null
$bestScore = 0
$bestName = ""
$bestType = ""
$bestRect = $null

foreach ($element in $elements) {
    try {
        if (-not $element.Current.IsEnabled) { continue }
        if ($element.Current.IsOffscreen) { continue }

        $controlType = [string]$element.Current.ControlType.ProgrammaticName
        if (
            -not $controlType.Contains("Button") -and
            -not $controlType.Contains("MenuItem") -and
            -not $controlType.Contains("Hyperlink")
        ) {
            continue
        }

        $rect = $element.Current.BoundingRectangle
        if ($rect.IsEmpty) { continue }
        $width = [int][Math]::Round($rect.Width)
        $height = [int][Math]::Round($rect.Height)
        if ($width -lt 10 -or $height -lt 10 -or $width -gt 120 -or $height -gt 120) { continue }

        $bitmap = New-Object System.Drawing.Bitmap($width, $height)
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
        try {
            $graphics.CopyFromScreen(
                [int][Math]::Round($rect.Left),
                [int][Math]::Round($rect.Top),
                0,
                0,
                ([System.Drawing.Size]::new($width, $height))
            )

            $score = Get-PlusIconScore $bitmap
            $name = [string]$element.Current.Name
            $automationId = [string]$element.Current.AutomationId
            $helpText = [string]$element.Current.HelpText
            $haystack = ("$name $automationId $helpText $controlType").ToLowerInvariant()

            if (
                $haystack.Contains("anex") -or
                $haystack.Contains("attach") -or
                $haystack.Contains("upload") -or
                $haystack.Contains("arquivo") -or
                $haystack.Contains("file") -or
                $haystack.Contains("add content") -or
                $haystack.Contains("adicionar conte") -or
                $haystack.Contains("gerenciar fontes") -or
                $haystack.Contains("fontes") -or
                $haystack.Contains("sources")
            ) {
                $score += 65
            }
            if (
                $haystack.Contains("adicionar e gerenciar fontes") -or
                $haystack.Contains("add sources") -or
                $haystack.Contains("manage sources")
            ) {
                $score += 70
            }
            if ($haystack.Contains("plus") -or $haystack.Contains("adicionar")) {
                $score += 25
            }
            if (
                $haystack.Contains("copy") -or
                $haystack.Contains("copiar") -or
                $haystack.Contains("more") -or
                $haystack.Contains("mais") -or
                $haystack.Contains("new chat") -or
                $haystack.Contains("novo chat") -or
                $haystack.Contains("configura") -or
                $haystack.Contains("refresh") -or
                $haystack.Contains("atualizar")
            ) {
                $score -= 90
            }

            if (-not $rootRect.IsEmpty -and $rootRect.Height -gt 0) {
                $relativeY = (($rect.Top + ($rect.Height / 2.0)) - $rootRect.Top) / [double]$rootRect.Height
                if ($relativeY -gt 0.55) {
                    $score += 35
                } elseif ($relativeY -gt 0.35) {
                    $score += 10
                } else {
                    $score -= 35
                }
            }

            if ($score -gt $bestScore) {
                $bestScore = $score
                $best = $element
                $bestName = $name
                $bestType = $controlType
                $bestRect = $rect
            }
        } finally {
            $graphics.Dispose()
            $bitmap.Dispose()
        }
    } catch {
        continue
    }
}

if ($null -eq $best -or $bestScore -lt 55) {
    Write-Output ("NOT_FOUND|icone de anexo nao localizado; score=" + $bestScore)
    exit 2
}

try {
    try {
        $point = $best.GetClickablePoint()
        $clickX = [int]$point.X
        $clickY = [int]$point.Y
    } catch {
        $clickX = [int][Math]::Round($bestRect.Left + ($bestRect.Width / 2.0))
        $clickY = [int][Math]::Round($bestRect.Top + ($bestRect.Height / 2.0))
    }
    [System.Windows.Forms.Cursor]::Position = [System.Drawing.Point]::new($clickX, $clickY)
    [Resumator.NativeMouse]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 80
    [Resumator.NativeMouse]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
    Write-Output ("CLICKED|score=" + $bestScore + "|name=" + $bestName + "|type=" + $bestType)
    exit 0
} catch {
    Write-Output ("FAILED|" + $_.Exception.Message)
    exit 3
}
""".replace("__HWND__", str(int(hwnd)))

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            check=False,
            capture_output=True,
            text=True,
            creationflags=creationflags,
            timeout=10,
        )
    except Exception as exc:  # noqa: BLE001 - best-effort visual UI automation
        return False, f"erro ao procurar icone de anexo: {exc}"

    output = (completed.stdout or completed.stderr or "").strip()
    return completed.returncode == 0, output or f"retorno={completed.returncode}"


def get_clipboard_text() -> str:
    if win32clipboard is None or win32con is None:
        return _get_clipboard_text_ctypes()
    win32clipboard.OpenClipboard()
    try:
        try:
            return win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
        except TypeError:
            return ""
    finally:
        win32clipboard.CloseClipboard()


def _normalize_paths(file_path: Path | Iterable[Path] | None) -> list[Path]:
    if file_path is None:
        return []
    if isinstance(file_path, Path):
        return [file_path]
    return [Path(path) for path in file_path]


def _normalize_pdf_paths(pdf_path: Path | Iterable[Path] | None) -> list[Path]:
    return _normalize_paths(pdf_path)


def _single_file_label(path: Path) -> str:
    suffix = path.suffix.casefold()
    if suffix == ".pdf":
        return "PDF"
    if suffix == ".docx":
        return "DOCX"
    return "arquivo"


def _attachment_note(file_paths: list[Path]) -> str:
    if len(file_paths) == 1:
        return f"{_single_file_label(file_paths[0])} colado como anexo pela área de transferência."
    return f"{len(file_paths)} arquivos colados como anexos pela área de transferência."


def _dialog_attachment_note(file_paths: list[Path], assistant: DesktopAssistant) -> str:
    if len(file_paths) == 1:
        return f"{_single_file_label(file_paths[0])} anexado no {assistant.display_name} pelo seletor de arquivos."
    return f"{len(file_paths)} arquivos anexados no {assistant.display_name} pelo seletor de arquivos."


def _manual_attachment_note(file_paths: list[Path], assistant: DesktopAssistant) -> str:
    if len(file_paths) == 1:
        return f"No {assistant.display_name}, anexe o arquivo pelo botao de arquivo do chat."
    return f"No {assistant.display_name}, anexe os {len(file_paths)} arquivos pelo botao de arquivo do chat."


def _must_pause_for_attachment(file_paths: list[Path], attached: bool) -> bool:
    return bool(file_paths and not attached)


def _attach_files_to_assistant(
    assistant: DesktopAssistant,
    target: AssistantTarget,
    file_paths: list[Path],
) -> AttachmentResult:
    if assistant.supports_clipboard_file_paste:
        attached = _copy_files_to_clipboard(file_paths)
        if attached:
            _hotkey("ctrl", "v")
            time.sleep(assistant.attachment_wait_seconds)
            return AttachmentResult(True, [_attachment_note(file_paths)])
        return AttachmentResult(False, ["Não foi possível colocar os arquivos na área de transferência como anexo."])

    if assistant.supports_file_dialog_attachment:
        if _open_attachment_dialog(assistant, target):
            if _select_files_in_open_dialog(file_paths, assistant.attachment_wait_seconds):
                return AttachmentResult(True, [_dialog_attachment_note(file_paths, assistant)])
            return AttachmentResult(
                False,
                [
                    "O botao de anexo foi acionado, mas o seletor de arquivos nao confirmou os arquivos.",
                    _manual_attachment_note(file_paths, assistant),
                ],
            )

        clipboard_attempted = _copy_files_to_clipboard(file_paths)
        if clipboard_attempted:
            _hotkey("ctrl", "v")
            time.sleep(assistant.attachment_wait_seconds)
            if assistant.trust_clipboard_attachment_fallback:
                return AttachmentResult(
                    True,
                    [
                        "Nao consegui confirmar o seletor de arquivos; colei os arquivos pela area de transferencia.",
                        "O envio automatico prosseguiu com o anexo por fallback.",
                    ],
                )
            return AttachmentResult(
                False,
                [
                    "Nao consegui acionar o botao de anexo; tentei colar os arquivos pela area de transferencia.",
                    "Confira se o anexo apareceu antes de enviar.",
                ],
            )

    return AttachmentResult(False, [_manual_attachment_note(file_paths, assistant)])


def _open_attachment_dialog(assistant: DesktopAssistant, target: AssistantTarget) -> bool:
    hwnd = target.hwnd or _foreground_window_handle()
    if hwnd:
        invoked, detail = _invoke_uia_action(hwnd, assistant.attachment_button_terms, "controle de anexo")
        _log_automation(f"{assistant.display_name}: tentativa de acionar botao de anexo: {detail}")
        if invoked and _wait_for_file_dialog(timeout_seconds=3.0):
            return True

        foreground = _foreground_window_handle() or hwnd
        invoked_menu, detail_menu = _invoke_uia_action(foreground, assistant.attachment_menu_terms, "menu de arquivo")
        _log_automation(f"{assistant.display_name}: tentativa de acionar menu de arquivo: {detail_menu}")
        if invoked_menu and _wait_for_file_dialog(timeout_seconds=3.0):
            return True

        visual_invoked, visual_detail = _invoke_visual_attachment_button(hwnd)
        _log_automation(f"{assistant.display_name}: tentativa visual de acionar botao de anexo: {visual_detail}")
        if visual_invoked:
            if _wait_for_file_dialog(timeout_seconds=3.0):
                return True

            time.sleep(0.3)
            foreground = _foreground_window_handle() or hwnd
            invoked_visual_menu, detail_visual_menu = _invoke_uia_action(
                foreground,
                assistant.attachment_menu_terms,
                "menu de arquivo",
            )
            _log_automation(
                f"{assistant.display_name}: tentativa de acionar menu de arquivo apos icone: {detail_visual_menu}"
            )
            if invoked_visual_menu and _wait_for_file_dialog(timeout_seconds=3.0):
                return True

    return bool(_wait_for_file_dialog(timeout_seconds=0.5))


def _invoke_uia_action(hwnd: int, terms: tuple[str, ...], action_label: str = "controle") -> tuple[bool, str]:
    if not hwnd or not terms:
        return False, "janela ou termos de busca ausentes"

    terms_json = json.dumps(list(terms), ensure_ascii=False)
    action_label_json = json.dumps(action_label, ensure_ascii=False)
    script = f"""
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
Add-Type -Namespace Resumator -Name NativeMouse -MemberDefinition @"
[System.Runtime.InteropServices.DllImport("user32.dll")]
public static extern void mouse_event(int dwFlags, int dx, int dy, int dwData, UIntPtr dwExtraInfo);
"@
$terms = ConvertFrom-Json @'
{terms_json}
'@
$actionLabel = {action_label_json}
$root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]{int(hwnd)})
if ($null -eq $root) {{
    Write-Output "NOT_FOUND|janela nao exposta ao UI Automation"
    exit 2
}}
$elements = $root.FindAll(
    [System.Windows.Automation.TreeScope]::Descendants,
    [System.Windows.Automation.Condition]::TrueCondition
)
$best = $null
$bestScore = 0
foreach ($element in $elements) {{
    try {{
        if (-not $element.Current.IsEnabled) {{ continue }}
        if ($element.Current.IsOffscreen) {{ continue }}
        $name = [string]$element.Current.Name
        $automationId = [string]$element.Current.AutomationId
        $helpText = [string]$element.Current.HelpText
        $controlType = [string]$element.Current.ControlType.ProgrammaticName
        if (
            -not $controlType.Contains("Button") -and
            -not $controlType.Contains("MenuItem") -and
            -not $controlType.Contains("Hyperlink") -and
            -not $controlType.Contains("ListItem")
        ) {{
            continue
        }}
        $haystack = ("$name $automationId $helpText $controlType").ToLowerInvariant()
        $score = 0
        foreach ($term in $terms) {{
            $needle = ([string]$term).ToLowerInvariant()
            if ([string]::IsNullOrWhiteSpace($needle)) {{ continue }}
            if ($haystack.Contains($needle)) {{ $score += 10 + $needle.Length }}
            if ($name.ToLowerInvariant() -eq $needle) {{ $score += 50 }}
        }}
        if ($score -gt $bestScore) {{
            $best = $element
            $bestScore = $score
        }}
    }} catch {{
        continue
    }}
}}
if ($null -eq $best) {{
    Write-Output ("NOT_FOUND|nenhum " + $actionLabel + " localizado")
    exit 2
}}
$bestName = [string]$best.Current.Name
$bestRect = $best.Current.BoundingRectangle
try {{
    $pattern = $best.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
    $pattern.Invoke()
    Write-Output ("INVOKED|" + $bestName)
    exit 0
}} catch {{
    try {{
        try {{
            $point = $best.GetClickablePoint()
            $clickX = [int]$point.X
            $clickY = [int]$point.Y
        }} catch {{
            if ($bestRect.IsEmpty) {{
                throw
            }}
            $clickX = [int][Math]::Round($bestRect.Left + ($bestRect.Width / 2.0))
            $clickY = [int][Math]::Round($bestRect.Top + ($bestRect.Height / 2.0))
        }}
        [System.Windows.Forms.Cursor]::Position = [System.Drawing.Point]::new($clickX, $clickY)
        [Resumator.NativeMouse]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)
        Start-Sleep -Milliseconds 80
        [Resumator.NativeMouse]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
        Write-Output ("CLICKED|" + $bestName)
        exit 0
    }} catch {{
        Write-Output ("FAILED|" + $_.Exception.Message)
        exit 3
    }}
}}
"""
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            check=False,
            capture_output=True,
            text=True,
            creationflags=creationflags,
            timeout=7,
        )
    except Exception as exc:  # noqa: BLE001 - best-effort UI automation
        return False, f"erro ao executar UI Automation: {exc}"

    output = (completed.stdout or completed.stderr or "").strip()
    return completed.returncode == 0, output or f"retorno={completed.returncode}"


def _select_files_in_open_dialog(file_paths: list[Path], wait_seconds: float) -> bool:
    dialog_hwnd = _wait_for_file_dialog(timeout_seconds=6.0)
    if not dialog_hwnd:
        return False

    _activate_window(dialog_hwnd)
    time.sleep(0.2)
    _set_clipboard_text(_file_dialog_selection_text(file_paths))
    time.sleep(0.1)
    _hotkey("ctrl", "v")
    time.sleep(0.2)
    _press("enter")
    time.sleep(wait_seconds)
    return True


def _wait_for_file_dialog(timeout_seconds: float) -> int | None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() <= deadline:
        hwnd = _foreground_window_handle()
        if hwnd:
            title = _window_text(hwnd).casefold()
            class_name = _window_class_name(hwnd)
            if class_name == "#32770" or any(term in title for term in ("abrir", "open", "selecionar", "choose")):
                return hwnd
        time.sleep(0.15)
    return None


def _foreground_window_handle() -> int | None:
    if not IS_WINDOWS:
        return None
    try:
        user32 = ctypes.windll.user32
        user32.GetForegroundWindow.restype = wintypes.HWND
        hwnd = int(user32.GetForegroundWindow())
        return hwnd or None
    except Exception:
        return None


def _window_text(hwnd: int) -> str:
    if win32gui is not None:
        try:
            return win32gui.GetWindowText(hwnd).strip()
        except Exception:
            return ""

    user32 = ctypes.windll.user32
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value.strip()


def _window_class_name(hwnd: int) -> str:
    if win32gui is not None:
        try:
            return win32gui.GetClassName(hwnd)
        except Exception:
            return ""

    user32 = ctypes.windll.user32
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClassNameW.restype = ctypes.c_int
    buffer = ctypes.create_unicode_buffer(256)
    if user32.GetClassNameW(hwnd, buffer, len(buffer)):
        return buffer.value
    return ""


def _file_dialog_selection_text(file_paths: list[Path]) -> str:
    return " ".join(f'"{path.resolve()}"' for path in file_paths if path.exists())


def _build_message(
    prompt_text: str,
    pdf_paths: list[Path],
    attached: bool,
    assistant_key: str | None = None,
) -> str:
    lines = [prompt_text.strip()]
    if pdf_paths:
        names = ", ".join(path.name for path in pdf_paths)
        if attached:
            lines.append("")
            label = "Arquivo anexado" if len(pdf_paths) == 1 else "Arquivos anexados"
            lines.append(f"{label}: {names}")
        elif _assistant_uses_manual_attachment(assistant_key):
            selected = "\n".join(f"- {path}" for path in pdf_paths)
            assistant_name = assistant_display_name(assistant_key or "")
            file_label = "PDF" if len(pdf_paths) == 1 else "PDFs"
            lines.append("")
            lines.append(
                f"Observacao: no {assistant_name}, anexe o {file_label} pelo botao de arquivo do chat "
                "antes de enviar esta mensagem."
            )
            selection_label = "Arquivo selecionado" if len(pdf_paths) == 1 else "Arquivos selecionados"
            lines.append(f"{selection_label}:\n{selected}")
        else:
            selected = "\n".join(f"- {path}" for path in pdf_paths)
            lines.append("")
            if len(pdf_paths) == 1:
                lines.append(
                    "Observação: tentei anexar o PDF automaticamente. Se o anexo não aparecer "
                    f"na conversa, use o arquivo selecionado no Resumator:\n{selected}"
                )
            else:
                lines.append(
                    "Observação: tentei anexar os PDFs automaticamente. Se os anexos não aparecerem "
                    f"na conversa, use os arquivos selecionados no Resumator:\n{selected}"
                )
    return "\n".join(line for line in lines if line is not None).strip()


def _assistant_uses_manual_attachment(assistant_key: str | None) -> bool:
    if not assistant_key:
        return False
    assistant = ASSISTANTS.get(assistant_key)
    return bool(assistant and not assistant.supports_clipboard_file_paste)


def _activate_assistant_target(target: AssistantTarget) -> None:
    if target.hwnd is not None:
        _activate_window(target.hwnd)
        return

    pids: list[int] = []
    if target.pid is not None:
        pids.append(target.pid)
    pids.extend(pid for pid in target.candidate_pids if pid not in pids)
    for pid in pids:
        if _activate_process(pid):
            return

    raise AutomationError("Não foi possível trazer a janela do aplicativo para frente.")


def _activate_window(hwnd: int) -> None:
    if win32gui is None or win32con is None:
        user32 = ctypes.windll.user32
        user32.ShowWindow(wintypes.HWND(hwnd), 9)
        user32.SetForegroundWindow(wintypes.HWND(hwnd))
        return
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        ctypes.windll.user32.SetForegroundWindow(hwnd)


def _activate_process(pid: int) -> bool:
    if not IS_WINDOWS:
        return False

    command = (
        "$shell = New-Object -ComObject WScript.Shell; "
        f"if ($shell.AppActivate({int(pid)})) {{ exit 0 }} else {{ exit 1 }}"
    )
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-Command", command],
            check=False,
            creationflags=creationflags,
            timeout=5,
        )
        return completed.returncode == 0
    except Exception as exc:  # noqa: BLE001 - best-effort fallback
        _log_automation(f"Falha ao ativar processo {pid}: {exc!r}")
        return False


def _log_automation(message: str) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with LOG_PATH.open("a", encoding="utf-8") as log_file:
            log_file.write(f"[{timestamp}] {message}\n")
    except Exception:
        pass


def _set_clipboard_text(text: str) -> None:
    if win32clipboard is None or win32con is None:
        _set_clipboard_text_ctypes(text)
        return
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
    finally:
        win32clipboard.CloseClipboard()


def _set_clipboard_text_ctypes(text: str) -> None:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002
    GMEM_ZEROINIT = 0x0040

    _configure_global_memory(kernel32)
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE

    payload = (text + "\0").encode("utf-16le")
    if not user32.OpenClipboard(None):
        raise AutomationError("Não foi possível abrir a área de transferência.")

    handle = None
    try:
        user32.EmptyClipboard()
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE | GMEM_ZEROINIT, len(payload))
        if not handle:
            raise AutomationError("Não foi possível reservar memória para a área de transferência.")
        locked = kernel32.GlobalLock(handle)
        if not locked:
            kernel32.GlobalFree(handle)
            raise AutomationError("Não foi possível preparar a área de transferência.")
        ctypes.memmove(locked, payload, len(payload))
        kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            kernel32.GlobalFree(handle)
            raise AutomationError("Não foi possível copiar texto para a área de transferência.")
        handle = None
    finally:
        user32.CloseClipboard()
        if handle:
            kernel32.GlobalFree(handle)


def _get_clipboard_text_ctypes() -> str:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    CF_UNICODETEXT = 13

    _configure_global_memory(kernel32)
    user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
    user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE

    if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
        return ""
    if not user32.OpenClipboard(None):
        raise AutomationError("Não foi possível abrir a área de transferência.")
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return ""
        locked = kernel32.GlobalLock(handle)
        if not locked:
            return ""
        try:
            return ctypes.wstring_at(locked)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def _copy_files_to_clipboard(paths: list[Path]) -> bool:
    if not IS_WINDOWS:
        return False

    normalized = [str(path.resolve()) for path in paths if path.exists()]
    if not normalized:
        return False

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    GMEM_MOVEABLE = 0x0002
    GMEM_ZEROINIT = 0x0040
    CF_HDROP = 15

    _configure_global_memory(kernel32)
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE

    file_list = ("\0".join(normalized) + "\0\0").encode("utf-16le")
    dropfiles = struct.pack("<IiiII", 20, 0, 0, 0, 1)
    payload = dropfiles + file_list

    if not user32.OpenClipboard(None):
        return False

    handle = None
    try:
        user32.EmptyClipboard()
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE | GMEM_ZEROINIT, len(payload))
        if not handle:
            return False
        locked = kernel32.GlobalLock(handle)
        if not locked:
            kernel32.GlobalFree(handle)
            return False
        ctypes.memmove(locked, payload, len(payload))
        kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(CF_HDROP, handle):
            kernel32.GlobalFree(handle)
            return False
        handle = None
        return True
    finally:
        user32.CloseClipboard()
        if handle:
            kernel32.GlobalFree(handle)


def _configure_global_memory(kernel32) -> None:
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.restype = wintypes.HGLOBAL


VK = {
    "ctrl": 0x11,
    "shift": 0x10,
    "alt": 0x12,
    "v": 0x56,
    "c": 0x43,
    "a": 0x41,
    "enter": 0x0D,
}


def _hotkey(*keys: str) -> None:
    for key in keys:
        _key_down(VK[key])
        time.sleep(0.03)
    for key in reversed(keys):
        _key_up(VK[key])
        time.sleep(0.03)


def _press(key: str) -> None:
    _key_down(VK[key])
    time.sleep(0.04)
    _key_up(VK[key])


def _key_down(vk: int) -> None:
    ctypes.windll.user32.keybd_event(vk, 0, 0, 0)


def _key_up(vk: int) -> None:
    KEYEVENTF_KEYUP = 0x0002
    ctypes.windll.user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
