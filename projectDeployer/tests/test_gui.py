import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import config as settings
from git_fixture import test_git_identity
from gui import App


class GuiTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        config = patch("gui.user_templates", return_value=self.directory / "presets")
        config.start()
        self.addCleanup(config.stop)
        patcher = patch.object(settings, "SETTINGS", self.directory / "settings.json")
        patcher.start()
        self.addCleanup(patcher.stop)
        test_git_identity(self)
        self.app = App()
        self.addCleanup(self.app.destroy)
        self.app.update()

    def test_preset_switch_and_folder_autofill(self):
        app = self.app
        self.assertTrue(app.winfo_viewable())
        self.assertIn("python main.py", app.cheatsheet.get("1.0", "end"))
        app.name.set("Название")
        self.assertEqual(app.folder.get(), "Название")
        app.folder.set("custom")
        app.name.set("Другое название")
        self.assertEqual(app.folder.get(), "custom")
        app.use_project_name()
        self.assertEqual(app.folder.get(), "Другое название")
        app.preset_list.selection_clear(0, "end")
        app.preset_list.selection_set(1)
        app.preset_list.event_generate("<<ListboxSelect>>")
        app.update()
        self.assertIn("npm run dev", app.cheatsheet.get("1.0", "end"))
        self.assertIn("Другое название", app.cheatsheet.get("1.0", "end"))

    def test_browse_accept_and_cancel(self):
        app = self.app
        with patch("gui.filedialog.askdirectory", return_value=str(self.directory)):
            app.choose_parent()
        with patch("gui.filedialog.askdirectory", return_value=""):
            app.choose_parent()
        self.assertEqual(app.parent.get(), str(self.directory))

    def test_deploy_button_reports_success_and_collision(self):
        app = self.app
        app.name.set("Демо")
        app.folder.set("demo")
        app.parent.set(str(self.directory))
        with patch.object(app, "deployment_options", return_value=None):
            app.create_button.invoke()
        self.assertTrue(app.busy)
        self.assertTrue(app.create_button.instate(["disabled"]))
        with patch("gui.messagebox.showinfo") as info:
            app.close()
            info.assert_called_once()
        self.wait_for_deployment()
        self.assertTrue((self.directory / "demo/CHEATSHEET.md").exists())
        self.assertIn("Проект создан", app.status.get())
        self.assertIn("Готово", app.log.get("1.0", "end"))
        with patch.object(app, "deployment_options", return_value=None):
            app.create_button.invoke()
        self.wait_for_deployment()
        self.assertIn("Не удалось", app.status.get())
        self.assertIn("уже существует", app.log.get("1.0", "end"))

    def test_settings_and_atomic_refresh(self):
        app = self.app
        self.assertEqual(app.preset_list.size(), 5)
        new = self.directory / "новый каталог"
        new.mkdir()
        with patch("gui.filedialog.askdirectory", return_value=str(new)):
            app.set_default()
        app.parent.set(str(self.directory))
        self.assertEqual(settings.default_directory(), str(new))
        app.preset_list.selection_clear(0, "end")
        app.preset_list.selection_set(2)
        selected = app.selected_preset().id
        app.refresh()
        self.assertEqual(app.selected_preset().id, selected)
        before = app.presets
        extra = self.directory / "presets" / "extra"
        extra.mkdir(parents=True)
        (extra/"template.json").write_text("{")
        app.refresh()
        self.assertIs(app.presets, before)
        self.assertIn("extra", app.log.get("1.0", "end"))
        app.set_busy(True)
        app.refresh()
        self.assertIs(app.presets, before)
        app.set_busy(False)

    def test_github_options_and_cancellation(self):
        values = ("Имя", "folder", str(self.directory))
        for public in (True, False):
            with patch("gui.messagebox.askyesno", return_value=True), patch(
                    "gui.messagebox.askyesnocancel", return_value=public), patch(
                    "gui.simpledialog.askstring", return_value="folder"):
                result = self.app.deployment_options(values)
                self.assertEqual((result.name, result.public), ("folder", public))
        with patch("gui.messagebox.askyesno", side_effect=[True, False]):
            self.assertIsNone(self.app.deployment_options(values))
        with patch("gui.messagebox.askyesno", return_value=False):
            self.assertIs(self.app.deployment_options(values), False)

    def test_worker_questions_and_partial_cleanup(self):
        import threading
        from common import Command
        app = self.app
        preset = app.selected_preset()
        preset.stages['Prepare'] = []
        preset.stages['Finalize'] = []
        app.parent.set(str(self.directory))
        current = threading.get_ident()
        for folder, decisions, delete_answers, remains, optional in (
            ("warn", ["skip"], [], True, True),
            ("kept", ["retry", "stop"], [False], True, False),
            ("removed", ["stop"], [True, True], False, False),
        ):
            app.name.set(folder)
            preset.stages["Scaffold"] = [Command("сбой", ("python", "-c", "raise SystemExit(7)"), not optional)]
            def reply(message, required):
                self.assertEqual(threading.get_ident(),current)
                self.assertEqual(required,not optional)
                return decisions.pop(0)
            with patch.object(app, "deployment_options",return_value=None), patch.object(
                    app,"decide_error",side_effect=reply), patch("gui.messagebox.askyesno",side_effect=delete_answers):
                app.start_deployment()
                self.wait_for_deployment()
            self.assertFalse(decisions)
            self.assertEqual((self.directory/folder).exists(), remains)
            self.assertIn("предупреждениями" if optional else "не завершено", app.status.get())
        self.assertFalse(list(self.directory.rglob("*.log")))
        self.assertFalse([p for p in self.directory.rglob("logs") if ".git" not in p.parts])

    def test_error_dialog_buttons_and_log(self):
        import tkinter as tk
        from tkinter import ttk
        app = self.app
        app.append_log("Тестовая диагностика")
        for required in (True, False):
            observed = []
            def interact():
                dialog = next(w for w in app.winfo_children() if isinstance(w, tk.Toplevel))
                buttons = {w.cget("text"): w for w in dialog.winfo_children() if isinstance(w, ttk.Button)}
                observed.append("Пропустить" in buttons)
                buttons["Посмотреть журнал"].invoke()
                viewer = next(w for w in dialog.winfo_children() if isinstance(w, tk.Toplevel))
                box = next(w for w in viewer.winfo_children() if isinstance(w, tk.Text))
                observed.append(box.get("1.0", "end").strip())
                viewer.destroy()
                buttons["Повторить" if required else "Пропустить"].invoke()
            app.after_idle(interact)
            self.assertEqual(app.decide_error("Ошибка", required), "retry" if required else "skip")
            self.assertEqual(observed, [not required, "Тестовая диагностика"])

    def wait_for_deployment(self):
        deadline = time.monotonic() + 20
        while self.app.busy and time.monotonic() < deadline:
            self.app.update()
            time.sleep(0.02)
        self.assertFalse(self.app.busy)


class EmptyGuiTests(unittest.TestCase):
    def test_empty_presets_disable_create(self):
        with TemporaryDirectory() as tmp, patch.object(settings, "SETTINGS", Path(tmp) / "settings.json"):
            app = App(presets=[])
        self.addCleanup(app.destroy)
        self.assertTrue(app.create_button.instate(["disabled"]))
        self.assertIn("Нет доступных", app.status.get())
        app.start_deployment()
        self.assertFalse(app.busy)
