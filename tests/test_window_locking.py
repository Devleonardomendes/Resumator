from __future__ import annotations

import unittest
from unittest import mock

from resumator import chatgpt_desktop as desktop
from resumator import ui


class AssistantWindowStyleTests(unittest.TestCase):
    def test_apply_lock_maximizes_and_removes_resize_styles(self) -> None:
        original_style = 0x00CF0000
        expected_style = original_style & ~desktop.LOCKED_WINDOW_STYLE_MASK

        with (
            mock.patch.object(desktop, "_window_is_maximized", return_value=False),
            mock.patch.object(desktop, "_show_window_state") as show_window,
            mock.patch.object(desktop, "_get_window_style", side_effect=(original_style, expected_style)),
            mock.patch.object(desktop, "_set_window_style") as set_style,
            mock.patch.object(desktop, "_refresh_window_frame") as refresh_frame,
        ):
            desktop._apply_assistant_window_lock(123)

        show_window.assert_called_once_with(123, desktop.SW_MAXIMIZE)
        set_style.assert_called_once_with(123, expected_style)
        refresh_frame.assert_called_once_with(123)

    def test_dialog_activation_restores_without_registering_a_lock(self) -> None:
        foreground = mock.Mock()
        fake_win32gui = mock.Mock(SetForegroundWindow=foreground)

        with (
            mock.patch.object(desktop, "win32gui", fake_win32gui),
            mock.patch.object(desktop, "_lock_assistant_window_maximized") as lock_window,
            mock.patch.object(desktop, "_show_window_state") as show_window,
        ):
            desktop._activate_window(
                456,
                lock_maximized=False,
                restore_unlocked=True,
            )

        lock_window.assert_not_called()
        show_window.assert_called_once_with(456, desktop.SW_RESTORE)
        foreground.assert_called_once_with(456)

    def test_unlocked_activation_can_preserve_the_current_window_state(self) -> None:
        foreground = mock.Mock()
        fake_win32gui = mock.Mock(SetForegroundWindow=foreground)

        with (
            mock.patch.object(desktop, "win32gui", fake_win32gui),
            mock.patch.object(desktop, "_lock_assistant_window_maximized") as lock_window,
            mock.patch.object(desktop, "_show_window_state") as show_window,
        ):
            desktop._activate_window(456, lock_maximized=False, restore_unlocked=False)

        lock_window.assert_not_called()
        show_window.assert_not_called()
        foreground.assert_called_once_with(456)

    def test_assistant_target_defaults_to_preserving_the_current_window_state(self) -> None:
        target = desktop.AssistantTarget(hwnd=123, title="Assistente")

        with (
            mock.patch.object(desktop, "_activate_window") as activate_window,
            mock.patch.object(desktop, "_foreground_window_handle", return_value=123),
        ):
            desktop._activate_assistant_target(target)

        activate_window.assert_called_once_with(
            123,
            lock_maximized=False,
            restore_unlocked=False,
        )

    def test_file_dialog_uses_unlocked_activation(self) -> None:
        with (
            mock.patch.object(desktop, "_wait_for_file_dialog", return_value=789),
            mock.patch.object(desktop, "_set_clipboard_text"),
            mock.patch.object(desktop, "_window_text", return_value="Abrir"),
            mock.patch.object(desktop, "_activate_assistant_target") as activate,
            mock.patch.object(desktop, "_hotkey"),
            mock.patch.object(desktop, "_press"),
            mock.patch.object(desktop.time, "sleep"),
        ):
            selected = desktop._select_files_in_open_dialog([], 0.0)

        self.assertTrue(selected)
        self.assertEqual(activate.call_count, 2)
        for call in activate.call_args_list:
            self.assertFalse(call.kwargs["lock_maximized"])
            self.assertTrue(call.kwargs["restore_unlocked"])

    def test_release_restores_only_the_resize_bits_removed_by_resumator(self) -> None:
        original_style = 0x10000000 | desktop.LOCKED_WINDOW_STYLE_MASK
        current_style = 0x08000000
        expected_style = current_style | desktop.LOCKED_WINDOW_STYLE_MASK
        desktop._ASSISTANT_WINDOW_LOCKS_SHUTTING_DOWN = False
        desktop._LOCKED_ASSISTANT_WINDOWS.clear()
        desktop._ORIGINAL_ASSISTANT_WINDOW_STYLES.clear()
        desktop._LOCKED_ASSISTANT_WINDOWS[123] = 77
        desktop._ORIGINAL_ASSISTANT_WINDOW_STYLES[123] = original_style

        try:
            with (
                mock.patch.object(desktop, "_window_exists", return_value=True),
                mock.patch.object(desktop, "_window_process_id", return_value=77),
                mock.patch.object(desktop, "_get_window_style", side_effect=(current_style, expected_style)),
                mock.patch.object(desktop, "_set_window_style") as set_style,
                mock.patch.object(desktop, "_refresh_window_frame") as refresh_frame,
            ):
                desktop.release_assistant_window_locks()

            set_style.assert_called_once_with(123, expected_style)
            refresh_frame.assert_called_once_with(123)
            self.assertTrue(desktop._ASSISTANT_WINDOW_LOCKS_SHUTTING_DOWN)
            self.assertEqual(desktop._LOCKED_ASSISTANT_WINDOWS, {})
        finally:
            desktop._ASSISTANT_WINDOW_LOCKS_SHUTTING_DOWN = False
            desktop._LOCKED_ASSISTANT_WINDOWS.clear()
            desktop._ORIGINAL_ASSISTANT_WINDOW_STYLES.clear()

    def test_shutdown_flag_prevents_a_late_worker_from_relocking_a_window(self) -> None:
        desktop._ASSISTANT_WINDOW_LOCKS_SHUTTING_DOWN = True
        try:
            with (
                mock.patch.object(desktop, "IS_WINDOWS", True),
                mock.patch.object(desktop, "_window_exists") as window_exists,
                mock.patch.object(desktop, "_apply_assistant_window_lock") as apply_lock,
            ):
                desktop._lock_assistant_window_maximized(123)

            window_exists.assert_not_called()
            apply_lock.assert_not_called()
        finally:
            desktop._ASSISTANT_WINDOW_LOCKS_SHUTTING_DOWN = False


class AssistantWindowPolicyFlowTests(unittest.TestCase):
    def assert_state_preserving_activation(
        self,
        activation: mock.Mock,
        expected_target: desktop.AssistantTarget,
        expected_count: int = 1,
    ) -> None:
        self.assertEqual(activation.call_count, expected_count)
        for call in activation.call_args_list:
            self.assertEqual(call.args, (expected_target,))
            self.assertEqual(
                call.kwargs,
                {
                    "lock_maximized": False,
                    "restore_unlocked": False,
                },
            )

    def test_chatgpt_work_confirmation_preserves_window_state(self) -> None:
        assistant = desktop.ASSISTANTS["chatgpt"]
        target = desktop.AssistantTarget(hwnd=123, title="ChatGPT")

        with (
            mock.patch.object(desktop, "_ensure_chatgpt_work_preference", return_value=(True, "ok")),
            mock.patch.object(desktop, "find_assistant_windows", return_value=[]),
            mock.patch.object(desktop, "_activate_assistant_target") as activate,
            mock.patch.object(
                desktop,
                "_select_chatgpt_work_mode",
                return_value=(True, "ALREADY_WORK|modo confirmado"),
            ),
            mock.patch.object(desktop, "_log_automation"),
            mock.patch.object(desktop.time, "sleep"),
        ):
            result = desktop._ensure_chatgpt_work_target(assistant, target, [])

        self.assertEqual(result.title, "ChatGPT Work")
        self.assert_state_preserving_activation(activate, target, expected_count=2)

    def test_copilot_new_chat_preserves_window_state_after_refresh(self) -> None:
        assistant = desktop.ASSISTANTS["copilot"]
        target = desktop.AssistantTarget(hwnd=123, title="Microsoft 365 Copilot")
        refreshed = desktop.AssistantTarget(hwnd=456, title="Microsoft 365 Copilot")

        with (
            mock.patch.object(desktop, "_launch_assistant_urls", return_value=(True, None)),
            mock.patch.object(desktop, "_assistant_target_from_current_windows", return_value=refreshed),
            mock.patch.object(desktop, "_activate_assistant_target") as activate,
            mock.patch.object(desktop, "_invoke_uia_action", return_value=(False, "nao encontrado")),
            mock.patch.object(desktop, "_log_automation"),
            mock.patch.object(desktop.time, "sleep"),
        ):
            result = desktop._prepare_copilot_new_chat(assistant, target, [])

        self.assertIs(result, refreshed)
        self.assert_state_preserving_activation(activate, refreshed)

    def test_lmstudio_reopen_preserves_window_state(self) -> None:
        assistant = desktop.ASSISTANTS["lmstudio"]
        expected = desktop.AssistantTarget(
            hwnd=456,
            title="LM Studio",
            note="LM Studio reaberto no novo chat.",
        )

        with (
            mock.patch.object(desktop, "_launch_assistant", return_value=(True, 900)),
            mock.patch.object(desktop, "_wait_for_assistant_window", return_value=[(456, "LM Studio")]),
            mock.patch.object(desktop, "_activate_assistant_target") as activate,
            mock.patch.object(desktop, "_log_automation"),
        ):
            result, _ = desktop._open_lmstudio_after_state_update()

        self.assertEqual(result, expected)
        self.assertFalse(assistant.lock_window_maximized)
        self.assert_state_preserving_activation(activate, expected)


class AssistantWindowMatchingTests(unittest.TestCase):
    def test_gemini_requires_a_supported_browser_process(self) -> None:
        assistant = desktop.ASSISTANTS["gemini"]

        self.assertTrue(
            desktop._matches_assistant_window(
                "Google Gemini",
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                assistant,
            )
        )
        self.assertFalse(
            desktop._matches_assistant_window(
                "Relatorio Gemini - Word",
                r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE",
                assistant,
            )
        )
        self.assertFalse(
            desktop._matches_assistant_window(
                "Google Gemini",
                r"C:\Program Files\Google\Chrome\Application\chrome-helper.exe",
                assistant,
            )
        )
        self.assertFalse(
            desktop._matches_assistant_window(
                "",
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                assistant,
            )
        )

    def test_copilot_rejects_titled_dialogs_from_the_right_process(self) -> None:
        assistant = desktop.ASSISTANTS["copilot"]
        process_path = r"C:\Program Files\WindowsApps\Microsoft.OfficeHub.exe"

        self.assertTrue(desktop._matches_assistant_window("Microsoft 365 Copilot", process_path, assistant))
        self.assertFalse(desktop._matches_assistant_window("Abrir", process_path, assistant))


class AssistantWindowPolicyTests(unittest.TestCase):
    def test_every_assistant_opts_out_of_window_maximize_locking(self) -> None:
        for assistant_key in ("chatgpt", "copilot", "gemini", "lmstudio", "deepseek"):
            with self.subTest(assistant=assistant_key):
                self.assertFalse(desktop.ASSISTANTS[assistant_key].lock_window_maximized)

    def test_configured_gemini_activation_preserves_its_window_state(self) -> None:
        assistant = desktop.ASSISTANTS["gemini"]
        target = desktop.AssistantTarget(hwnd=123, title="Google Gemini")

        with mock.patch.object(desktop, "_activate_assistant_target") as activate:
            desktop._activate_configured_assistant_target(assistant, target)

        activate.assert_called_once_with(
            target,
            lock_maximized=False,
            restore_unlocked=False,
        )

    def test_configured_non_gemini_activation_preserves_its_window_state(self) -> None:
        assistant = desktop.ASSISTANTS["copilot"]
        target = desktop.AssistantTarget(hwnd=123, title="Microsoft 365 Copilot")

        with mock.patch.object(desktop, "_activate_assistant_target") as activate:
            desktop._activate_configured_assistant_target(assistant, target)

        activate.assert_called_once_with(
            target,
            lock_maximized=False,
            restore_unlocked=False,
        )


class ResumatorWindowLockTests(unittest.TestCase):
    class FakeWindow:
        def __init__(self) -> None:
            self.current_state = "normal"
            self.calls: list[tuple] = []
            self.idle_callbacks: list[object] = []
            self.bindings: dict[str, object] = {}

        def winfo_exists(self) -> bool:
            return True

        def state(self, value: str | None = None) -> str:
            if value is not None:
                self.calls.append(("state", value))
                self.current_state = value
            return self.current_state

        def resizable(self, width: bool, height: bool) -> None:
            self.calls.append(("resizable", width, height))

        def bind(self, event: str, callback: object, add: str | None = None) -> None:
            self.calls.append(("bind", event, add))
            self.bindings[event] = callback

        def after_idle(self, callback: object) -> str:
            self.calls.append(("after_idle",))
            self.idle_callbacks.append(callback)
            return "after-id"

    def test_tk_window_is_maximized_and_remaximized_after_restore(self) -> None:
        window = self.FakeWindow()

        ui._lock_tk_window_maximized(window)  # type: ignore[arg-type]

        self.assertEqual(window.calls[0], ("state", "zoomed"))
        self.assertEqual(window.calls[1], ("resizable", False, False))
        window.current_state = "normal"
        configure_callback = window.bindings["<Configure>"]
        configure_callback()  # type: ignore[operator]
        window.idle_callbacks[-1]()  # type: ignore[operator]
        self.assertEqual(window.current_state, "zoomed")
        self.assertIn(("resizable", False, False), window.calls)

    def test_main_window_opens_maximized_without_fullscreen_or_resize_lock(self) -> None:
        window = self.FakeWindow()

        ui._maximize_tk_window_on_open(window)  # type: ignore[arg-type]

        self.assertEqual(window.calls[0], ("state", "zoomed"))
        self.assertNotIn(("resizable", False, False), window.calls)
        self.assertFalse(any(call[0] == "bind" for call in window.calls))
        self.assertEqual(len(window.idle_callbacks), 1)

        window.current_state = "normal"
        window.idle_callbacks[0]()  # type: ignore[operator]
        self.assertEqual(window.current_state, "zoomed")


if __name__ == "__main__":
    unittest.main()
