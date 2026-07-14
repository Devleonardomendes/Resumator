from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from resumator import solicitador_bridge as bridge


class Quimera41BridgeTests(unittest.TestCase):
    def test_quimera_41_is_the_preferred_target(self) -> None:
        self.assertEqual(
            bridge.SOLICITADOR_TARGETS[0],
            ("QUIMERA 4.1", "QUIMERA 4.1.exe"),
        )

    def test_candidate_targets_include_quimera_41_source_and_executable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            project_dir = root / "QUIMERA 4.1"
            dist_dir = project_dir / "dist-py314" / "QUIMERA 4.1"
            project_dir.mkdir()
            dist_dir.mkdir(parents=True)
            app_path = project_dir / "app.py"
            exe_path = dist_dir / "QUIMERA 4.1.exe"
            app_path.write_text("# teste\n", encoding="utf-8")
            exe_path.write_bytes(b"teste")
            payload_path = root / "resumo.json"
            payload_path.write_text("{}", encoding="utf-8")

            with (
                mock.patch.object(bridge, "_candidate_base_dirs", return_value=[root]),
                mock.patch.object(bridge, "_candidate_python_executables", return_value=[Path("python.exe")]),
                mock.patch.object(bridge.sys, "frozen", False, create=True),
                mock.patch.dict(bridge.os.environ, {"LOCALAPPDATA": str(root / "local")}, clear=False),
            ):
                targets = bridge._candidate_targets(payload_path)

        commands = [target.command for target in targets]
        self.assertIn(
            ("python.exe", str(app_path), "--summary-file", str(payload_path)),
            commands,
        )
        self.assertIn(
            (str(exe_path), "--summary-file", str(payload_path)),
            commands,
        )

    def test_export_launches_quimera_41_with_summary_file(self) -> None:
        target = bridge.SolicitadorTarget(
            command=("QUIMERA 4.1.exe", "--summary-file", "resumo.json"),
            cwd=Path("QUIMERA 4.1"),
            label="QUIMERA 4.1",
        )

        with (
            mock.patch.object(bridge, "_write_payload", return_value=Path("resumo.json")),
            mock.patch.object(bridge, "_candidate_targets", return_value=[target]),
            mock.patch.object(bridge.subprocess, "Popen") as popen,
        ):
            result = bridge.export_summary_to_solicitador("Resumo para o QUIMERA")

        self.assertTrue(result.ok)
        self.assertEqual(result.target, "QUIMERA 4.1")
        popen.assert_called_once()
        self.assertEqual(
            popen.call_args.args[0],
            ["QUIMERA 4.1.exe", "--summary-file", "resumo.json"],
        )

    def test_all_users_install_is_discovered_under_program_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            exe_path = root / "QUIMERA 4.1" / "QUIMERA 4.1.exe"
            exe_path.parent.mkdir(parents=True)
            exe_path.write_bytes(b"teste")

            with (
                mock.patch.object(bridge, "_candidate_base_dirs", return_value=[]),
                mock.patch.dict(
                    bridge.os.environ,
                    {"LOCALAPPDATA": "", "ProgramFiles": str(root), "ProgramFiles(x86)": ""},
                    clear=False,
                ),
            ):
                candidates = bridge._candidate_exe_paths()

        self.assertEqual(candidates, [exe_path])


if __name__ == "__main__":
    unittest.main()
