import json
import os
import shutil
import socket
import subprocess
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from git_fixture import test_git_identity
from urllib.error import URLError
from urllib.request import urlopen

from deployer import BUNDLED_TEMPLATES, DeploymentError, Preset, deploy, load_presets


def run(project, *args):
    result = subprocess.run(
        args, cwd=project, text=True, encoding="utf-8", capture_output=True, timeout=120,
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    if result.returncode:
        raise AssertionError(f"{args} failed:\n{result.stdout}\n{result.stderr}")
    return result.stdout + result.stderr


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        test_git_identity(self)
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.parent = Path(temporary.name)
        self.log = []

    def make_preset(self, commands=(), post_commands=(), name="custom"):
        directory = self.parent / "presets" / name
        files = directory / "files"
        files.mkdir(parents=True)
        (directory / "template.json").write_text(json.dumps({
            "name": name,
            "description": "Test preset",
            "commands": list(commands),
            "post_commands": list(post_commands),
        }), encoding="utf-8")
        (files / "CHEATSHEET.md").write_text("# {{project_name}}\n", encoding="utf-8")
        return directory

    def test_custom_preset_commands_and_files(self):
        directory = self.make_preset(
            commands=[{"label": "prepare", "args": [
                "python", "-c", "from pathlib import Path; Path('ready').mkdir()",
            ]}],
            post_commands=[{"label": "validate", "args": [
                "python", "-c",
                "from pathlib import Path; import sys;"
                "assert Path('ready/data.txt').read_text(encoding='utf-8') == sys.argv[1]; print('verified')",
                "{{project_name}}",
            ]}],
        )
        (directory / "files/ready").mkdir()
        (directory / "files/ready/data.txt").write_text("{{project_name}}", encoding="utf-8")
        (directory / "files/asset.bin").write_bytes(b"\x80\xff\x00")
        presets, errors = load_presets(directory.parent)
        self.assertFalse(errors)
        project = deploy(presets[0], 'Мой "проект" & Co', "custom-folder", str(self.parent), self.log.append)
        self.assertEqual(project.name, "custom-folder")
        self.assertEqual((project / "asset.bin").read_bytes(), b"\x80\xff\x00")
        self.assertIn("verified", self.log)

    def test_invalid_presets_are_reported_and_valid_presets_load(self):
        bad = self.make_preset([{"label": "bad", "args": ["{{unknown}}"]}])
        self.make_preset(name="valid")
        other = self.make_preset(post_commands=["bad"], name="bad-post")
        presets, errors = load_presets(self.parent / "absent", bad.parent)
        self.assertEqual([p.name for p in presets], ["valid"])
        self.assertEqual(len(errors), 2)
        self.assertTrue(any("unknown" in error for error in errors))
        self.assertTrue(any(other.name in error for error in errors))

    def test_rejects_invalid_input_and_preserves_existing_folder(self):
        preset = Preset.load(self.make_preset())
        existing = self.parent / "existing"
        existing.mkdir()
        important = existing / "important.txt"
        important.write_text("keep", encoding="utf-8")
        for project, folder, parent in (
            ("", "valid", self.parent), ("bad\nname", "valid", self.parent),
            ("Demo", "existing", self.parent), ("Demo", "valid", important),
            *(("Demo", name, self.parent) for name in ("", "..", "a/b", "a\\b", "NUL.txt", "trail.", " trail")),
        ):
            with self.subTest(name=project, folder=folder, parent=parent):
                with self.assertRaises(DeploymentError):
                    deploy(preset, project, folder, str(parent), self.log.append)
        self.assertEqual(important.read_text(encoding="utf-8"), "keep")
        self.assertFalse(self.log)

    def test_missing_program_fails_before_creation(self):
        preset = Preset.load(self.make_preset([{"label": "tool", "args": ["absent-tool"]}]))
        with self.assertRaisesRegex(DeploymentError, "absent-tool"):
            deploy(preset, "Demo", "demo", str(self.parent), self.log.append)
        self.assertFalse((self.parent / "demo").exists())

    def test_failed_command_keeps_partial_project_and_stops(self):
        preset = Preset.load(self.make_preset([
            {"label": "failed", "args": ["python", "-c", "print('diagnostic'); raise SystemExit(7)"]},
            {"label": "skip", "args": ["python", "-c", "raise AssertionError"]},
        ]))
        with self.assertRaisesRegex(DeploymentError, "кодом 7"):
            deploy(preset, "Demo", "demo", str(self.parent), self.log.append)
        self.assertTrue((self.parent / "demo").is_dir())
        self.assertIn("diagnostic", self.log)
        self.assertNotIn("› skip", self.log)
        self.assertFalse((self.parent / "demo/CHEATSHEET.md").exists())

    def test_overlay_replaces_a_generated_file(self):
        preset = Preset.load(self.make_preset([{"label": "prepare", "args": [
            "python", "-c", "from pathlib import Path; Path('CHEATSHEET.md').write_text('keep')",
        ]}]))
        project = deploy(preset, "Demo", "demo", str(self.parent), self.log.append)
        self.assertEqual((project / "CHEATSHEET.md").read_text(), "# Demo\n")

    def test_python_project(self):
        preset = Preset.load(BUNDLED_TEMPLATES / "python")
        project = deploy(preset, 'Мой "Python" & Co', "Мой проект", str(self.parent), self.log.append)
        python = project / (".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python")
        self.assertIn('Проект Мой "Python" & Co готов к работе!' , run(project, str(python), "main.py"))
        self.assertEqual((project / "requirements.txt").read_bytes(), b"")
        for rel in ("tests", "pyproject.toml", "test_main.py"):
            self.assertFalse((project / rel).exists())
        self.assertIn(".venv", run(project, str(python), "-m", "pip", "--version"))
        self.assertEqual(run(project, "git", "log", "-1", "--format=%s").strip(), "Initial commit")
        self.assertIn('Мой "Python" & Co', (project / "README.md").read_text(encoding="utf-8"))
        self.assertIn("python main.py", (project / "CHEATSHEET.md").read_text(encoding="utf-8"))
        self.assertEqual(run(project, "git", "branch", "--show-current").strip(), "main")
        self.assertIn(".venv", run(project, "git", "check-ignore", ".venv"))

    def test_react_project(self):
        npm = shutil.which("npm")
        self.assertIsNotNone(npm, "npm is required for the React integration test")
        for ident in ("react-ts", "react-full", "react-router", "react-tailwind"):
            with self.subTest(preset=ident):
                self.check_react(ident, npm)

    def check_react(self, ident, npm):
        preset = Preset.load(BUNDLED_TEMPLATES / ident)
        project = deploy(preset, "Мой React App", f"Web проект {ident}", str(self.parent), self.log.append)
        package = json.loads((project / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(package["name"], "react-app")
        self.assertIn("react", package["dependencies"])
        self.assertIn("typescript", package["devDependencies"])
        self.assertTrue((project / "package-lock.json").is_file())
        self.assertIn("npm run dev", (project / "CHEATSHEET.md").read_text(encoding="utf-8"))
        self.assertEqual(run(project, "git", "branch", "--show-current").strip(), "main")
        self.assertEqual(run(project, "git", "log", "-1", "--format=%s").strip(), "Initial commit")
        self.assertFalse(run(project, "git", "ls-files", "node_modules"))
        self.assertTrue((project / "README.md").is_file())
        self.assertFalse((project / "src/assets").exists())
        self.assertEqual("react-router-dom" in package["dependencies"], ident in ("react-router", "react-full"))
        self.assertEqual("tailwindcss" in package["devDependencies"], ident in ("react-tailwind", "react-full"))
        for name in ("Button", "Card", "Counter", "Toggle"):
            self.assertTrue((project / f"src/components/{name}.tsx").exists())
        run(project, npm, "run", "lint")
        run(project, npm, "run", "build")
        self.assertTrue((project / "dist/index.html").is_file())
        if os.getenv("DEPLOYER_BROWSER_TESTS") == "1":
            from browser_checks import check_page
            check_page(self, project, ident in ("react-router", "react-full"), ident in ("react-tailwind", "react-full"))
        args = [shutil.which("node"), str(project / "node_modules/vite/bin/vite.js")]
        self.assert_serves_html(project, args, "/src/main.tsx")
        self.assert_serves_html(project, [*args, "preview"], "/assets/")

    def assert_serves_html(self, project, args, expected):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        command = [*args, "--host", "127.0.0.1", "--port", str(port), "--strictPort"]
        with subprocess.Popen(command, cwd=project, stdout=subprocess.DEVNULL) as server:
            try:
                deadline = time.monotonic() + 15
                while server.poll() is None and time.monotonic() < deadline:
                    try:
                        with urlopen(f"http://127.0.0.1:{port}", timeout=1) as response:
                            self.assertIn(expected, response.read().decode())
                            return
                    except URLError:
                        time.sleep(0.1)
                self.fail(f"Vite did not serve HTML: {command}")
            finally:
                if server.poll() is None:
                    server.terminate()
