import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from gui import App


class GuiTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        config = patch("gui.user_templates", return_value=self.directory / "presets")
        config.start()
        self.addCleanup(config.stop)
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
        app.create_button.invoke()
        self.wait_for_deployment()
        self.assertIn("Не удалось", app.status.get())
        self.assertIn("уже существует", app.log.get("1.0", "end"))

    def wait_for_deployment(self):
        deadline = time.monotonic() + 20
        while self.app.busy and time.monotonic() < deadline:
            self.app.update()
            time.sleep(0.02)
        self.assertFalse(self.app.busy)


class EmptyGuiTests(unittest.TestCase):
    def test_empty_presets_disable_create(self):
        app = App(presets=[])
        self.addCleanup(app.destroy)
        self.assertTrue(app.create_button.instate(["disabled"]))
        self.assertIn("Нет доступных", app.status.get())
        app.start_deployment()
        self.assertFalse(app.busy)
