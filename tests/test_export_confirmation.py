from __future__ import annotations

import unittest
import wave
from pathlib import Path
from unittest.mock import Mock, patch

from resumator import ui


ASSETS_DIR = Path(__file__).resolve().parents[1] / "assets"
ANIMATION_PATH = ASSETS_DIR / "export-success.webp"
SOUND_PATH = ASSETS_DIR / "export-success.wav"


class ExportConfirmationTests(unittest.TestCase):
    def test_docx_and_pdf_use_export_confirmation(self) -> None:
        for output_format, file_label in (("docx", "DOCX"), ("pdf", "PDF")):
            with self.subTest(output_format=output_format):
                app = object.__new__(ui.ResumatorApp)
                with (
                    patch.object(app, "_show_export_confirmation") as show_confirmation,
                    patch.object(ui.messagebox, "showinfo") as showinfo,
                ):
                    app._show_export_success(output_format, file_label)

                show_confirmation.assert_called_once_with(file_label)
                showinfo.assert_not_called()

    def test_json_uses_standard_messagebox_confirmation(self) -> None:
        app = object.__new__(ui.ResumatorApp)
        with (
            patch.object(app, "_show_export_confirmation") as show_confirmation,
            patch.object(ui.messagebox, "showinfo") as showinfo,
        ):
            app._show_export_success("json", "JSON")

        show_confirmation.assert_not_called()
        showinfo.assert_called_once_with(ui.APP_TITLE, "Resposta exportada em JSON.")

    def test_export_confirmation_falls_back_when_pillow_is_unavailable(self) -> None:
        app = object.__new__(ui.ResumatorApp)
        for missing_dependency in ("Image", "ImageTk"):
            with self.subTest(missing_dependency=missing_dependency):
                with (
                    patch.object(ui, missing_dependency, None),
                    patch.object(ui.messagebox, "showinfo") as showinfo,
                ):
                    app._show_export_confirmation("PDF")

                showinfo.assert_called_once_with(ui.APP_TITLE, "Resposta exportada em PDF.")

    def test_export_confirmation_falls_back_when_animation_is_missing(self) -> None:
        app = object.__new__(ui.ResumatorApp)
        missing_path = ASSETS_DIR / "missing-export-success.webp"
        self.assertFalse(missing_path.exists())

        with (
            patch.object(ui, "Image", object()),
            patch.object(ui, "ImageTk", object()),
            patch.object(ui, "_resource_path", return_value=missing_path) as resource_path,
            patch.object(ui.messagebox, "showinfo") as showinfo,
        ):
            app._show_export_confirmation("DOCX")

        resource_path.assert_called_once_with("assets", "export-success.webp")
        showinfo.assert_called_once_with(ui.APP_TITLE, "Resposta exportada em DOCX.")

    def test_export_confirmation_sound_plays_existing_asset_asynchronously(self) -> None:
        self.assertTrue(SOUND_PATH.is_file())
        app = object.__new__(ui.ResumatorApp)
        fake_winsound = Mock()
        fake_winsound.SND_FILENAME = 0x00020000
        fake_winsound.SND_ASYNC = 0x0001
        fake_winsound.SND_NODEFAULT = 0x0002

        with (
            patch.object(ui, "winsound", fake_winsound),
            patch.object(ui, "_resource_path", return_value=SOUND_PATH) as resource_path,
        ):
            app._play_export_confirmation_sound()

        expected_flags = (
            fake_winsound.SND_FILENAME
            | fake_winsound.SND_ASYNC
            | fake_winsound.SND_NODEFAULT
        )
        resource_path.assert_called_once_with("assets", "export-success.wav")
        fake_winsound.PlaySound.assert_called_once_with(str(SOUND_PATH), expected_flags)
        self.assertEqual(expected_flags & fake_winsound.SND_ASYNC, fake_winsound.SND_ASYNC)

    def test_animation_asset_has_expected_metadata(self) -> None:
        self.assertTrue(ANIMATION_PATH.is_file())
        self.assertIsNotNone(ui.Image)

        with ui.Image.open(ANIMATION_PATH) as animation:  # type: ignore[union-attr]
            self.assertEqual(animation.format, "WEBP")
            self.assertEqual(animation.size, (640, 360))
            self.assertEqual(getattr(animation, "n_frames", 1), 36)

    def test_sound_asset_has_expected_metadata(self) -> None:
        self.assertTrue(SOUND_PATH.is_file())

        with wave.open(str(SOUND_PATH), "rb") as sound:
            channels = sound.getnchannels()
            frame_rate = sound.getframerate()
            duration_seconds = sound.getnframes() / frame_rate

        self.assertEqual(channels, 2)
        self.assertEqual(frame_rate, 44_100)
        self.assertAlmostEqual(duration_seconds, 3.0, delta=0.05)

    def test_real_tk_confirmation_creates_and_cleans_up_popup(self) -> None:
        if ui.Image is None or ui.ImageTk is None:
            self.skipTest("Pillow/ImageTk indisponivel")
        try:
            root = ui.tk.Tk()
        except ui.tk.TclError as exc:
            self.skipTest(f"Tk indisponivel: {exc}")

        app = object.__new__(ui.ResumatorApp)
        app.root = root
        root.withdraw()
        root.geometry("800x600")
        try:
            with (
                patch.object(app, "_play_export_confirmation_sound"),
                patch.object(ui.messagebox, "showinfo") as showinfo,
            ):
                app._show_export_confirmation("PDF")
                root.update()

            window = app._export_confirmation_window
            self.assertIsNotNone(window)
            self.assertTrue(window.winfo_exists())
            self.assertEqual(len(app._export_confirmation_frames), 36)
            self.assertIsNotNone(app._export_confirmation_frame_after_id)
            self.assertIsNotNone(app._export_confirmation_close_after_id)
            showinfo.assert_not_called()

            app._close_export_confirmation()
            root.update()
            self.assertIsNone(app._export_confirmation_window)
            self.assertEqual(app._export_confirmation_frames, [])
        finally:
            app._close_export_confirmation()
            root.destroy()


if __name__ == "__main__":
    unittest.main()
