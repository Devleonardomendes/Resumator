from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from resumator import chatgpt_desktop as desktop


class AssistantShortcutDiscoveryTests(unittest.TestCase):
    def test_finds_gemini_below_a_localized_shortcut_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            expected = root / "apps do Chrome" / "Gemini.lnk"
            expected.parent.mkdir()
            expected.write_bytes(b"shortcut")

            with mock.patch.object(desktop, "_windows_shortcut_roots", return_value=[root]):
                candidates = desktop._candidate_shortcut_paths(("Gemini.lnk", "Google Gemini.lnk"))

        self.assertEqual(candidates, [expected])

    def test_shortcut_matching_is_exact_and_case_insensitive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            expected = root / "qualquer pasta" / "gOoGlE GeMiNi.LNK"
            rejected = root / "qualquer pasta" / "Gemini Notes.lnk"
            expected.parent.mkdir()
            expected.write_bytes(b"shortcut")
            rejected.write_bytes(b"other shortcut")

            with mock.patch.object(desktop, "_windows_shortcut_roots", return_value=[root]):
                candidates = desktop._candidate_shortcut_paths(("Gemini.lnk", "Google Gemini.lnk"))

        self.assertEqual(candidates, [expected])


class AssistantShortcutLaunchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assistant = desktop.DesktopAssistant(
            key="gemini-test",
            display_name="Gemini Test",
            window_keywords=("gemini",),
            shortcut_names=("Gemini.lnk",),
            launch_urls=("https://gemini.example/app",),
        )

    def test_shortcut_is_launched_before_the_url_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            shortcut = Path(temporary_directory) / "Gemini.lnk"
            shortcut.write_bytes(b"shortcut")

            with (
                mock.patch.object(desktop, "_candidate_launch_paths", return_value=[]),
                mock.patch.object(desktop, "_candidate_shortcut_paths", return_value=[shortcut]),
                mock.patch.object(desktop.os, "startfile") as startfile,
                mock.patch.object(desktop, "_launch_assistant_urls") as launch_urls,
                mock.patch.object(desktop, "_log_automation"),
            ):
                launched, launched_pid = desktop._launch_assistant(self.assistant)

        self.assertTrue(launched)
        self.assertIsNone(launched_pid)
        startfile.assert_called_once_with(str(shortcut))
        launch_urls.assert_not_called()

    def test_url_remains_the_fallback_when_no_shortcut_exists(self) -> None:
        with (
            mock.patch.object(desktop, "_candidate_launch_paths", return_value=[]),
            mock.patch.object(desktop, "_candidate_shortcut_paths", return_value=[]),
            mock.patch.object(desktop, "_launch_assistant_urls", return_value=(True, None)) as launch_urls,
        ):
            launched, launched_pid = desktop._launch_assistant(self.assistant)

        self.assertTrue(launched)
        self.assertIsNone(launched_pid)
        launch_urls.assert_called_once_with(self.assistant)


class GeminiShortcutIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assistant = desktop.ASSISTANTS["gemini"]
        self.shortcut = Path("Gemini.lnk")

    def test_accepts_both_official_chromium_gemini_app_ids(self) -> None:
        for app_id in desktop.GEMINI_CHROMIUM_APP_IDS:
            with self.subTest(app_id=app_id), mock.patch.object(
                desktop,
                "_windows_shortcut_metadata",
                return_value=(
                    r"C:\Program Files\Google\Chrome\Application\chrome_proxy.exe",
                    f"--profile-directory=Default --app-id={app_id}",
                ),
            ):
                self.assertTrue(desktop._shortcut_matches_assistant(self.shortcut, self.assistant))

    def test_rejects_invalid_or_unrelated_gemini_shortcuts(self) -> None:
        cases = (
            None,
            (r"C:\Windows\System32\notepad.exe", "--app-id=gdfaincndogidkdcdkhapmbffkckdkhn"),
            (r"C:\Program Files\Google\Chrome\Application\chrome_proxy.exe", "--app-id=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"),
        )
        for metadata in cases:
            with self.subTest(metadata=metadata), mock.patch.object(
                desktop,
                "_windows_shortcut_metadata",
                return_value=metadata,
            ):
                self.assertFalse(desktop._shortcut_matches_assistant(self.shortcut, self.assistant))

    def test_resolve_prefers_installed_gemini_before_existing_web_windows(self) -> None:
        with (
            mock.patch.object(desktop, "_launch_installed_assistant", return_value=(True, None)) as launch,
            mock.patch.object(
                desktop,
                "find_assistant_windows",
                side_effect=[
                    [(111, "Google Gemini - Google Chrome")],
                    [(111, "Google Gemini - Google Chrome"), (123, "Google Gemini")],
                ],
            ),
            mock.patch.object(desktop, "_cached_preferred_assistant_target", return_value=None),
            mock.patch.object(
                desktop,
                "_window_matches_installed_assistant",
                side_effect=lambda hwnd, _assistant: hwnd == 123,
            ),
            mock.patch.object(desktop, "_remember_preferred_assistant_target") as remember,
        ):
            target, attempted = desktop._resolve_preferred_installed_target(self.assistant)

        self.assertTrue(attempted)
        self.assertIsNotNone(target)
        assert target is not None
        self.assertEqual(target.hwnd, 123)
        launch.assert_called_once_with(self.assistant)
        remember.assert_called_once_with(self.assistant, target)

    def test_cached_installed_gemini_window_is_reused_without_relaunch(self) -> None:
        desktop._PREFERRED_ASSISTANT_WINDOWS.clear()
        desktop._PREFERRED_ASSISTANT_WINDOWS[self.assistant.key] = (321, 77)
        try:
            with (
                mock.patch.object(desktop, "_window_exists", return_value=True),
                mock.patch.object(desktop, "_window_process_id", return_value=77),
                mock.patch.object(desktop, "_window_text", return_value="Google Gemini"),
                mock.patch.object(desktop, "_launch_installed_assistant") as launch,
            ):
                target = desktop._resolve_assistant_target(self.assistant)

            self.assertIsNotNone(target)
            assert target is not None
            self.assertEqual(target.hwnd, 321)
            launch.assert_not_called()
        finally:
            desktop._PREFERRED_ASSISTANT_WINDOWS.clear()

    def test_installed_gemini_identity_uses_the_chromium_app_id(self) -> None:
        with mock.patch.object(
            desktop,
            "_window_app_user_model_id",
            return_value="Chrome._crx_gdfaincndogidkdcdkhapmbffkckdkhn",
        ):
            self.assertTrue(desktop._window_matches_installed_assistant(123, self.assistant))

        with mock.patch.object(
            desktop,
            "_window_app_user_model_id",
            return_value="Chrome.Default",
        ):
            self.assertFalse(desktop._window_matches_installed_assistant(123, self.assistant))

    def test_failed_installed_window_confirmation_uses_only_the_url_fallback(self) -> None:
        with (
            mock.patch.object(
                desktop,
                "_resolve_preferred_installed_target",
                return_value=(None, True),
            ),
            mock.patch.object(desktop, "find_assistant_windows", return_value=[]),
            mock.patch.object(desktop, "_launch_assistant_urls", return_value=(True, None)) as launch_urls,
            mock.patch.object(desktop, "_wait_for_assistant_window", return_value=[]),
            mock.patch.object(desktop, "_launch_assistant") as launch_assistant,
        ):
            target = desktop._resolve_assistant_target(self.assistant)

        self.assertIsNone(target)
        launch_urls.assert_called_once_with(self.assistant)
        launch_assistant.assert_not_called()


if __name__ == "__main__":
    unittest.main()
