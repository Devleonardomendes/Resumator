from __future__ import annotations

import unittest
from pathlib import Path

from resumator import ui


class FakeVar:
    def __init__(self, value: object) -> None:
        self.value = value

    def get(self) -> object:
        return self.value

    def set(self, value: object) -> None:
        self.value = value


class FakeWidget:
    def __init__(self) -> None:
        self.options: dict[str, object] = {}

    def configure(self, **kwargs: object) -> None:
        self.options.update(kwargs)


class FakeText:
    def __init__(self, value: str) -> None:
        self.value = value

    def get(self, _start: str, _end: str) -> str:
        return self.value


class AssistantOptionPolicyTests(unittest.TestCase):
    def test_only_copilot_and_gemini_lock_submit(self) -> None:
        for assistant_key in ("copilot", "gemini"):
            with self.subTest(assistant=assistant_key):
                self.assertFalse(ui._assistant_allows_submit(assistant_key))

        for assistant_key in ("chatgpt", "lmstudio_desktop", "deepseek"):
            with self.subTest(assistant=assistant_key):
                self.assertTrue(ui._assistant_allows_submit(assistant_key))

    def test_multi_pdf_attachment_defaults_off_only_for_copilot_and_gemini(self) -> None:
        for assistant_key in ("copilot", "gemini"):
            self.assertFalse(ui._automatic_attachment_defaults_off(assistant_key, 1))
            self.assertTrue(ui._automatic_attachment_defaults_off(assistant_key, 2))
            self.assertTrue(ui._automatic_attachment_defaults_off(assistant_key, 10))

        self.assertFalse(ui._automatic_attachment_defaults_off("chatgpt", 2))

    def test_selecting_gemini_with_multiple_pdfs_turns_attachment_default_off(self) -> None:
        app = object.__new__(ui.ResumatorApp)
        app.pdf_paths = [Path("one.pdf"), Path("two.pdf")]
        app.delivery_mode_var = FakeVar(ui.DELIVERY_DOCX)  # type: ignore[assignment]
        app.response_mode_var = FakeVar(ui.RESPONSE_TEXT_AND_DOCX)  # type: ignore[assignment]
        app.attach_var = FakeVar(True)  # type: ignore[assignment]
        app.submit_var = FakeVar(True)  # type: ignore[assignment]

        app._apply_default_modes_for_assistant("gemini")

        self.assertFalse(app.attach_var.get())
        self.assertFalse(app.submit_var.get())
        self.assertEqual(app.delivery_mode_var.get(), ui.DELIVERY_TEXT)
        self.assertEqual(app.response_mode_var.get(), ui.RESPONSE_TEXT_ONLY)

    def test_selecting_copilot_with_one_pdf_preserves_attachment_choice(self) -> None:
        app = object.__new__(ui.ResumatorApp)
        app.pdf_paths = [Path("one.pdf")]
        app.delivery_mode_var = FakeVar(ui.DELIVERY_DOCX)  # type: ignore[assignment]
        app.response_mode_var = FakeVar(ui.RESPONSE_TEXT_AND_DOCX)  # type: ignore[assignment]
        app.attach_var = FakeVar(True)  # type: ignore[assignment]
        app.submit_var = FakeVar(True)  # type: ignore[assignment]

        app._apply_default_modes_for_assistant("copilot")

        self.assertTrue(app.attach_var.get())

    def test_refresh_locks_submit_but_preserves_manual_attachment_choice(self) -> None:
        app = object.__new__(ui.ResumatorApp)
        app.pdf_paths = [Path("one.pdf"), Path("two.pdf")]
        app.assistant_var = FakeVar("copilot")  # type: ignore[assignment]
        app.attach_var = FakeVar(True)  # type: ignore[assignment]
        app.submit_var = FakeVar(True)  # type: ignore[assignment]
        app.send_button = FakeWidget()  # type: ignore[assignment]
        app.attach_check = FakeWidget()  # type: ignore[assignment]
        app.submit_check = FakeWidget()  # type: ignore[assignment]
        app.ignore_time_limit_check = FakeWidget()  # type: ignore[assignment]
        app._reset_assistant_if_prerequisites_missing = lambda: False  # type: ignore[method-assign]
        app._refresh_assistant_radio_states = lambda: None  # type: ignore[method-assign]
        app._refresh_delivery_controls = lambda _assistant: None  # type: ignore[method-assign]
        app._refresh_response_mode_controls = lambda _assistant: None  # type: ignore[method-assign]
        app._refresh_pdf_controls = lambda _assistant=None: None  # type: ignore[method-assign]

        app._refresh_send_button()

        self.assertTrue(app.attach_var.get())
        self.assertEqual(app.attach_check.options["state"], "normal")
        self.assertFalse(app.submit_var.get())
        self.assertEqual(app.submit_check.options["state"], "disabled")
        self.assertFalse(app._effective_submit("copilot"))

    def test_session_modes_are_applied_after_pdf_rows_are_rendered(self) -> None:
        app = object.__new__(ui.ResumatorApp)
        app.process_number_var = FakeVar("")  # type: ignore[assignment]
        app.assistant_var = FakeVar("gemini")  # type: ignore[assignment]
        app.delivery_mode_var = FakeVar(ui.DELIVERY_TEXT)  # type: ignore[assignment]
        app.response_mode_var = FakeVar(ui.RESPONSE_TEXT_ONLY)  # type: ignore[assignment]
        app.attach_var = FakeVar(False)  # type: ignore[assignment]
        app.submit_var = FakeVar(False)  # type: ignore[assignment]
        app.ignore_time_limit_var = FakeVar(False)  # type: ignore[assignment]

        def render_pdf_rows() -> None:
            # Reproduce the control refresh that previously applied the old Gemini policy
            # while saved values had already been loaded.
            if app.assistant_var.get() == "gemini":
                app.delivery_mode_var.set(ui.DELIVERY_TEXT)
                app.response_mode_var.set(ui.RESPONSE_TEXT_ONLY)
                app.submit_var.set(False)

        app._render_pdf_rows = render_pdf_rows  # type: ignore[method-assign]
        app._set_response_text = lambda *_args: None  # type: ignore[method-assign]
        app._restore_session_prompt = lambda _payload: None  # type: ignore[method-assign]
        app._can_choose_assistant = lambda: True  # type: ignore[method-assign]
        app._refresh_send_button = lambda: None  # type: ignore[method-assign]

        app._apply_session_payload(
            {
                "process_number": "123",
                "assistant": "chatgpt",
                "delivery_mode": ui.DELIVERY_DOCX,
                "response_mode": ui.RESPONSE_TEXT_AND_DOCX,
                "attach_pdf": True,
                "submit": True,
                "ignore_time_limit": True,
                "pdf_paths": ["one.pdf"],
            }
        )

        self.assertEqual(app.assistant_var.get(), "chatgpt")
        self.assertEqual(app.delivery_mode_var.get(), ui.DELIVERY_DOCX)
        self.assertEqual(app.response_mode_var.get(), ui.RESPONSE_TEXT_AND_DOCX)
        self.assertTrue(app.attach_var.get())
        self.assertTrue(app.submit_var.get())
        self.assertTrue(app.ignore_time_limit_var.get())

    def test_restored_gemini_session_locks_stale_submit_and_preserves_manual_attach(self) -> None:
        app = object.__new__(ui.ResumatorApp)
        app.process_number_var = FakeVar("")  # type: ignore[assignment]
        app.assistant_var = FakeVar("none")  # type: ignore[assignment]
        app.delivery_mode_var = FakeVar(ui.DELIVERY_TEXT)  # type: ignore[assignment]
        app.response_mode_var = FakeVar(ui.RESPONSE_TEXT_ONLY)  # type: ignore[assignment]
        app.attach_var = FakeVar(False)  # type: ignore[assignment]
        app.submit_var = FakeVar(False)  # type: ignore[assignment]
        app.ignore_time_limit_var = FakeVar(False)  # type: ignore[assignment]
        app.send_button = FakeWidget()  # type: ignore[assignment]
        app.attach_check = FakeWidget()  # type: ignore[assignment]
        app.submit_check = FakeWidget()  # type: ignore[assignment]
        app.ignore_time_limit_check = FakeWidget()  # type: ignore[assignment]
        app._render_pdf_rows = lambda: None  # type: ignore[method-assign]
        app._set_response_text = lambda *_args: None  # type: ignore[method-assign]
        app._restore_session_prompt = lambda _payload: None  # type: ignore[method-assign]
        app._can_choose_assistant = lambda: True  # type: ignore[method-assign]
        app._reset_assistant_if_prerequisites_missing = lambda: False  # type: ignore[method-assign]
        app._refresh_assistant_radio_states = lambda: None  # type: ignore[method-assign]
        app._refresh_delivery_controls = lambda _assistant: None  # type: ignore[method-assign]
        app._refresh_response_mode_controls = lambda _assistant: None  # type: ignore[method-assign]
        app._refresh_pdf_controls = lambda _assistant=None: None  # type: ignore[method-assign]

        app._apply_session_payload(
            {
                "process_number": "123",
                "assistant": "gemini",
                "attach_pdf": True,
                "submit": True,
                "pdf_paths": ["one.pdf", "two.pdf"],
            }
        )

        self.assertEqual(app.assistant_var.get(), "gemini")
        self.assertTrue(app.attach_var.get())
        self.assertEqual(app.attach_check.options["state"], "normal")
        self.assertFalse(app.submit_var.get())
        self.assertEqual(app.submit_check.options["state"], "disabled")

    def test_session_payload_never_persists_submit_for_gemini(self) -> None:
        app = object.__new__(ui.ResumatorApp)
        app.transient_prompt_content = None
        app.transient_prompt_name = None
        app.process_number_var = FakeVar("123")  # type: ignore[assignment]
        app.selected_prompt_id = "prompt-id"
        app.pdf_paths = [Path("one.pdf")]
        app.assistant_var = FakeVar("gemini")  # type: ignore[assignment]
        app.delivery_mode_var = FakeVar(ui.DELIVERY_TEXT)  # type: ignore[assignment]
        app.response_mode_var = FakeVar(ui.RESPONSE_TEXT_ONLY)  # type: ignore[assignment]
        app.attach_var = FakeVar(True)  # type: ignore[assignment]
        app.submit_var = FakeVar(True)  # type: ignore[assignment]
        app.ignore_time_limit_var = FakeVar(False)  # type: ignore[assignment]
        app.response_text = FakeText("resposta")  # type: ignore[assignment]
        app.response_rich_html = ""
        app.last_output_path = None
        app.status_var = FakeVar("Pronto")  # type: ignore[assignment]

        payload = app._session_payload()

        self.assertFalse(payload["submit"])


if __name__ == "__main__":
    unittest.main()
