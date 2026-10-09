import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SnapshotInstallTests(unittest.TestCase):
    def test_wrapper_does_not_write_bytecode_into_runtime(self):
        scratch = ROOT / '.local'
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as tmp:
            fixture = Path(tmp)
            (fixture / 'scripts').mkdir()
            (fixture / 'voice_kanban').mkdir()
            shutil.copyfile(ROOT / 'scripts/consume.sh', fixture / 'scripts/consume.sh')
            (fixture / 'voice_kanban/consumer.py').write_text('import helper\n')
            (fixture / 'voice_kanban/helper.py').write_text('import os\nprint(os.environ.get("PYTHONDONTWRITEBYTECODE"))\n')
            env = dict(os.environ, VOICE_KANBAN_CONFIG=str(fixture / 'absent.sh'),
                       VOICE_KANBAN_PYTHON=sys.executable, PYTHONDONTWRITEBYTECODE='0')
            result = subprocess.run(['/bin/sh', str(fixture / 'scripts/consume.sh')], env=env,
                                    capture_output=True, text=True, check=True)
            self.assertEqual(result.stdout.strip(), '1')
            self.assertFalse((fixture / 'voice_kanban/__pycache__').exists())

    def test_reinstall_rejects_unexpected_files_and_symlinked_paths(self):
        from scripts.install_snapshot import install_snapshot
        scratch = ROOT / '.local'
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as tmp:
            repo = Path(tmp) / 'source'
            repo.mkdir()
            def git(*args):
                return subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True)
            git('init', '-q')
            git('config', 'user.name', 'Example')
            git('config', 'user.email', 'dev@example.org')
            (repo / 'voice_kanban').mkdir()
            (repo / 'voice_kanban/consumer.py').write_text('print("synthetic")\n')
            git('add', '.')
            git('commit', '-qm', 'Synthetic fixture')
            for kind in ('extra-file', 'package-symlink', 'root-symlink', 'manifest-symlink'):
                with self.subTest(kind=kind):
                    destination = Path(tmp) / kind
                    installed = install_snapshot(repo, destination)
                    if kind == 'extra-file':
                        (installed / 'voice_kanban/__init__.py').write_text('raise RuntimeError("unexpected")\n')
                    else:
                        original = installed if kind == 'root-symlink' else installed / (
                            'voice_kanban' if kind == 'package-symlink' else 'SOURCE.json')
                        moved = Path(tmp) / (kind + '-external')
                        shutil.move(str(original), str(moved))
                        original.symlink_to(moved, target_is_directory=moved.is_dir())
                    with self.assertRaises(RuntimeError):
                        install_snapshot(repo, destination)

    def test_installs_frozen_source_only_and_records_identity(self):
        from scripts.install_snapshot import install_snapshot
        scratch = ROOT / '.local'
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as tmp:
            repo = Path(tmp) / 'source'
            repo.mkdir()
            subprocess.run(['git', 'init', '-q', str(repo)], check=True)
            def git(*args):
                return subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()
            git('config', 'user.name', 'Example')
            git('config', 'user.email', 'dev@example.org')
            (repo / 'voice_kanban').mkdir()
            (repo / 'voice_kanban/consumer.py').write_text('print("synthetic")\n')
            (repo / '.gitignore').write_text('.local/\n')
            runtime_files = {'voice_kanban/__init__.py', 'voice_kanban/consumer.py',
                             'voice_kanban/transcribe.py', 'scripts/consume.sh'}
            for name in runtime_files - {'voice_kanban/consumer.py'}:
                target = repo / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / name).read_bytes())
            for name in ('scripts/setup.py', 'scripts/install_snapshot.py',
                         'scripts/test_audio_integration.py', 'voice_kanban/build_shortcut.py',
                         'voice_kanban/build_launchagent.py', 'native/receiver.swift',
                         'native/transcribe.swift', 'config.example.sh'):
                target = repo / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text('build/test-only fixture\n')
            git('add', '.')
            git('commit', '-qm', 'Synthetic fixture')
            (repo / '.local').mkdir()
            (repo / '.local/private.txt').write_text('Must not deploy')
            revision = git('rev-parse', 'HEAD')
            installed = install_snapshot(repo, Path(tmp) / 'runtimes')
            manifest = json.loads((installed / 'SOURCE.json').read_text())
            self.assertEqual(installed.name, revision)
            self.assertEqual(manifest['commit'], revision)
            self.assertEqual(set(manifest['sha256']), runtime_files)
            self.assertEqual((installed / 'voice_kanban/consumer.py').read_text(), 'print("synthetic")\n')
            self.assertFalse((installed / '.local').exists())
            self.assertEqual(install_snapshot(repo, Path(tmp) / 'runtimes'), installed)
            (repo / 'voice_kanban/consumer.py').write_text('changed\n')
            with self.assertRaises(RuntimeError):
                install_snapshot(repo, Path(tmp) / 'other-runtimes')
            (installed / 'voice_kanban/consumer.py').write_text('tampered\n')
            git('restore', 'voice_kanban/consumer.py')
            with self.assertRaises(RuntimeError):
                install_snapshot(repo, Path(tmp) / 'runtimes')


if __name__ == '__main__':
    unittest.main()
