from __future__ import annotations

import unittest
import tempfile
import tomllib
from pathlib import Path
from unittest import mock

from resumator import chatgpt_desktop as desktop


class ChatGPTWorkConfigurationTests(unittest.TestCase):
    def test_chatgpt_uses_new_app_aumid_and_requires_visible_window(self) -> None:
        assistant = desktop.ASSISTANTS["chatgpt"]

        self.assertEqual(desktop.CHATGPT_WORK_AUMID, "OpenAI.Codex_2p2nqsd0c76g0!App")
        self.assertEqual(
            assistant.launch_commands,
            ((desktop.WINDOWS_EXPLORER_PATH, f"shell:AppsFolder\\{desktop.CHATGPT_WORK_AUMID}"),),
        )
        self.assertTrue(desktop.WINDOWS_EXPLORER_PATH.casefold().endswith(r"\windows\explorer.exe"))
        self.assertTrue(assistant.require_visible_window)
        self.assertEqual(assistant.launch_urls, ())

    def test_work_preference_updates_only_desktop_mode_in_existing_config(self) -> None:
        source = (
            'model = "gpt-5"\n'
            '# comentario que deve ser preservado\n'
            '[desktop]\n'
            'other_setting = true\n'
            'conversationDetailMode = "CODE" # manter comentario inline\n'
            '[features]\n'
            'sandbox = true\n'
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / ".codex" / "config.toml"
            config_path.parent.mkdir(parents=True)
            config_path.write_text(source, encoding="utf-8")

            with mock.patch.object(desktop, "_chatgpt_config_path", return_value=config_path):
                ok, _ = desktop._ensure_chatgpt_work_preference()

            updated = config_path.read_text(encoding="utf-8")

        parsed = tomllib.loads(updated)
        self.assertTrue(ok)
        self.assertEqual(parsed["model"], "gpt-5")
        self.assertTrue(parsed["desktop"]["other_setting"])
        self.assertEqual(
            parsed["desktop"][desktop.CHATGPT_WORK_MODE_KEY],
            desktop.CHATGPT_WORK_MODE_VALUE,
        )
        self.assertTrue(parsed["features"]["sandbox"])
        self.assertIn("# comentario que deve ser preservado", updated)
        self.assertIn("# manter comentario inline", updated)

    def test_work_preference_preserves_comment_on_desktop_header(self) -> None:
        source = (
            '[desktop] # configuracao da interface\n'
            'conversationDetailMode = "STEPS_COMMANDS"\n'
            'localeOverride = "pt-BR"\n'
        )

        updated, changed = desktop._chatgpt_work_config_text(source)
        parsed = tomllib.loads(updated)

        self.assertTrue(changed)
        self.assertEqual(parsed["desktop"][desktop.CHATGPT_WORK_MODE_KEY], "STEPS_PROSE")
        self.assertEqual(parsed["desktop"]["localeOverride"], "pt-BR")
        self.assertIn("[desktop] # configuracao da interface", updated)

    def test_work_preference_is_persisted_before_new_app_is_launched(self) -> None:
        assistant = desktop.ASSISTANTS["chatgpt"]
        events: list[str] = []

        def ensure_preference() -> tuple[bool, str]:
            events.append("preference")
            return True, "preferencia confirmada"

        def launch(_assistant: desktop.DesktopAssistant) -> tuple[bool, int | None]:
            events.append("launch")
            return True, None

        with (
            mock.patch.object(
                desktop,
                "_ensure_chatgpt_work_preference",
                side_effect=ensure_preference,
            ),
            mock.patch.object(desktop, "_launch_assistant", side_effect=launch),
            mock.patch.object(
                desktop,
                "find_assistant_windows",
                return_value=[(123, "ChatGPT")],
            ),
            mock.patch.object(desktop, "_foreground_window_handle", return_value=123),
            mock.patch.object(desktop.time, "monotonic", side_effect=(0.0, 0.1)),
            mock.patch.object(desktop, "_log_automation"),
        ):
            target = desktop._resolve_chatgpt_work_target(assistant)

        self.assertEqual(events, ["preference", "launch"])
        self.assertIsNotNone(target)
        assert target is not None
        self.assertEqual((target.hwnd, target.title), (123, "ChatGPT"))


class ChatGPTWorkWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assistant = desktop.ASSISTANTS["chatgpt"]
        self.chatgpt_process = (
            r"C:\Program Files\WindowsApps\OpenAI.Codex_1.0.0.0_x64__2p2nqsd0c76g0"
            r"\app\ChatGPT.exe"
        )

    def test_filter_accepts_only_chatgpt_surfaces_from_chatgpt_process(self) -> None:
        for title in ("ChatGPT", "ChatGPT Work"):
            with self.subTest(title=title):
                self.assertTrue(
                    desktop._matches_assistant_window(title, self.chatgpt_process, self.assistant)
                )

        for title in ("Dictation", "Codex", "Debug", "Pet Surface", ""):
            with self.subTest(title=title):
                self.assertFalse(
                    desktop._matches_assistant_window(title, self.chatgpt_process, self.assistant)
                )

    def test_sort_prefers_foreground_even_when_another_window_is_larger(self) -> None:
        windows = [(101, "ChatGPT"), (202, "ChatGPT")]
        areas = {101: 1_500_000, 202: 900_000}

        with (
            mock.patch.object(desktop, "_foreground_window_handle", return_value=202),
            mock.patch.object(desktop, "_window_area", side_effect=areas.__getitem__),
        ):
            ordered = desktop._sort_assistant_windows(windows, self.assistant)

        self.assertEqual(ordered, [(202, "ChatGPT"), (101, "ChatGPT")])

    def test_sort_prefers_larger_main_window_when_none_is_foreground(self) -> None:
        windows = [(101, "ChatGPT"), (202, "ChatGPT")]
        areas = {101: 640 * 480, 202: 1280 * 820}

        with (
            mock.patch.object(desktop, "_foreground_window_handle", return_value=999),
            mock.patch.object(desktop, "_window_area", side_effect=areas.__getitem__),
        ):
            ordered = desktop._sort_assistant_windows(windows, self.assistant)

        self.assertEqual(ordered, [(202, "ChatGPT"), (101, "ChatGPT")])


class ChatGPTWorkFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assistant = desktop.ASSISTANTS["chatgpt"]
        self.target = desktop.AssistantTarget(hwnd=123, title="ChatGPT")

    def test_open_fails_when_work_selection_is_not_confirmed(self) -> None:
        error = desktop.AutomationError("ChatGPT Work nao confirmado")

        with (
            mock.patch.object(desktop, "IS_WINDOWS", True),
            mock.patch.object(desktop, "_log_automation"),
            mock.patch.object(desktop, "_ensure_chatgpt_work_preference"),
            mock.patch.object(desktop, "_resolve_assistant_target", return_value=self.target),
            mock.patch.object(desktop, "_activate_assistant_target"),
            mock.patch.object(
                desktop,
                "_ensure_chatgpt_work_target",
                side_effect=error,
            ) as ensure_work,
        ):
            result = desktop.open_desktop_assistant("chatgpt")

        self.assertFalse(result.ok)
        ensure_work.assert_called_once()
        args = ensure_work.call_args.args
        self.assertIs(args[0], self.assistant)
        self.assertEqual(args[1], self.target)

    def test_send_stops_before_clipboard_when_work_selection_is_not_confirmed(self) -> None:
        error = desktop.AutomationError("ChatGPT Work nao confirmado")

        with (
            mock.patch.object(desktop, "IS_WINDOWS", True),
            mock.patch.object(desktop, "_log_automation"),
            mock.patch.object(desktop, "_resolve_assistant_target", return_value=self.target),
            mock.patch.object(desktop, "_activate_assistant_target"),
            mock.patch.object(desktop.time, "sleep"),
            mock.patch.object(
                desktop,
                "_ensure_chatgpt_work_target",
                side_effect=error,
            ) as ensure_work,
            mock.patch.object(desktop, "_set_clipboard_text") as set_clipboard,
            mock.patch.object(desktop, "_press") as press,
        ):
            result = desktop.send_to_desktop_assistant(
                "chatgpt",
                "texto confidencial",
                None,
                attach_pdf=False,
                submit=True,
            )

        self.assertFalse(result.ok)
        ensure_work.assert_called_once()
        args = ensure_work.call_args.args
        self.assertIs(args[0], self.assistant)
        self.assertEqual(args[1], self.target)
        set_clipboard.assert_not_called()
        press.assert_not_called()

    def test_activation_fails_when_foreground_does_not_confirm_target(self) -> None:
        with (
            mock.patch.object(desktop, "_activate_window"),
            mock.patch.object(desktop, "_foreground_window_handle", return_value=999),
            mock.patch.object(desktop.time, "sleep"),
        ):
            with self.assertRaises(desktop.AutomationError):
                desktop._activate_assistant_target(self.target)


if __name__ == "__main__":
    unittest.main()
