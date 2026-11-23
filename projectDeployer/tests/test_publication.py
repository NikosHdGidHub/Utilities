import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from common import DeploymentError
from github import Publication
from deployer import deploy
from presets import Preset
from git_fixture import test_git_identity


class PublicationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name)
        self.calls = []
        self.origin = None
        self.fail = None
        self.publication = Publication("sample")
        for patcher in (patch("github.prepare_command", side_effect=lambda command, _:command),
                        patch("github.run_command", side_effect=self.run_tool)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_tool(self, command, directory, log):
        args = command.args
        log(command.label)
        self.calls.append(args)
        if self.fail and self.fail in args:
            raise DeploymentError(f"ошибка {self.fail}")
        if ".login" in args:
            log("tester")
        elif args == ("git","remote") and self.origin:
            log("origin")
        elif "get-url" in args:
            log(self.origin)
        elif "add" in args:
            self.origin=args[-1]

    def test_retry_push_private_and_public(self):
        for public in (False, True):
            with self.subTest(public=public):
                publication = Publication("sample",public)
                self.origin = None
                self.calls.clear()
                self.fail = "push"
                with self.assertRaises(DeploymentError):
                    publication.publish(self.path,lambda _:None)
                self.fail = None
                publication.publish(self.path,lambda _:None)
                creates=[args for args in self.calls if "POST" in args]
                self.assertEqual(len(creates),1)
                self.assertIn("private="+str(not public).lower(),creates[0])
                self.assertEqual(sum("add" in args for args in self.calls),1)
                self.assertEqual(self.calls[-1][-3:],("-u","origin","main"))

    def test_auth_network_conflict_and_existing_origin(self):
        for failed_arg in ("auth","user","POST"):
            self.calls.clear()
            self.fail=failed_arg
            with self.assertRaises(DeploymentError):
                self.publication.publish(self.path,lambda _:None)
            self.assertFalse(self.publication.created_url)
            self.assertFalse(any("push" in args for args in self.calls))
        self.fail=None
        self.origin="https://example.invalid/another"
        self.calls.clear()
        with self.assertRaisesRegex(DeploymentError,"origin"):
            self.publication.publish(self.path,lambda _:None)
        self.assertFalse(any("POST" in args for args in self.calls))

    def test_invalid_name_and_missing_cli(self):
        for bad in ("", "x/y", ".", "..", "a"*101):
            with self.assertRaisesRegex(DeploymentError,'имя'):
                Publication(bad).publish(self.path,lambda _:None)
        self.assertFalse(self.calls)
        with patch("github.prepare_command",side_effect=DeploymentError("gh недоступна")):
            with self.assertRaisesRegex(DeploymentError,"gh"):
                self.publication.publish(self.path,lambda _:None)

    def test_opt_out_and_failure_preserve_local_project(self):
        test_git_identity(self)
        template=self.path/'templates'/'custom'
        (template/'files').mkdir(parents=True)
        (template/'files/CHEATSHEET.md').write_text("test")
        (template/'template.json').write_text('{"name":"custom","description":"test"}')
        preset=Preset.load(template)
        deploy(preset,"test","local",str(self.path),lambda _:None)
        self.assertFalse(self.calls)
        self.fail='auth'
        warnings=[]
        path=deploy(preset,"test","remote",str(self.path),lambda _:None,publication=self.publication,
                    decide=lambda *_:"stop",warn=warnings.append)
        self.assertTrue(warnings)
        self.assertTrue((path/'.git/refs/heads/main').is_file())
