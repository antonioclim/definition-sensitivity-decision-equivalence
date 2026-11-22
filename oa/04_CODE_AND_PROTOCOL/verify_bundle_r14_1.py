"""Check the exact public R14.1 file roster and SHA-256 identities."""
from pathlib import Path
from hashlib import sha256
import argparse
import json


def verify(root):
    root = root.resolve(); manifest_path = root / 'MANIFEST_SHA256.json'
    manifest = json.loads(manifest_path.read_bytes())
    declared = set(); errors = []
    for row in manifest['files']:
        rel = row['path']; path = (root / rel).resolve()
        if not path.is_relative_to(root) or path == manifest_path or rel in declared:
            errors.append('Invalid or duplicate path'); continue
        declared.add(rel)
        if not path.is_file():
            errors.append('Missing: ' + rel); continue
        if path.stat().st_size != row['bytes'] or sha256(path.read_bytes()).hexdigest() != row['sha256']:
            errors.append('Changed: ' + rel)
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and p != manifest_path}
    errors.extend('Unlisted: ' + p for p in sorted(actual - declared))
    return {'status': 'PASS_BUNDLE_INTEGRITY' if not errors else 'FAIL_BUNDLE_INTEGRITY',
            'manifest_sha256': sha256(manifest_path.read_bytes()).hexdigest(),
            'payload_files': len(declared), 'errors': errors,
            'scope': 'File roster and byte identity; not a signature, data-rights clearance or scientific validation.'}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('bundle', nargs='?', type=Path, default=Path(__file__).resolve().parents[1])
    r = verify(p.parse_args().bundle)
    print(json.dumps(r, indent=2)); raise SystemExit(bool(r['errors']))
