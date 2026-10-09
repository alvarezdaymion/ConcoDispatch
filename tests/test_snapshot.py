import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SnapshotInstallTests(unittest.TestCase):
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
            git('add', '.')
            git('commit', '-qm', 'Synthetic fixture')
            (repo / '.local').mkdir()
            (repo / '.local/private.txt').write_text('Must not deploy')
            revision = git('rev-parse', 'HEAD')
            installed = install_snapshot(repo, Path(tmp) / 'runtimes')
            manifest = json.loads((installed / 'SOURCE.json').read_text())
            self.assertEqual(installed.name, revision)
            self.assertEqual(manifest['commit'], revision)
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
