from __future__ import annotations

import subprocess
import unittest
from unittest import mock

from resumator import chatgpt_desktop as desktop


class AssistantComposerConfigurationTests(unittest.TestCase):
    def test_only_copilot_and_gemini_require_explicit_composer_focus(self) -> None:
        self.assertTrue(desktop.ASSISTANTS["copilot"].composer_terms)
        self.assertTrue(desktop.ASSISTANTS["gemini"].composer_terms)

        for assistant_key in ("chatgpt", "deepseek", "lmstudio"):
            with self.subTest(assistant=assistant_key):
                self.assertEqual(desktop.ASSISTANTS[assistant_key].composer_terms, ())


class AssistantKeyboardFocusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.target = desktop.AssistantTarget(hwnd=123, title="Assistente")

    def test_pwa_already_in_foreground_is_not_reactivated(self) -> None:
        assistant = desktop.ASSISTANTS["copilot"]

        with (
            mock.patch.object(desktop, "_foreground_window_handle", return_value=123),
            mock.patch.object(desktop, "_activate_assistant_target") as activate,
            mock.patch.object(
                desktop,
                "_focus_assistant_composer",
                return_value=(True, "FOCUSED|campo confirmado"),
            ) as focus,
            mock.patch.object(desktop, "_log_automation"),
            mock.patch.object(desktop.time, "sleep"),
        ):
            desktop._activate_assistant_for_keyboard_input(assistant, self.target)

        activate.assert_not_called()
        focus.assert_called_once_with(123, assistant.composer_terms)

    def test_pwa_is_reactivated_if_another_window_took_foreground(self) -> None:
        assistant = desktop.ASSISTANTS["gemini"]

        with (
            mock.patch.object(desktop, "_foreground_window_handle", return_value=999),
            mock.patch.object(desktop, "_activate_assistant_target") as activate,
            mock.patch.object(
                desktop,
                "_focus_assistant_composer",
                return_value=(True, "FOCUSED|campo confirmado"),
            ),
            mock.patch.object(desktop, "_log_automation"),
            mock.patch.object(desktop.time, "sleep"),
        ):
            desktop._activate_assistant_for_keyboard_input(assistant, self.target)

        activate.assert_called_once_with(self.target)

    def test_pwa_focus_failure_stops_keyboard_input(self) -> None:
        assistant = desktop.ASSISTANTS["copilot"]

        with (
            mock.patch.object(desktop, "_foreground_window_handle", return_value=123),
            mock.patch.object(
                desktop,
                "_focus_assistant_composer",
                return_value=(False, "NOT_FOUND|campo ausente"),
            ),
            mock.patch.object(desktop, "_log_automation"),
        ):
            with self.assertRaises(desktop.AutomationError):
                desktop._activate_assistant_for_keyboard_input(assistant, self.target)

    def test_other_assistants_keep_the_original_activation_path(self) -> None:
        assistant = desktop.ASSISTANTS["deepseek"]

        with (
            mock.patch.object(desktop, "_activate_assistant_target") as activate,
            mock.patch.object(desktop, "_focus_assistant_composer") as focus,
        ):
            desktop._activate_assistant_for_keyboard_input(assistant, self.target)

        activate.assert_called_once_with(self.target)
        focus.assert_not_called()


class AssistantSendFocusFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.target = desktop.AssistantTarget(hwnd=123, title="Assistente")

    def _run_send(self, assistant_key: str) -> tuple[desktop.AutomationResult, list[str]]:
        events: list[str] = []

        with (
            mock.patch.object(desktop, "IS_WINDOWS", True),
            mock.patch.object(desktop, "_resolve_assistant_target", return_value=self.target),
            mock.patch.object(desktop, "_activate_assistant_target"),
            mock.patch.object(desktop, "_prepare_assistant_for_send", return_value=self.target),
            mock.patch.object(desktop, "_log_automation"),
            mock.patch.object(desktop.time, "sleep"),
            mock.patch.object(
                desktop,
                "_activate_assistant_for_keyboard_input",
                side_effect=lambda *_: events.append("focus"),
            ) as keyboard_focus,
            mock.patch.object(
                desktop,
                "_set_clipboard_text",
                side_effect=lambda *_: events.append("clipboard"),
            ),
            mock.patch.object(
                desktop,
                "_hotkey",
                side_effect=lambda *_: events.append("paste"),
            ),
            mock.patch.object(
                desktop,
                "_press",
                side_effect=lambda *_: events.append("enter"),
            ),
        ):
            result = desktop.send_to_desktop_assistant(
                assistant_key,
                "texto do teste",
                None,
                attach_pdf=False,
                submit=True,
            )

        self.assertEqual(keyboard_focus.call_count, 2)
        return result, events

    def test_copilot_focuses_before_paste_and_again_before_enter(self) -> None:
        result, events = self._run_send("copilot")

        self.assertTrue(result.ok)
        self.assertEqual(events, ["focus", "clipboard", "paste", "focus", "enter"])

    def test_gemini_focuses_before_paste_and_again_before_enter(self) -> None:
        result, events = self._run_send("gemini")

        self.assertTrue(result.ok)
        self.assertEqual(events, ["focus", "clipboard", "paste", "focus", "enter"])

    def test_focus_failure_stops_before_clipboard_paste_and_enter(self) -> None:
        assistant = desktop.ASSISTANTS["gemini"]
        error = desktop.AutomationError("campo de mensagem nao confirmado")

        with (
            mock.patch.object(desktop, "IS_WINDOWS", True),
            mock.patch.object(desktop, "_resolve_assistant_target", return_value=self.target),
            mock.patch.object(desktop, "_activate_assistant_target"),
            mock.patch.object(desktop, "_prepare_assistant_for_send", return_value=self.target),
            mock.patch.object(desktop, "_log_automation"),
            mock.patch.object(desktop.time, "sleep"),
            mock.patch.object(
                desktop,
                "_activate_assistant_for_keyboard_input",
                side_effect=error,
            ) as keyboard_focus,
            mock.patch.object(desktop, "_set_clipboard_text") as clipboard,
            mock.patch.object(desktop, "_hotkey") as hotkey,
            mock.patch.object(desktop, "_press") as press,
        ):
            result = desktop.send_to_desktop_assistant(
                assistant.key,
                "texto confidencial",
                None,
                attach_pdf=False,
                submit=True,
            )

        self.assertFalse(result.ok)
        keyboard_focus.assert_called_once_with(assistant, self.target)
        clipboard.assert_not_called()
        hotkey.assert_not_called()
        press.assert_not_called()


class ComposerUiAutomationResultTests(unittest.TestCase):
    def test_focused_status_is_success(self) -> None:
        completed = subprocess.CompletedProcess([], 0, "FOCUSED|score=320|name=Ask Gemini", "")

        with mock.patch.object(desktop.subprocess, "run", return_value=completed):
            ok, detail = desktop._focus_assistant_composer(123, ("ask gemini",), 0.5)

        self.assertTrue(ok)
        self.assertTrue(detail.startswith("FOCUSED|"))

    def test_not_found_status_is_failure(self) -> None:
        completed = subprocess.CompletedProcess([], 2, "NOT_FOUND|campo ausente", "")

        with mock.patch.object(desktop.subprocess, "run", return_value=completed):
            ok, detail = desktop._focus_assistant_composer(123, ("ask copilot",), 0.5)

        self.assertFalse(ok)
        self.assertEqual(detail, "NOT_FOUND|campo ausente")


if __name__ == "__main__":
    unittest.main()
