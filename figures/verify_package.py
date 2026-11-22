#!/usr/bin/env python3
"""Verify the complete delivered file set against its fixed SHA-256 manifest."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parent
MANIFEST = 'MANIFEST_SHA256.json'

def main():
    try:
        document = json.loads((ROOT / MANIFEST).read_text(encoding='utf-8'))
        rows = document['files']
        if document.get('schema') != 'FIGURE_DELIVERY_MANIFEST_1' or not isinstance(rows, list):
            raise ValueError('Unsupported manifest structure')
        expected = {}
        for row in rows:
            name = row['path']
            relative = PurePosixPath(name)
            if not isinstance(name, str) or relative.is_absolute() or '..' in relative.parts or '\\' in name or name == MANIFEST:
                raise ValueError('Unsafe or reserved manifest path')
            if name in expected:
                raise ValueError('Duplicate manifest path: ' + name)
            expected[name] = row
        actual = {}
        for path in ROOT.rglob('*'):
            if path.is_symlink():
                raise ValueError('Unexpected symbolic link: ' + str(path.relative_to(ROOT)))
            if path.is_file() and str(path.relative_to(ROOT)).replace('\\','/') != MANIFEST:
                actual[path.relative_to(ROOT).as_posix()] = path
        if set(actual) != set(expected):
            missing = sorted(set(expected) - set(actual))
            extra = sorted(set(actual) - set(expected))
            raise ValueError('File list differs; missing=' + repr(missing) + '; extra=' + repr(extra))
        for name, path in actual.items():
            row = expected[name]
            if path.stat().st_size != row['bytes']:
                raise ValueError('Size differs: ' + name)
            if hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
                raise ValueError('SHA-256 differs: ' + name)
        print('PASS: ' + str(len(actual)) + ' files match the closed delivery manifest.')
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print('FAIL: ' + str(exc), file=sys.stderr)
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
