from __future__ import annotations

import ctypes
from ctypes import wintypes
from datetime import datetime
import json
from pathlib import Path
import os
import re
import subprocess
import sys
import tempfile
import threading

from .chatgpt_desktop import (
    assistant_display_name,
    capture_latest_response_from_assistant,
    get_clipboard_text,
    open_desktop_assistant,
    send_to_desktop_assistant,
)
from .logging_utils import collect_logs, write_exception, write_log
from .pdf_export import export_prompt_docx, export_response_docx, export_response_json, export_response_pdf
from .prompt_store import DEFAULT_SELECTED_PROMPT_ID, Prompt, PromptStore
from .solicitador_bridge import SolicitadorExportResult, export_summary_to_solicitador


APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
DATA_DIR = APP_DIR / "data"
PROMPTS_PATH = DATA_DIR / "prompts.json"
OUTPUT_DIR = APP_DIR / "saidas"
APP_TITLE = "Resumator 10.1"
DEVELOPER = "LEONARDO CARDOSO DE MELO TEIXEIRA MENDES - PROCURADOR FEDERAL / AGU"
MAX_PDF_FILES = 10
DELIVERY_TEXT = "text"
DELIVERY_DOCX = "docx"
ASSISTANT_SELECTION_MOUSE_SUSPEND_SECONDS = 10
LMSTUDIO_SELECTION_MOUSE_SUSPEND_SECONDS = 30
SEND_MOUSE_SUSPEND_SECONDS = 15
WH_MOUSE_LL = 14
HC_ACTION = 0
LLMHF_INJECTED = 0x00000001
LLMHF_LOWER_IL_INJECTED = 0x00000002
CALLBACK_FACTORY = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)
LOW_LEVEL_MOUSE_PROC = CALLBACK_FACTORY(wintypes.LPARAM, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
_TCL_DLL = None


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", wintypes.POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", wintypes.WPARAM),
    ]


def _initialize_tcl_runtime() -> None:
    global _TCL_DLL

    if os.name != "nt":
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

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from tkinter.scrolledtext import ScrolledText


def _resource_path(*parts: str) -> Path:
    relative = Path(*parts)
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", APP_DIR))
        candidates.extend([meipass / relative, APP_DIR / "_internal" / relative])
    candidates.extend([APP_DIR / relative, Path(__file__).resolve().parents[1] / relative])

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0] if candidates else relative


def _mouse_suspend_ms(seconds: int) -> int:
    return int(seconds * 1000)


def _mouse_suspend_status(seconds: int) -> str:
    return f"mouse suspenso por {seconds} segundos"


class ResumatorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1060x860")
        self.root.minsize(980, 760)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.logo_image: tk.PhotoImage | None = None
        self.banner_image: tk.PhotoImage | None = None
        self._set_window_icon()

        self.store = PromptStore(PROMPTS_PATH)
        self.prompts: list[Prompt] = []
        self.selected_prompt_id: str | None = None
        self.transient_prompt_name: str | None = None
        self.transient_prompt_content: str | None = None
        self.pdf_paths: list[Path] = []
        self.last_output_path: Path | None = None

        self.prompt_var = tk.StringVar()
        self.pdf_var = tk.StringVar()
        self.process_number_var = tk.StringVar()
        self.assistant_var = tk.StringVar(value="none")
        self.delivery_mode_var = tk.StringVar(value=DELIVERY_TEXT)
        self.status_var = tk.StringVar(value="Pronto.")
        self.attach_var = tk.BooleanVar(value=True)
        self.submit_var = tk.BooleanVar(value=True)
        self._mouse_suspend_active = False
        self._status_after_mouse_suspend: str | None = None
        self._mouse_suspend_generation = 0
        self._mouse_block_hook: int | None = None
        self._mouse_block_callback = None
        self._mouse_clip_active = False

        self._configure_style()
        self._build_ui()
        self._reload_prompts()

    def _configure_style(self) -> None:
        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"))
        style.configure("Developer.TLabel", font=("Segoe UI", 9))
        style.configure("Section.TLabel", font=("Segoe UI", 10, "bold"))
        style.configure("Status.TLabel", foreground="#335")
        style.configure("StatusAlert.TLabel", foreground="#b00020")

    def _set_window_icon(self) -> None:
        icon_path = _resource_path("assets", "robot.ico")
        if not icon_path.exists():
            return
        try:
            self.root.iconbitmap(str(icon_path))
        except tk.TclError:
            pass

    def _load_image(self, filename: str) -> tk.PhotoImage | None:
        image_path = _resource_path("assets", filename)
        if not image_path.exists():
            return None
        try:
            return tk.PhotoImage(file=str(image_path))
        except tk.TclError:
            return None

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        header = ttk.Frame(self.root, padding=(18, 14, 18, 8))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)

        self.logo_image = self._load_image("robot-logo.png")
        if self.logo_image is not None:
            ttk.Label(header, image=self.logo_image).grid(row=0, column=0, rowspan=2, sticky="nw", padx=(0, 12))

        ttk.Label(header, text=APP_TITLE, style="Title.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Label(header, text=f"Desenvolvedor: {DEVELOPER}", style="Developer.TLabel").grid(
            row=1, column=1, sticky="w", pady=(3, 0)
        )

        self.banner_image = self._load_image("robot-banner.png")
        if self.banner_image is not None:
            ttk.Label(header, image=self.banner_image).grid(
                row=2, column=0, columnspan=2, sticky="w", pady=(12, 0)
            )

        main = ttk.Frame(self.root, padding=(18, 8, 18, 12))
        main.grid(row=1, column=0, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(4, weight=1)

        self._build_prompt_section(main)
        self._build_file_section(main)
        self._build_automation_section(main)
        self._build_response_section(main)
        self._build_footer()

    def _build_prompt_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Prompt", padding=12)
        frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)

        self.prompt_combo = ttk.Combobox(frame, textvariable=self.prompt_var, state="readonly")
        self.prompt_combo.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.prompt_combo.bind("<<ComboboxSelected>>", self._on_prompt_selected)

        ttk.Button(frame, text="Personalizado", command=self._new_prompt).grid(row=0, column=1, padx=2)
        ttk.Button(frame, text="Assistente", command=self._open_prompt_assistant).grid(row=0, column=2, padx=2)
        self.edit_prompt_button = ttk.Button(frame, text="Editar", command=self._edit_prompt)
        self.edit_prompt_button.grid(row=0, column=3, padx=2)
        self.delete_prompt_button = ttk.Button(frame, text="Excluir", command=self._delete_prompt)
        self.delete_prompt_button.grid(row=0, column=4, padx=2)
        ttk.Button(frame, text="Importar do Resumator", command=self._import_prompts).grid(
            row=0, column=5, padx=(8, 0)
        )
        ttk.Button(frame, text="Exportar prompts", command=self._export_user_prompts).grid(
            row=0, column=6, padx=(8, 0)
        )

        ttk.Label(frame, text="Texto do prompt").grid(row=1, column=0, columnspan=7, sticky="w", pady=(10, 4))
        self.prompt_description_text = ScrolledText(frame, wrap="word", height=5, font=("Segoe UI", 9))
        self.prompt_description_text.grid(row=2, column=0, columnspan=7, sticky="ew")
        self.prompt_description_text.configure(state="disabled")

    def _build_file_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="PDFs para análise", padding=12)
        frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        frame.columnconfigure(0, weight=1)

        entry = ttk.Entry(frame, textvariable=self.pdf_var, state="readonly")
        entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.add_pdf_button = ttk.Button(frame, text="Adicionar PDFs", command=self._select_pdf)
        self.add_pdf_button.grid(row=0, column=1, padx=(0, 6))
        ttk.Button(frame, text="Limpar PDFs", command=self._clear_pdf_selection).grid(row=0, column=2)

        process_frame = ttk.Frame(frame)
        process_frame.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        process_frame.columnconfigure(1, weight=1)
        ttk.Label(process_frame, text="Nº do processo administrativo/judicial").grid(
            row=0, column=0, sticky="w", padx=(0, 8)
        )
        ttk.Entry(process_frame, textvariable=self.process_number_var).grid(row=0, column=1, sticky="ew")

    def _build_automation_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Envio à IA", padding=12)
        frame.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        frame.columnconfigure(7, weight=1)

        ttk.Label(frame, text="Destino:").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Radiobutton(
            frame,
            text="Nenhum",
            variable=self.assistant_var,
            value="none",
            command=self._on_assistant_selected,
        ).grid(row=0, column=1, sticky="w", padx=(0, 12))
        ttk.Radiobutton(
            frame,
            text="ChatGPT Desktop",
            variable=self.assistant_var,
            value="chatgpt",
            command=self._on_assistant_selected,
        ).grid(row=0, column=2, sticky="w", padx=(0, 12))
        ttk.Radiobutton(
            frame,
            text="Microsoft 365 Copilot",
            variable=self.assistant_var,
            value="copilot",
            command=self._on_assistant_selected,
        ).grid(row=0, column=3, sticky="w", padx=(0, 12))
        ttk.Radiobutton(
            frame,
            text="Google Gemini",
            variable=self.assistant_var,
            value="gemini",
            command=self._on_assistant_selected,
        ).grid(row=0, column=4, sticky="w", padx=(0, 12))
        ttk.Radiobutton(
            frame,
            text="LM Studio Desktop",
            variable=self.assistant_var,
            value="lmstudio_desktop",
            command=self._on_assistant_selected,
        ).grid(row=0, column=5, sticky="w", padx=(0, 12))
        ttk.Radiobutton(
            frame,
            text="Jus IA",
            variable=self.assistant_var,
            value="jusia",
            command=self._on_assistant_selected,
        ).grid(row=0, column=6, sticky="w", padx=(0, 12))

        ttk.Label(frame, text="Envio:").grid(row=1, column=0, sticky="w", pady=(8, 0), padx=(0, 8))
        self.delivery_text_radio = ttk.Radiobutton(
            frame,
            text="Texto colado",
            variable=self.delivery_mode_var,
            value=DELIVERY_TEXT,
            command=self._on_delivery_mode_selected,
        )
        self.delivery_text_radio.grid(row=1, column=1, sticky="w", pady=(8, 0), padx=(0, 12))
        self.delivery_docx_radio = ttk.Radiobutton(
            frame,
            text="Documento DOCX",
            variable=self.delivery_mode_var,
            value=DELIVERY_DOCX,
            command=self._on_delivery_mode_selected,
        )
        self.delivery_docx_radio.grid(row=1, column=2, sticky="w", pady=(8, 0), padx=(0, 12))

        self.attach_check = ttk.Checkbutton(frame, text="Anexar PDFs automaticamente", variable=self.attach_var)
        self.attach_check.grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(8, 0), padx=(0, 18)
        )
        self.submit_check = ttk.Checkbutton(frame, text="Enviar ao final", variable=self.submit_var)
        self.submit_check.grid(
            row=2, column=2, sticky="w", pady=(8, 0), padx=(0, 18)
        )
        self.send_button = ttk.Button(frame, text="Escolha um destino", command=self._send_to_assistant)
        self.send_button.grid(
            row=0, column=8, rowspan=3, sticky="e", padx=(12, 0)
        )
        self._refresh_send_button()

    def _build_response_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Resposta", padding=12)
        frame.grid(row=4, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        self.response_text = ScrolledText(frame, wrap="word", font=("Segoe UI", 10))
        self.response_text.grid(row=0, column=0, sticky="nsew")

        actions = ttk.Frame(frame)
        actions.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        actions.columnconfigure(7, weight=1)

        ttk.Button(actions, text="Capturar resposta da IA", command=self._capture_assistant_response).grid(
            row=0, column=0, padx=(0, 8)
        )
        ttk.Button(actions, text="Capturar texto copiado", command=self._capture_clipboard).grid(
            row=0, column=1, padx=(0, 8)
        )
        ttk.Button(actions, text="Limpar resposta", command=self._clear_response).grid(
            row=0, column=2, padx=(0, 8)
        )
        ttk.Button(actions, text="Exportar PDF", command=lambda: self._export_response("pdf")).grid(
            row=0, column=3, padx=(0, 8)
        )
        ttk.Button(actions, text="Exportar DOCX", command=lambda: self._export_response("docx")).grid(
            row=0, column=4, padx=(0, 8)
        )
        ttk.Button(actions, text="Exportar JSON", command=lambda: self._export_response("json")).grid(
            row=0, column=5, padx=(0, 8)
        )
        ttk.Button(actions, text="Acionar QUIMERA", command=self._export_to_solicitador).grid(
            row=0, column=6, padx=(0, 8)
        )
        ttk.Button(actions, text="Abrir último arquivo", command=self._open_last_output).grid(
            row=1, column=0, padx=(0, 8), pady=(8, 0)
        )
        ttk.Button(actions, text="Exportar logs TXT", command=self._export_logs_txt).grid(
            row=1, column=1, padx=(0, 8), pady=(8, 0)
        )
        ttk.Button(actions, text="Readme", command=self._open_readme_txt).grid(
            row=1, column=2, padx=(0, 8), pady=(8, 0)
        )

    def _build_footer(self) -> None:
        footer = ttk.Frame(self.root, padding=(18, 0, 18, 14))
        footer.grid(row=2, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        self.status_label = ttk.Label(footer, textvariable=self.status_var, style="Status.TLabel")
        self.status_label.grid(
            row=0, column=0, sticky="w"
        )

    def _reload_prompts(self, keep_id: str | None = None) -> None:
        self.prompts = self.store.all()
        self.prompt_combo["values"] = [self._prompt_label(prompt) for prompt in self.prompts]
        if not self.prompts:
            self.selected_prompt_id = None
            self.prompt_var.set("")
            self._set_prompt_description(None)
            self._refresh_prompt_actions()
            return

        selected = next(
            (
                prompt
                for prompt in self.prompts
                if prompt.id == (keep_id or DEFAULT_SELECTED_PROMPT_ID)
            ),
            self.prompts[0],
        )
        self.selected_prompt_id = selected.id
        self.prompt_var.set(self._prompt_label(selected))
        self._set_prompt_description(selected)
        self._refresh_prompt_actions()

    def _on_prompt_selected(self, _: tk.Event) -> None:
        index = self.prompt_combo.current()
        if index < 0 or index >= len(self.prompts):
            return
        prompt = self.prompts[index]
        self.transient_prompt_name = None
        self.transient_prompt_content = None
        self.selected_prompt_id = prompt.id
        self._set_prompt_description(prompt)
        self._refresh_prompt_actions()

    def _selected_prompt(self) -> Prompt | None:
        if self.transient_prompt_content:
            return Prompt(
                id="assistant-transient-prompt",
                name=self.transient_prompt_name or "Prompt montado pelo Assistente",
                content=self.transient_prompt_content,
                updated_at=datetime.now().isoformat(timespec="seconds"),
                system=False,
                protected=False,
            )
        if not self.selected_prompt_id:
            return None
        return self.store.get(self.selected_prompt_id)

    @staticmethod
    def _prompt_label(prompt: Prompt) -> str:
        if prompt.protected:
            return f"{prompt.name} (padrão protegido)"
        if prompt.system:
            return f"{prompt.name} (prompt do sistema)"
        return prompt.name

    def _refresh_prompt_actions(self) -> None:
        prompt = self.store.get(self.selected_prompt_id) if self.selected_prompt_id else None
        state = "normal" if prompt is not None else "disabled"
        self.edit_prompt_button.configure(state=state)
        self.delete_prompt_button.configure(state=state)

    def _set_prompt_description(self, prompt: Prompt | None) -> None:
        text = ""
        if prompt is not None:
            text = prompt.content.strip()
        self.prompt_description_text.configure(state="normal")
        self.prompt_description_text.delete("1.0", "end")
        self.prompt_description_text.insert("1.0", text)
        self.prompt_description_text.configure(state="disabled")

    def _refresh_send_button(self) -> None:
        assistant_key = self.assistant_var.get()
        self._refresh_delivery_controls(assistant_key)
        self._refresh_pdf_controls(assistant_key)
        if assistant_key == "none":
            self.send_button.configure(text="Escolha um destino", state="disabled")
            self.attach_check.configure(state="disabled")
            self.submit_check.configure(state="disabled")
            return
        if assistant_key == "lmstudio_desktop":
            self.send_button.configure(text="Enviar ao LM Studio", state="normal")
            self.attach_check.configure(state="normal")
            self.submit_check.configure(state="normal")
            return

        assistant_name = assistant_display_name(assistant_key).replace(" Desktop", "")
        self.send_button.configure(text=f"Enviar ao {assistant_name}", state="normal")
        self.attach_check.configure(state="normal")
        self.submit_check.configure(state="normal")

    def _refresh_delivery_controls(self, assistant_key: str) -> None:
        text_state = "normal"
        docx_state = "normal"
        if assistant_key == "none":
            text_state = "disabled"
            docx_state = "disabled"
        elif assistant_key == "copilot":
            self.delivery_mode_var.set(DELIVERY_TEXT)
            docx_state = "disabled"
        elif assistant_key == "lmstudio_desktop":
            self.delivery_mode_var.set(DELIVERY_TEXT)
            docx_state = "disabled"
        self.delivery_text_radio.configure(state=text_state)
        self.delivery_docx_radio.configure(state=docx_state)

    def _refresh_pdf_controls(self, assistant_key: str | None = None) -> None:
        add_pdf_button = getattr(self, "add_pdf_button", None)
        if add_pdf_button is None:
            return
        selected_assistant = assistant_key if assistant_key is not None else self.assistant_var.get()
        add_pdf_button.configure(state="normal" if selected_assistant == "none" else "disabled")

    def _on_delivery_mode_selected(self) -> None:
        self._refresh_send_button()

    def _on_assistant_selected(self) -> None:
        self._refresh_send_button()
        assistant_key = self._desktop_assistant_key(self.assistant_var.get())
        if assistant_key is None:
            self._set_status("Destino: nenhum.")
            return

        assistant_name = assistant_display_name(assistant_key)
        suspend_seconds = (
            LMSTUDIO_SELECTION_MOUSE_SUSPEND_SECONDS
            if assistant_key == "lmstudio"
            else ASSISTANT_SELECTION_MOUSE_SUSPEND_SECONDS
        )
        self._begin_mouse_suspend(suspend_seconds)
        self._set_status(f"Abrindo {assistant_name}...")
        threading.Thread(target=self._open_assistant_worker, args=(assistant_key,), daemon=True).start()

    @staticmethod
    def _desktop_assistant_key(assistant_key: str) -> str | None:
        if assistant_key in {"chatgpt", "copilot", "gemini", "jusia"}:
            return assistant_key
        if assistant_key == "lmstudio_desktop":
            return "lmstudio"
        return None

    def _open_assistant_worker(self, assistant_key: str) -> None:
        result = open_desktop_assistant(assistant_key)
        self.root.after(0, lambda: self._handle_open_result(result))

    def _handle_open_result(self, result) -> None:
        detail = ""
        if result.notes:
            detail = " " + " ".join(result.notes)
        self._set_status(result.message + detail)

    def _new_prompt(self) -> None:
        editor = PromptEditor(self.root, title="Prompt personalizado")
        result = editor.show()
        if result is None:
            return
        prompt = self.store.create(result["name"], result["content"])
        self._reload_prompts(prompt.id)
        self._set_status("Prompt criado.")

    def _open_prompt_assistant(self) -> None:
        assistant = PromptAssistantDialog(self.root)
        result = assistant.show()
        if result is None:
            return

        prompt_text = result["content"].strip()
        prompt_name = result["name"].strip() or "Prompt do Assistente"
        if result["save_as_system"]:
            prompt = self.store.create(prompt_name, prompt_text, system=True)
            self.transient_prompt_name = None
            self.transient_prompt_content = None
            self._reload_prompts(prompt.id)
            self._set_status("Prompt do sistema criado pelo Assistente.")
            return

        self.selected_prompt_id = None
        self.transient_prompt_name = prompt_name
        self.transient_prompt_content = prompt_text
        self.prompt_combo.set(f"{prompt_name} (não salvo)")
        self._set_prompt_description(self._selected_prompt())
        self._refresh_prompt_actions()
        self._set_status("Prompt montado pelo Assistente.")

    def _edit_prompt(self) -> None:
        prompt = self._selected_prompt()
        if prompt is None:
            messagebox.showwarning(APP_TITLE, "Selecione um prompt para editar.")
            return
        editor = PromptEditor(self.root, title="Editar prompt", prompt=prompt)
        result = editor.show()
        if result is None:
            return
        try:
            updated = self.store.update(prompt.id, result["name"], result["content"])
        except PermissionError as exc:
            messagebox.showwarning(APP_TITLE, str(exc))
            self._refresh_prompt_actions()
            return
        self._reload_prompts(updated.id)
        self._set_status("Prompt atualizado.")

    def _delete_prompt(self) -> None:
        prompt = self._selected_prompt()
        if prompt is None:
            messagebox.showwarning(APP_TITLE, "Selecione um prompt para excluir.")
            return
        confirmed = messagebox.askyesno(
            "Excluir prompt",
            f"Excluir o prompt '{prompt.name}'?",
            icon="warning",
        )
        if not confirmed:
            return
        try:
            self.store.delete(prompt.id)
        except PermissionError as exc:
            messagebox.showwarning(APP_TITLE, str(exc))
            self._refresh_prompt_actions()
            return
        self._reload_prompts()
        self._set_status("Prompt excluido.")

    def _import_prompts(self) -> None:
        source_paths = self._default_resumator_prompts_paths()
        if not source_paths:
            selected = filedialog.askopenfilename(
                title="Selecionar prompts do Resumator",
                filetypes=[
                    ("Arquivo de prompts", "prompts.json"),
                    ("Arquivos JSON", "*.json"),
                    ("Todos os arquivos", "*.*"),
                ],
            )
            if not selected:
                return
            source_paths = [Path(selected)]

        source_list = "\n".join(str(path) for path in source_paths)
        confirmed = messagebox.askyesno(
            "Importar prompts",
            f"Importar prompts de:\n{source_list}\n\nPrompts já existentes serão ignorados.",
        )
        if not confirmed:
            return

        total_imported = 0
        total_skipped = 0
        try:
            for source_path in source_paths:
                imported, skipped = self.store.import_from_file(source_path, system=True)
                total_imported += imported
                total_skipped += skipped
        except Exception as exc:  # noqa: BLE001 - surfaced to user
            write_exception("Falha ao importar prompts", exc)
            messagebox.showerror(APP_TITLE, f"Não foi possível importar os prompts: {exc}")
            return

        self._reload_prompts()
        if total_imported == 0 and total_skipped:
            detail = "Nenhum prompt novo foi encontrado; os prompts detectados já existiam no Resumator."
        else:
            detail = f"Importados: {total_imported}\nIgnorados: {total_skipped}"
        messagebox.showinfo(
            APP_TITLE,
            f"Importação concluída.\n\n{detail}",
        )
        self._set_status(f"Prompts importados: {total_imported}. Ignorados: {total_skipped}.")

    def _export_user_prompts(self) -> None:
        default_name = f"prompts-resumator-10.1-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        path = filedialog.asksaveasfilename(
            title="Exportar prompts criados pelo usuário",
            defaultextension=".json",
            initialdir=str(_downloads_dir()),
            initialfile=default_name,
            filetypes=[("Arquivos JSON", "*.json")],
        )
        if not path:
            return
        try:
            output_path = Path(path)
            exported = self.store.export_user_prompts(output_path)
        except Exception as exc:  # noqa: BLE001 - surfaced to user
            messagebox.showerror(APP_TITLE, f"Não foi possível exportar os prompts: {exc}")
            return
        self.last_output_path = output_path
        self._set_status(f"Prompts exportados: {output_path}")
        messagebox.showinfo(APP_TITLE, f"Prompts criados pelo usuário exportados: {exported}.")

    def _default_resumator_prompts_paths(self) -> list[Path]:
        base_dirs = [APP_DIR, Path.cwd(), Path(sys.executable).resolve().parent]
        if not getattr(sys, "frozen", False):
            base_dirs.append(Path(__file__).resolve().parents[1])

        candidates: list[Path] = []
        for base_dir in base_dirs:
            for parent in [base_dir, *base_dir.parents]:
                candidates.extend(
                    [
                        parent / "Resumator" / "data" / "prompts.json",
                        parent / "Resumator 3.0" / "data" / "prompts.json",
                        parent / "Resumator 3.0" / "prompts.json",
                        parent / "Resumator 2.0" / "prompts.json",
                    ]
                )

        found: list[Path] = []
        seen: set[Path] = set()
        current_path = PROMPTS_PATH.resolve()
        for candidate in candidates:
            if not candidate.exists():
                continue
            resolved = candidate.resolve()
            if resolved == current_path or resolved in seen:
                continue
            seen.add(resolved)
            found.append(candidate)
        return found

    def _default_resumator_prompts_path(self) -> Path | None:
        paths = self._default_resumator_prompts_paths()
        return paths[0] if paths else None

    def _select_pdf(self) -> None:
        if self.assistant_var.get() != "none":
            messagebox.showwarning(
                APP_TITLE,
                "Para adicionar PDFs, selecione 'Nenhum' no destino de IA.",
            )
            self._set_status("Adição de PDFs bloqueada após a escolha da IA.")
            return

        selected = filedialog.askopenfilenames(
            title="Selecionar até 10 PDFs",
            filetypes=[("Arquivos PDF", "*.pdf"), ("Todos os arquivos", "*.*")],
        )
        if not selected:
            return

        previous_paths = _deduplicate_paths(self.pdf_paths)
        selected_paths = [Path(path) for path in selected]
        combined_paths = _deduplicate_paths([*previous_paths, *selected_paths])

        if len(combined_paths) > MAX_PDF_FILES:
            messagebox.showwarning(
                APP_TITLE,
                (
                    f"A seleção total ficaria com {len(combined_paths)} PDFs. "
                    f"Selecione no máximo {MAX_PDF_FILES} arquivos PDF."
                ),
            )
            return

        added_count = len(combined_paths) - len(previous_paths)
        self.pdf_paths = combined_paths
        self.pdf_var.set(_format_pdf_selection(self.pdf_paths))
        if added_count:
            self._set_status(f"{len(self.pdf_paths)} PDF(s) selecionado(s). {added_count} adicionado(s).")
        else:
            self._set_status(f"{len(self.pdf_paths)} PDF(s) selecionado(s). Arquivos ja estavam na lista.")

    def _clear_pdf_selection(self) -> None:
        self.pdf_paths = []
        self.pdf_var.set("")
        self._set_status("Seleção de PDFs limpa.")

    def _send_to_assistant(self) -> None:
        prompt = self._selected_prompt()
        if prompt is None:
            messagebox.showwarning(APP_TITLE, "Crie ou selecione um prompt antes de enviar.")
            return
        if not self.pdf_paths or any(not path.exists() for path in self.pdf_paths):
            messagebox.showwarning(APP_TITLE, "Selecione de 1 a 10 arquivos PDF válidos.")
            return

        assistant_key = self.assistant_var.get()
        if assistant_key == "none":
            messagebox.showwarning(APP_TITLE, "Escolha um destino antes de enviar.")
            return
        if assistant_key == "lmstudio_desktop":
            assistant_name = "LM Studio Desktop"
        else:
            assistant_name = assistant_display_name(assistant_key)
        delivery_mode = self._effective_delivery_mode(assistant_key)
        prompt_document_path: Path | None = None
        if delivery_mode == DELIVERY_DOCX:
            try:
                prompt_document_path = self._create_prompt_document(prompt, list(self.pdf_paths))
            except Exception as exc:  # noqa: BLE001 - surfaced to user
                write_exception("Falha ao gerar DOCX de envio", exc)
                messagebox.showerror(APP_TITLE, f"Não foi possível gerar o DOCX de envio: {exc}")
                return
        if not self._confirm_local_automation(assistant_name, delivery_mode):
            self._set_status("Envio cancelado pelo usuario.")
            return
        self.send_button.configure(state="disabled")
        self._begin_mouse_suspend(SEND_MOUSE_SUSPEND_SECONDS)
        self._set_status(f"Enviando ao {assistant_name}...")
        write_log(
            "Envio solicitado. "
            f"destino={assistant_key} modo={delivery_mode} pdfs={[str(path) for path in self.pdf_paths]} "
            f"docx={prompt_document_path}"
        )
        self._start_send_worker(
            assistant_key,
            prompt,
            list(self.pdf_paths),
            self.attach_var.get(),
            self.submit_var.get(),
            delivery_mode,
            prompt_document_path,
        )

    def _effective_delivery_mode(self, assistant_key: str) -> str:
        if assistant_key == "copilot":
            return DELIVERY_TEXT
        if assistant_key == "lmstudio_desktop":
            return DELIVERY_TEXT
        mode = self.delivery_mode_var.get()
        if mode not in {DELIVERY_TEXT, DELIVERY_DOCX}:
            return DELIVERY_TEXT
        return mode

    def _create_prompt_document(self, prompt: Prompt, pdf_paths: list[Path]) -> Path:
        output_dir = Path(tempfile.gettempdir()) / "resumator-10.1-envios"
        output_path = _unique_output_path(
            output_dir,
            f"prompt-ia-resumator-10.1-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            ".docx",
        )
        return export_prompt_docx(
            output_path,
            prompt.content,
            prompt_name=prompt.name,
            source_pdf=pdf_paths,
        )

    def _confirm_local_automation(self, assistant_name: str, delivery_mode: str) -> bool:
        pdf_list = "\n".join(f"- {path}" for path in self.pdf_paths)
        attach_action = (
            "tentar anexar automaticamente os PDFs selecionados"
            if self.attach_var.get()
            else "nao anexar automaticamente os PDFs"
        )
        delivery_action = (
            "colar o prompt como texto"
            if delivery_mode == DELIVERY_TEXT
            else "anexar o prompt em um documento DOCX"
        )
        submit_action = "pressionar Enter ao final" if self.submit_var.get() else "deixar o envio pausado"
        return messagebox.askyesno(
            "Autorizar automacao local",
            (
                f"{APP_TITLE} vai ativar o {assistant_name}, {attach_action}, "
                f"{delivery_action} e {submit_action}.\n\n"
                "PDFs autorizados nesta acao:\n"
                f"{pdf_list}\n\n"
                "Continuar?"
            ),
            icon="question",
        )

    def _start_send_worker(
        self,
        assistant_key: str,
        prompt: Prompt,
        pdf_paths: list[Path],
        attach_pdf: bool,
        submit: bool,
        delivery_mode: str,
        prompt_document_path: Path | None,
    ) -> None:
        threading.Thread(
            target=self._send_worker,
            args=(
                assistant_key,
                prompt,
                pdf_paths,
                attach_pdf,
                submit,
                delivery_mode,
                prompt_document_path,
            ),
            daemon=True,
        ).start()

    def _send_worker(
        self,
        assistant_key: str,
        prompt: Prompt,
        pdf_paths: list[Path],
        attach_pdf: bool,
        submit: bool,
        delivery_mode: str,
        prompt_document_path: Path | None,
    ) -> None:
        paste_prompt_text = delivery_mode == DELIVERY_TEXT
        if assistant_key == "lmstudio_desktop":
            result = send_to_desktop_assistant(
                "lmstudio",
                prompt.content,
                pdf_paths,
                attach_pdf=attach_pdf,
                submit=submit,
                prompt_document_path=prompt_document_path,
                paste_prompt_text=paste_prompt_text,
            )
        else:
            result = send_to_desktop_assistant(
                assistant_key,
                prompt.content,
                pdf_paths,
                attach_pdf=attach_pdf,
                submit=submit,
                prompt_document_path=prompt_document_path,
                paste_prompt_text=paste_prompt_text,
            )
        self.root.after(0, lambda: self._handle_send_result(result))

    def _handle_send_result(self, result) -> None:
        self._refresh_send_button()
        detail = ""
        if result.notes:
            detail = " " + " ".join(result.notes)
        self._set_status(result.message + detail)
        if not result.ok:
            messagebox.showerror(APP_TITLE, result.message)
            return
        response_text = getattr(result, "text", "")
        if response_text:
            self.response_text.delete("1.0", "end")
            self.response_text.insert("1.0", response_text)
            messagebox.showinfo(APP_TITLE, "Resposta gerada pelo LM Studio.")

    def _capture_assistant_response(self) -> None:
        assistant_key = self._desktop_assistant_key(self.assistant_var.get())
        if assistant_key is None:
            messagebox.showwarning(APP_TITLE, "Escolha o destino de IA antes de capturar a resposta.")
            return

        assistant_name = assistant_display_name(assistant_key)
        confirmed = messagebox.askyesno(
            "Autorizar captura automática",
            (
                f"{APP_TITLE} vai ativar o {assistant_name}, procurar o botao de copiar "
                "resposta, aciona-lo e preencher o campo Resposta com o texto copiado.\n\n"
                "Continuar?"
            ),
            icon="question",
        )
        if not confirmed:
            self._set_status("Captura automática cancelada pelo usuario.")
            return

        self._set_status(f"Capturando resposta do {assistant_name}...")
        threading.Thread(
            target=self._capture_assistant_response_worker,
            args=(assistant_key,),
            daemon=True,
        ).start()

    def _capture_assistant_response_worker(self, assistant_key: str) -> None:
        result = capture_latest_response_from_assistant(assistant_key)
        self.root.after(0, lambda: self._handle_capture_assistant_result(result))

    def _handle_capture_assistant_result(self, result) -> None:
        detail = ""
        if result.notes:
            detail = " " + " ".join(result.notes)
        self._set_status(result.message + detail)
        if not result.ok:
            messagebox.showerror(APP_TITLE, result.message)
            return
        if not result.text:
            messagebox.showwarning(APP_TITLE, "A captura automática não retornou texto.")
            return
        self.response_text.delete("1.0", "end")
        self.response_text.insert("1.0", result.text)
        messagebox.showinfo(APP_TITLE, "Resposta capturada automaticamente.")

    def _capture_clipboard(self) -> None:
        try:
            text = get_clipboard_text().strip()
        except Exception as exc:  # noqa: BLE001 - surfaced to user
            messagebox.showerror(APP_TITLE, f"Não foi possível ler a área de transferência: {exc}")
            return
        if not text:
            messagebox.showwarning(APP_TITLE, "A área de transferência não contém texto.")
            return
        self.response_text.delete("1.0", "end")
        self.response_text.insert("1.0", text)
        self._set_status("Resposta capturada da área de transferência.")

    def _clear_response(self) -> None:
        self.response_text.delete("1.0", "end")
        self._set_status("Resposta limpa.")

    def _export_response(self, output_format: str) -> None:
        text = self.response_text.get("1.0", "end").strip()
        if not text:
            messagebox.showwarning(APP_TITLE, "Cole ou capture a resposta antes de exportar.")
            return

        prompt = self._selected_prompt()
        export_stem = self._export_stem_from_process_number()
        if export_stem is None:
            return

        if output_format == "json":
            extension = ".json"
            file_label = "JSON"
            filetypes = [("Arquivos JSON", "*.json")]
            exporter = export_response_json
        elif output_format == "docx":
            extension = ".docx"
            file_label = "DOCX"
            filetypes = [("Documentos Word", "*.docx")]
            exporter = export_response_docx
        else:
            extension = ".pdf"
            file_label = "PDF"
            filetypes = [("Arquivos PDF", "*.pdf")]
            exporter = export_response_pdf

        default_name = f"{export_stem}{extension}"
        path = filedialog.asksaveasfilename(
            title=f"Salvar resposta em {file_label}",
            defaultextension=extension,
            initialdir=str(OUTPUT_DIR),
            initialfile=default_name,
            filetypes=filetypes,
        )
        if not path:
            return
        output_path = _enforce_export_filename(Path(path), default_name)
        selected_path = Path(path)
        if output_path != selected_path and output_path.exists():
            replace = messagebox.askyesno(
                APP_TITLE,
                f"O arquivo {output_path.name} já existe em {output_path.parent}. Deseja substituir?",
            )
            if not replace:
                return
        try:
            self.last_output_path = exporter(
                output_path,
                text,
                prompt_name=prompt.name if prompt else None,
                source_pdf=list(self.pdf_paths),
            )
        except Exception as exc:  # noqa: BLE001 - surfaced to user
            write_exception(f"Falha ao exportar {file_label}", exc)
            messagebox.showerror(APP_TITLE, f"Não foi possível gerar o arquivo {file_label}: {exc}")
            return
        self._set_status(f"{file_label} gerado: {self.last_output_path}")
        messagebox.showinfo(APP_TITLE, f"Resposta exportada em {file_label}.")

    def _export_stem_from_process_number(self) -> str | None:
        process_number = self.process_number_var.get().strip()
        if not process_number:
            process_number = simpledialog.askstring(
                APP_TITLE,
                "Informe o número do processo administrativo ou judicial para nomear o arquivo exportado.",
                parent=self.root,
            )
            if process_number is None:
                return None
            process_number = process_number.strip()
            if not process_number:
                messagebox.showwarning(
                    APP_TITLE,
                    "Informe o número do processo administrativo ou judicial antes de exportar.",
                )
                return None
            self.process_number_var.set(process_number)

        safe_process_number = _sanitize_process_number_for_filename(process_number)
        if not safe_process_number:
            messagebox.showwarning(
                APP_TITLE,
                "O número do processo informado não gera um nome de arquivo válido.",
            )
            return None
        return f"Resumator-{safe_process_number}"

    def _export_to_solicitador(self) -> None:
        text = self.response_text.get("1.0", "end").strip()
        if not text:
            messagebox.showwarning(APP_TITLE, "Cole ou capture a resposta antes de acionar o QUIMERA.")
            return

        prompt = self._selected_prompt()
        self._set_status("Abrindo QUIMERA...")
        write_log("Acionamento do QUIMERA solicitado.")
        threading.Thread(
            target=self._export_to_solicitador_worker,
            args=(text, prompt.name if prompt else None, list(self.pdf_paths)),
            daemon=True,
        ).start()

    def _export_to_solicitador_worker(
        self,
        text: str,
        prompt_name: str | None,
        pdf_paths: list[Path],
    ) -> None:
        result = export_summary_to_solicitador(text, prompt_name=prompt_name, source_pdf=pdf_paths)
        self.root.after(0, lambda: self._handle_solicitador_result(result))

    def _handle_solicitador_result(self, result: SolicitadorExportResult) -> None:
        if result.payload_path is not None:
            self.last_output_path = result.payload_path
        detail = ""
        if result.target:
            detail = f" Alvo: {result.target}"
        elif result.notes:
            detail = " " + " ".join(result.notes)
        self._set_status(result.message + detail)
        if not result.ok:
            messagebox.showerror(APP_TITLE, result.message)
            return

    def _export_logs_txt(self) -> None:
        default_name = f"logs-resumator-10.1-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"
        path = filedialog.asksaveasfilename(
            title="Salvar logs em TXT",
            defaultextension=".txt",
            initialdir=str(OUTPUT_DIR),
            initialfile=default_name,
            filetypes=[("Arquivos TXT", "*.txt")],
        )
        if not path:
            return
        try:
            output_path = Path(path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(collect_logs(), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001 - surfaced to user
            write_exception("Falha ao exportar logs", exc)
            messagebox.showerror(APP_TITLE, f"Não foi possível exportar os logs: {exc}")
            return
        self.last_output_path = output_path
        self._set_status(f"Logs exportados: {output_path}")
        messagebox.showinfo(APP_TITLE, "Logs exportados em TXT.")

    def _open_readme_txt(self) -> None:
        readme_path = _readme_txt_path()
        if readme_path is None:
            messagebox.showwarning(APP_TITLE, "README.txt não encontrado na pasta do Resumator.")
            return
        try:
            _open_path(readme_path)
        except Exception as exc:  # noqa: BLE001 - surfaced to user
            write_exception("Falha ao abrir README", exc)
            messagebox.showerror(APP_TITLE, f"Não foi possível abrir o README: {exc}")
            return
        self.last_output_path = readme_path
        self._set_status(f"README aberto: {readme_path}")

    def _open_last_output(self) -> None:
        if self.last_output_path is None or not self.last_output_path.exists():
            messagebox.showwarning(APP_TITLE, "Ainda não há arquivo gerado nesta sessão.")
            return
        _open_path(self.last_output_path)

    def _begin_mouse_suspend(self, seconds: int) -> None:
        self._mouse_suspend_generation += 1
        generation = self._mouse_suspend_generation
        self._mouse_suspend_active = True
        self._status_after_mouse_suspend = None
        self._release_mouse_block()
        self._install_mouse_block()
        self.status_var.set(_mouse_suspend_status(seconds))
        self._set_status_style(alert=True)
        self.root.after(_mouse_suspend_ms(seconds), lambda: self._finish_mouse_suspend(generation))

    def _finish_mouse_suspend(self, generation: int) -> None:
        if generation != self._mouse_suspend_generation:
            return
        self._mouse_suspend_active = False
        self._release_mouse_block()
        message = self._status_after_mouse_suspend or "Pronto."
        self._status_after_mouse_suspend = None
        self._set_status_style(alert=False)
        self.status_var.set(message)

    def _install_mouse_block(self) -> None:
        if os.name != "nt":
            return

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        hook_handle = None

        def block_mouse(n_code: int, w_param: int, l_param: int) -> int:
            if n_code >= HC_ACTION:
                try:
                    mouse_info = ctypes.cast(l_param, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                    if mouse_info.flags & (LLMHF_INJECTED | LLMHF_LOWER_IL_INJECTED):
                        return user32.CallNextHookEx(self._mouse_block_hook or None, n_code, w_param, l_param)
                except Exception:
                    pass
                return 1
            return user32.CallNextHookEx(self._mouse_block_hook or None, n_code, w_param, l_param)

        try:
            user32.SetWindowsHookExW.argtypes = [
                ctypes.c_int,
                LOW_LEVEL_MOUSE_PROC,
                wintypes.HINSTANCE,
                wintypes.DWORD,
            ]
            user32.SetWindowsHookExW.restype = wintypes.HHOOK
            user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
            user32.CallNextHookEx.restype = wintypes.LPARAM
            kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
            kernel32.GetModuleHandleW.restype = wintypes.HMODULE

            callback = LOW_LEVEL_MOUSE_PROC(block_mouse)
            module_handle = kernel32.GetModuleHandleW(None)
            hook_handle = user32.SetWindowsHookExW(WH_MOUSE_LL, callback, module_handle, 0)
            if not hook_handle:
                hook_handle = user32.SetWindowsHookExW(WH_MOUSE_LL, callback, None, 0)
            if hook_handle:
                self._mouse_block_callback = callback
                self._mouse_block_hook = int(hook_handle)
        except Exception as exc:  # noqa: BLE001 - mouse blocking is best-effort protection
            write_exception("Falha ao instalar bloqueio temporario do mouse", exc)

    def _confine_mouse_to_current_position(self) -> None:
        if os.name != "nt":
            return

        user32 = ctypes.windll.user32
        point = wintypes.POINT()
        try:
            user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
            user32.GetCursorPos.restype = wintypes.BOOL
            user32.ClipCursor.argtypes = [ctypes.POINTER(wintypes.RECT)]
            user32.ClipCursor.restype = wintypes.BOOL
            if not user32.GetCursorPos(ctypes.byref(point)):
                return
            rect = wintypes.RECT(point.x, point.y, point.x + 1, point.y + 1)
            self._mouse_clip_active = bool(user32.ClipCursor(ctypes.byref(rect)))
        except Exception as exc:  # noqa: BLE001 - mouse clipping is best-effort protection
            write_exception("Falha ao confinar temporariamente o mouse", exc)

    def _release_mouse_block(self) -> None:
        if os.name != "nt":
            return

        user32 = ctypes.windll.user32
        if self._mouse_clip_active:
            try:
                user32.ClipCursor.argtypes = [ctypes.c_void_p]
                user32.ClipCursor.restype = wintypes.BOOL
                user32.ClipCursor(None)
            except Exception as exc:  # noqa: BLE001 - release must not interrupt the app
                write_exception("Falha ao liberar confinamento temporario do mouse", exc)
            finally:
                self._mouse_clip_active = False
        if self._mouse_block_hook:
            try:
                user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
                user32.UnhookWindowsHookEx.restype = wintypes.BOOL
                user32.UnhookWindowsHookEx(wintypes.HHOOK(self._mouse_block_hook))
            except Exception as exc:  # noqa: BLE001 - release must not interrupt the app
                write_exception("Falha ao liberar bloqueio temporario do mouse", exc)
            finally:
                self._mouse_block_hook = None
                self._mouse_block_callback = None

    def _on_close(self) -> None:
        self._release_mouse_block()
        self.root.destroy()

    def _set_status_style(self, alert: bool) -> None:
        status_label = getattr(self, "status_label", None)
        if status_label is None:
            return
        status_label.configure(style="StatusAlert.TLabel" if alert else "Status.TLabel")

    def _set_status(self, message: str) -> None:
        if getattr(self, "_mouse_suspend_active", False):
            self._status_after_mouse_suspend = message
            return
        self._set_status_style(alert=False)
        self.status_var.set(message)


def _downloads_dir() -> Path:
    downloads = Path.home() / "Downloads"
    return downloads if downloads.exists() else Path.home()


def _desktop_dir() -> Path:
    desktop = Path.home() / "Desktop"
    return desktop if desktop.exists() else Path.home()


def _open_path(path: Path) -> None:
    if os.name == "nt":
        os.startfile(path)  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", str(path)])


def _unique_output_path(directory: Path, stem: str, extension: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    candidate = directory / f"{stem}{extension}"
    counter = 2
    while candidate.exists():
        candidate = directory / f"{stem}-{counter}{extension}"
        counter += 1
    return candidate


def _sanitize_process_number_for_filename(process_number: str) -> str:
    cleaned = " ".join(process_number.strip().split())
    cleaned = cleaned.translate(str.maketrans({char: "-" for char in '<>:"/\\|?*'}))
    cleaned = re.sub(r"[-\s]+", "-", cleaned)
    return cleaned.strip(" .-")


def _enforce_export_filename(selected_path: Path, filename: str) -> Path:
    return selected_path.parent / filename


def _format_pdf_selection(paths: list[Path]) -> str:
    if not paths:
        return ""
    if len(paths) == 1:
        return str(paths[0])
    names = ", ".join(path.name for path in paths)
    return f"{len(paths)} PDFs selecionados: {names}"


def _deduplicate_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    unique_paths: list[Path] = []
    for path in paths:
        key = _path_selection_key(path)
        if key in seen:
            continue
        seen.add(key)
        unique_paths.append(path)
    return unique_paths


def _path_selection_key(path: Path) -> str:
    try:
        normalized = path.resolve()
    except OSError:
        normalized = path.absolute()
    text = str(normalized)
    return text.casefold() if os.name == "nt" else text


def _readme_txt_path() -> Path | None:
    candidates = [
        APP_DIR / "README.txt",
        APP_DIR / "_internal" / "README.txt",
        _resource_path("README.txt"),
        Path(__file__).resolve().parents[1] / "README.txt",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


class PromptAssistantDialog:
    UNSELECTED_VALUE = "__resumator_prompt_assistant_unselected__"
    ROLE_OPTIONS = [
        "advogado de pessoa física ou empresa privada",
        "procurador da União ou de Autarquia Federal",
        "especialista de Agência Reguladora",
        "analista processual do Poder Judiciário",
    ]
    EXPERTISE_OPTIONS = [
        "membro de corregedoria de órgão público",
        "Direito Civil e Empresarial",
        "Direito administrativo com enfoque em processo administrativo disciplinar",
        "Direito Público (Direito Tributário e Direito administrativo em geral)",
        "Direito Processual Civil",
        "Direito Minerário e engenharia de mineração",
        "Direito e Engenharia do Petróleo, Gás Natural e Biocombustíveis",
        "Direito no campo da Saúde Suplementar",
        "Transportes terrestres (ANTT) e Direito de trânsito",
        "Metrologia, Qualidade e Tecnologia",
        "Direito Ambiental e Engenharia Ambiental",
        "Vigilância Sanitária",
        "Direito Previdenciário",
        "Títulos e Valores Mobiliários",
        "Direito Marítimo",
    ]
    DOCUMENT_OPTIONS = [
        "documento único (exemplo: petição inicial, contestação, sentença, decisão administrativa)",
        "processo administrativo",
        "processo judicial do Eproc",
        "processo judicial do PJe",
        "dossiê de processo judicial baixado do SuperSapiens",
    ]
    REPORT_OPTIONS = [
        "Relatório objetivo imparcial",
        "Relatório detalhado imparcial",
        "Relatório e análise administrativa e jurídica objetiva",
        "Relatório e análise administrativa e jurídica detalhada",
    ]
    OPINION_OPTIONS = [
        "a IA deverá sugerir a medida a ser adotada",
        "a IA não deverá opinar",
    ]

    def __init__(self, parent: tk.Tk):
        self.parent = parent
        self.result: dict[str, str | bool] | None = None
        self.option_vars: dict[str, tk.StringVar] = {}
        self.save_as_system_var = tk.BooleanVar(value=False)
        self.name_var = tk.StringVar(
            value=f"Prompt Assistente {datetime.now().strftime('%Y-%m-%d %H%M')}"
        )

        self.window = tk.Toplevel(parent)
        self.window.title("Assistente de Prompt")
        self.window.geometry("1120x900")
        self.window.minsize(980, 760)
        self.window.transient(parent)
        self.window.grab_set()
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(0, weight=1)

        container = ttk.Frame(self.window, padding=14)
        container.grid(row=0, column=0, sticky="nsew")
        container.columnconfigure(0, weight=1)
        container.columnconfigure(1, weight=1)
        container.rowconfigure(4, weight=1)

        self._build_section(container, 0, 0, "1. Você é um:", "role", self.ROLE_OPTIONS)
        self._build_section(
            container,
            0,
            1,
            "2. Conhecimento especializado:",
            "expertise",
            self.EXPERTISE_OPTIONS,
            rowspan=4,
            description=(
                "O papel da inteligência artificial indicado no item anterior deverá contar com conhecimento "
                "especializado em:"
            ),
        )
        self._build_section(container, 1, 0, "3. O documento a ser analisado é:", "document", self.DOCUMENT_OPTIONS)
        self._build_section(container, 2, 0, "4. Faça um:", "report", self.REPORT_OPTIONS)
        self._build_section(container, 3, 0, "5. Opinião:", "opinion", self.OPINION_OPTIONS)

        additional = ttk.LabelFrame(container, text="Orientações adicionais para a IA", padding=10)
        additional.grid(row=4, column=0, columnspan=2, sticky="nsew", pady=(10, 0))
        additional.columnconfigure(0, weight=1)
        additional.rowconfigure(0, weight=1)
        self.additional_text = ScrolledText(additional, wrap="word", height=8, font=("Segoe UI", 10))
        self.additional_text.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        ttk.Button(additional, text="Importar JSON", command=self._import_json).grid(row=1, column=0, sticky="w")

        save_frame = ttk.Frame(container)
        save_frame.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        save_frame.columnconfigure(2, weight=1)
        ttk.Checkbutton(save_frame, text="Salvar como prompt do sistema", variable=self.save_as_system_var).grid(
            row=0, column=0, sticky="w", padx=(0, 12)
        )
        ttk.Label(save_frame, text="Nome").grid(row=0, column=1, sticky="e", padx=(0, 8))
        ttk.Entry(save_frame, textvariable=self.name_var).grid(row=0, column=2, sticky="ew")

        actions = ttk.Frame(container)
        actions.grid(row=6, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(actions, text="Cancelar", command=self._cancel).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(actions, text="Aplicar", command=self._apply).grid(row=0, column=1)

        self.window.bind("<Escape>", lambda _: self._cancel())
        self.window.bind("<Control-Return>", lambda _: self._apply())

    def _build_section(
        self,
        parent: ttk.Frame,
        row: int,
        column: int,
        title: str,
        key: str,
        options: list[str],
        rowspan: int = 1,
        description: str | None = None,
    ) -> None:
        frame = ttk.LabelFrame(parent, text=title, padding=10)
        frame.grid(
            row=row,
            column=column,
            rowspan=rowspan,
            sticky="nsew",
            padx=(0, 8) if column == 0 else (8, 0),
            pady=(0, 10),
        )
        frame.columnconfigure(0, weight=1)
        var = tk.StringVar(value=self.UNSELECTED_VALUE)
        start_row = 0
        if description:
            ttk.Label(frame, text=description, wraplength=500, justify="left").grid(
                row=0,
                column=0,
                sticky="ew",
                pady=(0, 8),
            )
            start_row = 1
        for index, option in enumerate(options):
            tk.Radiobutton(
                frame,
                text=option,
                variable=var,
                value=option,
                wraplength=420,
                justify="left",
                anchor="w",
                highlightthickness=0,
            ).grid(
                row=start_row + index, column=0, sticky="w", pady=2
            )
        self.option_vars[key] = var

    def show(self) -> dict[str, str | bool] | None:
        self.parent.wait_window(self.window)
        return self.result

    def _import_json(self) -> None:
        selected = filedialog.askopenfilename(
            title="Importar orientações adicionais em JSON",
            parent=self.window,
            filetypes=[("Arquivos JSON", "*.json"), ("Todos os arquivos", "*.*")],
        )
        if not selected:
            return
        try:
            raw_text = Path(selected).read_text(encoding="utf-8-sig")
            try:
                loaded = json.loads(raw_text)
                imported_text = json.dumps(loaded, ensure_ascii=False, indent=2)
            except json.JSONDecodeError:
                imported_text = raw_text
        except Exception as exc:  # noqa: BLE001 - surfaced to user
            messagebox.showerror(APP_TITLE, f"Não foi possível importar o JSON: {exc}", parent=self.window)
            return
        if self.additional_text.get("1.0", "end").strip():
            self.additional_text.insert("end", "\n\n")
        self.additional_text.insert("end", imported_text)

    def _apply(self) -> None:
        name = self.name_var.get().strip() or "Prompt do Assistente"
        content = self._build_prompt()
        self.result = {
            "name": name,
            "content": content,
            "save_as_system": self.save_as_system_var.get(),
        }
        self.window.destroy()

    def _selected_options(self, key: str) -> list[str]:
        selected = self.option_vars[key].get().strip()
        if selected == self.UNSELECTED_VALUE:
            return []
        return [selected] if selected else []

    @staticmethod
    def _format_options(options: list[str]) -> str:
        if not options:
            return "- não especificado"
        return "\n".join(f"- {option}" for option in options)

    def _build_prompt(self) -> str:
        roles = self._selected_options("role")
        expertise = self._selected_options("expertise")
        documents = self._selected_options("document")
        reports = self._selected_options("report")
        opinions = self._selected_options("opinion")
        additional = self.additional_text.get("1.0", "end").strip()
        instruction_lines = self._instruction_lines(roles, documents, reports)

        lines = [
            "Analise os documentos anexados e produza a resposta conforme as opções abaixo.",
            "",
            "Você é um:",
            self._format_options(roles),
            "",
            "O papel da inteligência artificial indicado no item anterior deverá contar com conhecimento especializado em:",
            self._format_options(expertise),
            "",
            "O documento a ser analisado é:",
            self._format_options(documents),
            "",
            "Faça um:",
            self._format_options(reports),
            "",
            "Opinião:",
            self._format_options(opinions),
        ]
        if additional:
            lines.extend(
                [
                    "",
                    "Orientações adicionais para a IA:",
                    additional,
                ]
            )
        lines.extend(
            [
                "",
                "Instruções obrigatórias:",
                *instruction_lines,
            ]
        )
        return "\n".join(lines).strip()

    def _instruction_lines(self, roles: list[str], documents: list[str], reports: list[str]) -> list[str]:
        instruction_items = [
            ("always", "Use somente informações localizadas nos documentos anexados ou nas orientações acima."),
            ("always", "Não invente fatos, datas, nomes, valores, fundamentos ou movimentações processuais."),
            (
                "admin_process_no_value_judgment",
                "A inteligência artificial não deverá emitir Juízo de valor ou analisar sobre erros ou acertos da autoridade administrativa ou do interessado.",
            ),
            ("not_found", "Quando uma informação relevante não estiver localizada, registre expressamente: não localizado."),
            (
                "differentiate",
                "Diferencie fatos, pedidos, fundamentos jurídicos, provas/documentos, atos processuais e conclusões.",
            ),
            ("always", "Preserve linguagem técnica, objetiva e formal, em português do Brasil."),
            (
                "always",
                "Se houver múltiplos documentos ou peças, indique a origem de cada informação sempre que possível.",
            ),
        ]
        instructions = []
        for kind, instruction in instruction_items:
            if kind == "admin_process_no_value_judgment" and not self._should_include_admin_process_instruction(
                documents
            ):
                continue
            if kind == "not_found" and self._should_omit_not_found_instruction(roles, documents, reports):
                continue
            if kind == "differentiate" and not self._should_include_differentiate_instruction(documents):
                continue
            instructions.append(instruction)
        return [f"{index}. {instruction}" for index, instruction in enumerate(instructions, start=1)]

    def _should_include_admin_process_instruction(self, documents: list[str]) -> bool:
        document = documents[0] if documents else ""
        return self._same_option(document, "processo administrativo")

    def _should_omit_not_found_instruction(
        self,
        roles: list[str],
        documents: list[str],
        reports: list[str],
    ) -> bool:
        role = roles[0] if roles else ""
        document = documents[0] if documents else ""
        report = reports[0] if reports else ""

        is_regulatory_specialist = self._same_option(role, "especialista de Agência Reguladora")
        is_single_or_admin_document = document.casefold().startswith("documento único") or self._same_option(
            document,
            "processo administrativo",
        )
        is_objective_report = self._same_option(report, "Relatório objetivo imparcial") or self._same_option(
            report,
            "Relatório e análise administrativa e jurídica objetiva",
        )
        return is_regulatory_specialist and is_single_or_admin_document and is_objective_report

    def _should_include_differentiate_instruction(self, documents: list[str]) -> bool:
        document = documents[0] if documents else ""
        return (
            document.casefold().startswith("documento único")
            or self._same_option(document, "processo judicial do Eproc")
            or self._same_option(document, "processo judicial do PJe")
        )

    @staticmethod
    def _same_option(left: str, right: str) -> bool:
        return left.strip().casefold() == right.strip().casefold()

    def _cancel(self) -> None:
        self.result = None
        self.window.destroy()


class PromptEditor:
    def __init__(self, parent: tk.Tk, title: str, prompt: Prompt | None = None):
        self.parent = parent
        self.prompt = prompt
        self.result: dict[str, str] | None = None

        self.window = tk.Toplevel(parent)
        self.window.title(title)
        self.window.geometry("680x430")
        self.window.minsize(580, 360)
        self.window.transient(parent)
        self.window.grab_set()
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(1, weight=1)

        container = ttk.Frame(self.window, padding=14)
        container.grid(row=0, column=0, sticky="nsew")
        container.columnconfigure(0, weight=1)
        container.rowconfigure(3, weight=1)

        ttk.Label(container, text="Nome").grid(row=0, column=0, sticky="w")
        self.name_var = tk.StringVar(value=prompt.name if prompt else "")
        ttk.Entry(container, textvariable=self.name_var).grid(row=1, column=0, sticky="ew", pady=(4, 12))

        ttk.Label(container, text="Texto do prompt").grid(row=2, column=0, sticky="w")
        self.content_text = ScrolledText(container, wrap="word", height=12, font=("Segoe UI", 10))
        self.content_text.grid(row=3, column=0, sticky="nsew", pady=(4, 12))
        if prompt:
            self.content_text.insert("1.0", prompt.content)

        actions = ttk.Frame(container)
        actions.grid(row=4, column=0, sticky="e")
        ttk.Button(actions, text="Cancelar", command=self._cancel).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(actions, text="Salvar", command=self._save).grid(row=0, column=1)

        self.window.bind("<Escape>", lambda _: self._cancel())
        self.window.bind("<Control-s>", lambda _: self._save())

    def show(self) -> dict[str, str] | None:
        self.parent.wait_window(self.window)
        return self.result

    def _save(self) -> None:
        name = self.name_var.get().strip()
        content = self.content_text.get("1.0", "end").strip()
        if not name:
            messagebox.showwarning(APP_TITLE, "Informe o nome do prompt.", parent=self.window)
            return
        if not content:
            messagebox.showwarning(APP_TITLE, "Informe o texto do prompt.", parent=self.window)
            return
        self.result = {"name": name, "content": content}
        self.window.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.window.destroy()


def main() -> None:
    _initialize_tcl_runtime()
    root = tk.Tk()
    app = ResumatorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
