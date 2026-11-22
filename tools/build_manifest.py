#!/usr/bin/env python3
"""Maintainer operation: record the release file inventory after authorised packaging.

This creates an integrity inventory. It does not authenticate changes or approve
scientific modifications. Ordinary users should run reproduce.py verify.
"""
from pathlib import Path
from hashlib import sha256
import argparse
import json
import os

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
args = parser.parse_args()
root = args.root.resolve()
paths = []
for directory, dirs, files in os.walk(root):
    dirs[:] = [n for n in dirs if n != '.git']
    for name in dirs + files:
        if (Path(directory) / name).is_symlink():
            raise SystemExit('Symlinks are not part of the release payload')
    for name in files:
        p = Path(directory) / name
        if p != root / 'MANIFEST_SHA256.json' and p != root / 'FILE_ALLOWLIST.txt':
            paths.append(p.relative_to(root).as_posix())
names = sorted(paths + ['MANIFEST_SHA256.json', 'FILE_ALLOWLIST.txt'])
(root / 'FILE_ALLOWLIST.txt').write_text('\n'.join(names) + '\n', encoding='utf-8', newline='\n')
rows = []
for rel in sorted(paths + ['FILE_ALLOWLIST.txt']):
    p = root / rel
    h = sha256()
    with p.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    rows.append({'path': rel, 'bytes': p.stat().st_size, 'sha256': h.hexdigest()})
manifest = {'schema_version': '1.0', 'version': '1.0.0',
            'scope': 'Exact local release payload, excluding this manifest and local Git metadata.',
            'files': rows}
(root / 'MANIFEST_SHA256.json').write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n'
)
print(json.dumps({'payload_files': len(rows), 'manifest_sha256': sha256((root / 'MANIFEST_SHA256.json').read_bytes()).hexdigest()}))
