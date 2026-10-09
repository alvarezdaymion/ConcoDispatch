#!/usr/bin/env python3
"""Install commit-frozen source, excluding local settings, data, and environments."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
FILES = {'voice_kanban/__init__.py', 'voice_kanban/consumer.py',
         'voice_kanban/transcribe.py', 'scripts/consume.sh'}


def git(repo: Path, *args: str) -> bytes:
    return subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True).stdout


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def install_snapshot(repo: Path, destination: Path) -> Path:
    repo, destination = repo.resolve(), destination.expanduser().resolve()
    if git(repo, 'status', '--porcelain').strip():
        raise RuntimeError('Commit and review all source changes before installing a snapshot')
    commit = git(repo, 'rev-parse', 'HEAD').decode().strip()
    tree = git(repo, 'rev-parse', 'HEAD^{tree}').decode().strip()
    source = {}
    for entry in git(repo, 'ls-tree', '-rz', 'HEAD').split(b'\0'):
        if not entry:
            continue
        metadata, raw_name = entry.split(b'\t', 1)
        name = raw_name.decode()
        if name not in FILES:
            continue
        if metadata.split()[0] != b'100644' and metadata.split()[0] != b'100755':
            raise RuntimeError('Runtime source must consist of regular tracked files')
        source[name] = git(repo, 'show', commit + ':' + name)
    if 'voice_kanban/consumer.py' not in source:
        raise RuntimeError('No receiver source found in this revision')
    manifest = {'commit': commit, 'tree': tree,
                'sha256': {name: digest(data) for name, data in sorted(source.items())}}
    destination.mkdir(parents=True, exist_ok=True)
    installed = destination / commit
    if installed.is_symlink():
        raise RuntimeError('Existing snapshot root must not be a symlink')
    if installed.exists():
        expected_paths = set(source) | {'SOURCE.json'}
        for name in source:
            expected_paths.update(str(parent) for parent in Path(name).parents if str(parent) != '.')
        actual_paths = set()
        for path in installed.rglob('*'):
            if path.is_symlink() or not (path.is_file() or path.is_dir()):
                raise RuntimeError('Existing snapshot contains a nonregular path: ' + str(path.relative_to(installed)))
            actual_paths.add(str(path.relative_to(installed)))
        if actual_paths != expected_paths:
            raise RuntimeError('Existing snapshot path set does not match the source revision')
        if json.loads((installed / 'SOURCE.json').read_text()) != manifest:
            raise RuntimeError('Existing snapshot manifest does not match the source revision')
        for name, expected in manifest['sha256'].items():
            path = installed / name
            if path.is_symlink() or digest(path.read_bytes()) != expected:
                raise RuntimeError('Existing snapshot content has changed: ' + name)
        return installed
    staging = Path(tempfile.mkdtemp(prefix='.staging-', dir=destination))
    try:
        for name, data in source.items():
            target = staging / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        (staging / 'SOURCE.json').write_text(json.dumps(manifest, indent=2) + '\n')
        staging.rename(installed)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return installed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path,
                        default=Path.home() / 'Library/Application Support/Hermes Voice Kanban/runtimes')
    args = parser.parse_args()
    print(install_snapshot(ROOT, args.destination))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
