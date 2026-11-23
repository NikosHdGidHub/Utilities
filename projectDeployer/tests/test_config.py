import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import config


class ConfigTests(unittest.TestCase):
    def test_read_write_and_invalid_settings(self):
        with TemporaryDirectory() as tmp, patch.object(config, "SETTINGS", Path(tmp) / "settings.json"):
            self.assertEqual(config.default_directory(), str(Path.home()))
            config.save_default(tmp)
            self.assertEqual(config.default_directory(), tmp)
            for content in ("{", "null", '{"directory":""}', json.dumps({"directory": tmp + "/absent"})):
                config.SETTINGS.write_text(content)
                with self.assertRaises(ValueError):
                    config.default_directory()
            with patch.object(config.os, "replace", side_effect=PermissionError):
                with self.assertRaises(PermissionError):
                    config.save_default(tmp)
            self.assertEqual(list(Path(tmp).iterdir()), [config.SETTINGS])

    def test_frozen_external_paths(self):
        with TemporaryDirectory() as tmp:
            code = ("import sys; from pathlib import Path; sys.frozen=True; "
                    "sys.executable=str(Path(sys.argv[1])/'ProjectDeployer.exe'); "
                    "import config, common; print(config.SETTINGS); print(common.BUNDLED_TEMPLATES)")
            paths = subprocess.check_output([sys.executable,"-c",code,tmp],text=True).splitlines()
            self.assertEqual(list(map(Path,paths)), [Path(tmp)/"settings.json",Path(tmp)/"templates"])
