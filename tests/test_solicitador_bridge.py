from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from resumator import solicitador_bridge as bridge


class Quimera42BridgeTests(unittest.TestCase):
    def test_quimera_42_is_preferred_and_41_is_the_first_fallback(self) -> None:
        self.assertEqual(
            bridge.SOLICITADOR_TARGETS[:2],
            (
                ("QUIMERA 4.2", "QUIMERA 4.2.exe"),
                ("QUIMERA 4.1", "QUIMERA 4.1.exe"),
            ),
        )

    def test_candidate_targets_include_quimera_42_before_41_source_and_executable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            project_42_dir = root / "QUIMERA 4.2"
            project_41_dir = root / "QUIMERA 4.1"
            dist_42_dir = project_42_dir / "dist-py314" / "QUIMERA 4.2"
            dist_41_dir = project_41_dir / "dist-py314" / "QUIMERA 4.1"
            project_42_dir.mkdir()
            project_41_dir.mkdir()
            dist_42_dir.mkdir(parents=True)
            dist_41_dir.mkdir(parents=True)
            app_42_path = project_42_dir / "app.py"
            app_41_path = project_41_dir / "app.py"
            exe_42_path = dist_42_dir / "QUIMERA 4.2.exe"
            exe_41_path = dist_41_dir / "QUIMERA 4.1.exe"
            app_42_path.write_text("# teste\n", encoding="utf-8")
            app_41_path.write_text("# teste\n", encoding="utf-8")
            exe_42_path.write_bytes(b"teste")
            exe_41_path.write_bytes(b"teste")
            payload_path = root / "resumo.json"
            payload_path.write_text("{}", encoding="utf-8")

            with (
                mock.patch.object(bridge, "_candidate_base_dirs", return_value=[root]),
                mock.patch.object(bridge, "_candidate_python_executables", return_value=[Path("python.exe")]),
                mock.patch.object(bridge.sys, "frozen", False, create=True),
                mock.patch.dict(
                    bridge.os.environ,
                    {
                        "LOCALAPPDATA": str(root / "local"),
                        "ProgramFiles": "",
                        "ProgramFiles(x86)": "",
                    },
                    clear=False,
                ),
            ):
                targets = bridge._candidate_targets(payload_path)

        commands = [target.command for target in targets]
        self.assertEqual(
            commands,
            [
                ("python.exe", str(app_42_path), "--summary-file", str(payload_path)),
                ("python.exe", str(app_41_path), "--summary-file", str(payload_path)),
                (str(exe_42_path), "--summary-file", str(payload_path)),
                (str(exe_41_path), "--summary-file", str(payload_path)),
            ],
        )

    def test_export_launches_quimera_42_with_summary_file(self) -> None:
        target = bridge.SolicitadorTarget(
            command=("QUIMERA 4.2.exe", "--summary-file", "resumo.json"),
            cwd=Path("QUIMERA 4.2"),
            label="QUIMERA 4.2",
        )

        with (
            mock.patch.object(bridge, "_write_payload", return_value=Path("resumo.json")),
            mock.patch.object(bridge, "_candidate_targets", return_value=[target]),
            mock.patch.object(bridge.subprocess, "Popen") as popen,
        ):
            result = bridge.export_summary_to_solicitador("Resumo para o QUIMERA")

        self.assertTrue(result.ok)
        self.assertEqual(result.target, "QUIMERA 4.2")
        popen.assert_called_once()
        self.assertEqual(
            popen.call_args.args[0],
            ["QUIMERA 4.2.exe", "--summary-file", "resumo.json"],
        )

    def test_export_falls_back_to_quimera_41_when_42_launch_fails(self) -> None:
        targets = [
            bridge.SolicitadorTarget(
                command=("QUIMERA 4.2.exe", "--summary-file", "resumo.json"),
                cwd=Path("QUIMERA 4.2"),
                label="QUIMERA 4.2",
            ),
            bridge.SolicitadorTarget(
                command=("QUIMERA 4.1.exe", "--summary-file", "resumo.json"),
                cwd=Path("QUIMERA 4.1"),
                label="QUIMERA 4.1",
            ),
        ]

        with (
            mock.patch.object(bridge, "_write_payload", return_value=Path("resumo.json")),
            mock.patch.object(bridge, "_candidate_targets", return_value=targets),
            mock.patch.object(
                bridge.subprocess,
                "Popen",
                side_effect=[OSError("QUIMERA 4.2 indisponível"), mock.Mock()],
            ) as popen,
        ):
            result = bridge.export_summary_to_solicitador("Resumo para o QUIMERA")

        self.assertTrue(result.ok)
        self.assertEqual(result.target, "QUIMERA 4.1")
        self.assertEqual(
            [call.args[0] for call in popen.call_args_list],
            [
                ["QUIMERA 4.2.exe", "--summary-file", "resumo.json"],
                ["QUIMERA 4.1.exe", "--summary-file", "resumo.json"],
            ],
        )

    def test_all_users_installs_are_discovered_in_version_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            exe_42_path = root / "QUIMERA 4.2" / "QUIMERA 4.2.exe"
            exe_41_path = root / "QUIMERA 4.1" / "QUIMERA 4.1.exe"
            exe_42_path.parent.mkdir(parents=True)
            exe_41_path.parent.mkdir(parents=True)
            exe_42_path.write_bytes(b"teste")
            exe_41_path.write_bytes(b"teste")

            with (
                mock.patch.object(bridge, "_candidate_base_dirs", return_value=[]),
                mock.patch.dict(
                    bridge.os.environ,
                    {"LOCALAPPDATA": "", "ProgramFiles": str(root), "ProgramFiles(x86)": ""},
                    clear=False,
                ),
            ):
                candidates = bridge._candidate_exe_paths()

        self.assertEqual(candidates, [exe_42_path, exe_41_path])


if __name__ == "__main__":
    unittest.main()
