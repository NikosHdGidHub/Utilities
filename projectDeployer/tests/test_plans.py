import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import common
from common import Command, DeploymentError
from deployer import PartialProject, deploy
from git_fixture import test_git_identity
from presets import STAGES, load_presets


class PlanTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.templates = self.root / 'templates'
        self.log = []
        test_git_identity(self)

    def layer(self, folder, **fields):
        path = self.templates / folder
        path.mkdir(parents=True, exist_ok=True)
        (path / 'template.json').write_text(json.dumps(dict(name=folder, description='test', **fields)))
        return path

    def load(self):
        plans, errors = load_presets(self.templates)
        self.assertFalse(errors)
        return plans[0]

    def run_plan(self, **kwargs):
        return deploy(self.load(), 'Имя', 'result', str(self.root), self.log.append, **kwargs)

    def test_multi_level_order_snapshot_and_diamond(self):
        for folder, fields in (
            ('base', {}), ('mid', {'extends':'base'}), ('feature', {'extends':'base'}),
            ('final', {'extends':'mid', 'features':['feature', 'feature']})
        ):
            path = self.layer(folder, component=folder != 'final', stages={
                'Finalize':[{'label':folder, 'args':['python', '-V']}]}, **fields)
            source = path / 'files'
            source.mkdir()
            (source / 'CHEATSHEET.md').write_text(folder)
        preset = self.load()
        self.assertEqual([op.label for op in preset.stages['Finalize']], ['base','mid','feature','final'])
        self.assertEqual(preset.cheatsheet,'final')
        (source / 'CHEATSHEET.md').write_text('new')
        self.assertEqual(preset.files[Path('CHEATSHEET.md')], 'final')
        self.assertEqual(self.load().cheatsheet, 'new')

    def test_invalid_configs(self):
        path = self.layer('a', component=True)
        j = path / 'template.json'
        for value in ([], {'version':True}, {'version':2},{'extends':'missing'}, {'extends':'a'},
                      {'features':'a'},{'files':'../x'},{'mkdir':['/root']},{'remove':['C:\\x']},
                      {'stages':{'Late':[]}}, {'stages':{'Prepare':[{'label':'x','args':['echo'],'required':0}]}},
                      {'stages':{'Prepare':[{'label':'x','args':[None]}]}}):
            with self.subTest(value=value):
                j.write_text(json.dumps(dict(name="a",description="a",component=True,**value) if isinstance(value,dict) else value))
                self.assertTrue(load_presets(self.templates)[1])
        j.write_text('!')
        self.assertTrue(load_presets(self.templates)[1])
        j.unlink()
        self.assertTrue(load_presets(self.templates)[1])
        self.layer('a',component=True)
        self.layer('b',id='a',component=True)
        self.assertIn('Повтор ID',str(load_presets(self.templates)[1]))

    def simple(self, stages=None, **fields):
        d = self.layer('template', stages=stages or {}, **fields) / 'files'
        d.mkdir()
        (d/'CHEATSHEET.md').write_text('Hello')
        return d

    def test_stage_order_cleanup_mkdir_and_optional_skip(self):
        self.simple({'Scaffold':[{'label':'touch','args':['python','-c','open("old","w").close()']}],
                     'Finalize':[{'label':'optional','required':False,'args':['missing-binary-xyz']}]},
                    mkdir=['a/b'],remove=['old','absent'])
        warnings = []
        path = self.run_plan(decide=lambda *_:'skip',warn=warnings.append)
        self.assertEqual(len(warnings),1)
        self.assertFalse((path/'old').exists())
        self.assertTrue((path/'a/b').is_dir())
        self.assertEqual([line[5:] for line in self.log if line.startswith('Этап ')], list(STAGES[:-1]))

    def test_retry_only_failed_command_and_disallow_required_skip(self):
        self.simple({'Scaffold':[{'label':'fail once','args':['python','-c',
            'from pathlib import Path; import sys; p=Path("flag"); ok=p.exists(); p.touch(); print("stderr", file=sys.stderr); sys.exit(0 if ok else 4)']}]})
        self.run_plan(decide=lambda *_:'retry')
        self.assertEqual(self.log.count('stderr'),2)
        self.assertEqual(self.log.count('Этап Scaffold'),1)
        (self.root/'result').rename(self.root/'first')
        with self.assertRaises(PartialProject) as ctx:
            self.run_plan(decide=lambda *_:'skip')
        ctx.exception.discard()
        self.assertFalse((self.root/'result').exists())

    def test_replaced_partial_directory_cannot_be_deleted(self):
        self.simple({'Finalize':[{'label':'fail','args':['python','-c','raise SystemExit(1)']}]})
        with self.assertRaises(PartialProject) as ctx:
            self.run_plan()
        path = ctx.exception.path
        path.rename(self.root/'old')
        path.mkdir()
        with self.assertRaises(DeploymentError):
            ctx.exception.discard()
        self.assertTrue(path.exists())

    @unittest.skipIf(os.name == 'nt', 'Создание ссылок в Windows требует привилегии')
    def test_symlink_traversal(self):
        protected = self.root/'keep'
        protected.mkdir()
        sentinel = protected/'sentinel'
        sentinel.write_text('keep')
        self.simple({'Scaffold':[{'label':'symlink','args':['python','-c',
            'from pathlib import Path; import sys; Path("link").symlink_to(sys.argv[1],target_is_directory=True)',str(protected)]}]},
            remove=['link/sentinel'])
        with self.assertRaisesRegex(PartialProject, 'ссылку') as ctx:
            self.run_plan()
        ctx.exception.discard()
        self.assertEqual(sentinel.read_text(),'keep')

    def test_missing_git_identity(self):
        self.simple()
        with patch.dict(os.environ,GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL=os.devnull,GIT_CONFIG_COUNT='0'):
            with self.assertRaisesRegex(PartialProject, 'user.name') as ctx:
                self.run_plan()
        self.assertNotEqual(subprocess.run(['git','rev-parse','--verify','HEAD'],cwd=ctx.exception.path,
                                           capture_output=True).returncode,0)

    def test_batch_argument_filter(self):
        with patch.object(common.sys,'platform','win32'), patch.object(common,'resolve_program',return_value='npm.cmd'):
            with self.assertRaises(DeploymentError):
                common.prepare_command(Command('tool',('npm','bad & argument')), {})
            self.assertEqual(common.prepare_command(Command('tool',('npm','--version')),{}).args[-1],'--version')

    @unittest.skipUnless(os.name=='nt','Требуется Windows')
    def test_real_cmd(self):
        path=self.root/'test tool.cmd'
        path.write_text('@echo off\necho %1\n')
        op=common.prepare_command(Command('test',(str(path),'sample')), {})
        common.run_command(op,self.root,self.log.append)
        self.assertIn('sample',self.log)
